# Remote Agent 연동 계약 (v2)

웹 UI(stream.xxs.kr/remote)가 사용자 PC의 로컬 에이전트를 제어하기 위한 통신 규격.
로컬 에이전트는 이 문서만 보고 구현하면 된다.

## 개요

```
[사용자 PC 브라우저]  https://stream.xxs.kr/remote
        │  (페이지 로딩)
        ▼
[웹 UI] ── HTTP JSON ──▶ http://127.0.0.1:17300  ◀── [로컬 에이전트]
                           (localhost 전용 리스닝)        (릴레이 도구 + HTTP 서버)
```

- 승인/페어링 절차 없음. 에이전트는 127.0.0.1에 HTTP 서버만 열면 된다.
- 모든 통신은 브라우저가 에이전트로 직접 요청하는 구조다(웹 서버는 개입하지 않음).
- 상태 확인은 2~3초 간격 폴링으로 한다(WebSocket 불필요).

## 포트

- **TCP 17300**, bind **127.0.0.1** (외부 인터페이스에 절대 열지 말 것)
- 기존 사용 포트와 충돌하지 않음: 10000(stream-service), 9001~9012(vMix SRT),
  19100~19112(pacer TCP 피드), 5173(vite dev)

## CORS (필수)

브라우저는 https(stream.xxs.kr)에서 http://127.0.0.1로 요청한다.
에이전트는 모든 응답에 다음 헤더를 붙이고, `OPTIONS` 프리플라이트에 204로 응답한다.

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, OPTIONS
Access-Control-Allow-Headers: Content-Type
Access-Control-Allow-Private-Network: true
```

마지막 줄은 Chrome의 Private Network Access(로컬 네트워크 접근 사전요청) 대응이다.
`Access-Control-Request-Private-Network: true` 헤더가 온 프리플라이트에도 동일하게 답한다.

> **mixed content 주의**: https 페이지에서 http://127.0.0.1로의 fetch는 브라우저 정책에 의해
> 차단될 수 있다. Chrome은 localhost를 secure context로 인정하므로 통과하는 경우가 많지만,
> 차단되는 구버전/브라우저에서는 웹 UI가 "연결할 수 없음" 화면을 보여준다.
> 우회책: (1) Chrome 최신 버전 사용, (2) 크롬://flags 의 mixed-content 관련 플래그,
> (3) 에이전트를 https화(자체 셀프사인 인증서 — 브라우저 경고 추가 발생).

## 응답 형식

- 모든 응답은 `Content-Type: application/json; charset=utf-8` (로그 엔드포인트 포함)
- 에러: HTTP 4xx/5xx + `{"error": "사용자 표시용 메시지"}`

## 엔드포인트

### GET /agent/info

연결 확인용. 웹 UI는 진입 시 한 번 호출하고, 이후 재연결 시도 때마다 다시 부른다.

```json
{ "name": "srt-relay-agent", "version": "1.0.0", "api_version": 1 }
```

`api_version`이 1이 아니면 웹 UI가 "호환되지 않는 버전"을 표시한다.

### GET /agent/status

슬롯(SRT 스트림) 상태. 2~3초마다 폴링된다.

```json
{
  "sessions": [
    {
      "id": "9001",
      "label": "슬롯 1",
      "port": 9001,
      "state": "running",
      "last_error": null
    }
  ],
  "vmix_ports": [ { "port": 9001, "alive": true } ],
  "last_error": null
}
```

- 슬롯과 세션은 **포트로 1:1 대응**한다(슬롯 인덱스 i → 포트 9001+i).
  웹 UI는 `port`로 세션을 찾아 상태·제어 버튼을 슬롯 카드에 붙인다.
- `state`: `stopped` | `starting` | `running` | `waiting` | `error`
  - `waiting`: m3u8 다운로드 대기/재시도 중 (SrtRelay의 "waiting" 상태와 매핑)
- `vmix_ports`: vMix SRT 리스너 생사 (UDP/TCP 프로브 결과). 웹 UI가 상태 점으로 표시
- `last_error`: 최근 오류 한 줄, 없으면 null

### POST /agent/sessions/{id}/start · /stop · /restart

세션 제어. 성공 시 `{"ok": true}`. `id`는 `/agent/status`가 돌려준 세션 id(= 포트 문자열).

### GET /agent/config

SRT 슬롯 목록(포트 9001부터 증가). SrtRelay의 pacer_config.txt 역할 + 슬롯 크기.

```json
{
  "slots": [
    {
      "id": "slot-0",
      "port": 9001,
      "page_url": "https://chzzk.naver.com/live/xxxxxxxx",
      "m3u8_url": "https://...playlist.m3u8?token=...",
      "quality": "auto",
      "platform": "chzzk",
      "streamer_name": "스트리머이름",
      "title": "방송 제목"
    }
  ]
}
```

- **슬롯 인덱스 i의 `port`는 `9001 + i`** — 웹 UI가 이 값을 준다. 에이전트는
  슬롯 수에 맞춰 세션(릴레이 프로세스)을 만들고/제거한다.
- **에이전트가 실제로 재생에 쓰는 필드는 `m3u8_url`뿐**이다. 나머지는 웹 UI 표시용
  메타데이터이므로 그대로 보관·반환하면 된다. `m3u8_url`이 빈 문자열이면 그 슬롯은
  건너뛴다(빈 슬롯).
- `page_url`: 방송 페이지 주소(치지직 live URL 등). 토큰 갱신(재추출)에 쓰인다.
- `quality`: `auto` | `1080p` | `720p` | ... (웹 UI가 추출할 때 사용)

### PUT /agent/config

슬롯 목록 전체를 교체한다(슬롯 수 변경 포함). 바디:

```json
{ "slots": [ /* GET /agent/config 와 동일한 shape */ ] }
```

성공 시 `{"ok": true}`. 웹 UI는 모든 변경(슬롯 수 조절, 방송 드롭, URL 붙여넣기,
토큰 갱신, 제거)을 **저장 버튼 없이 즉시 PUT**한다. 에이전트는 PUT을 받으면
슬롯 수에 맞춰 세션을 만들/죽이고, `m3u8_url`이 바뀐 세션은 재시작해도 된다
(웹 UI는 다음 status 폴링으로 상태를 갱신한다).

### GET /agent/logs?session_id=<id>&limit=<n>

세션 로그 tail. 기본 `limit=100`, 최대 500.

```json
{ "lines": ["2026-10-31 12:00:01 [9001] started", "..."] }
```

`session_id` 생략 시 전체 세션 통합 로그. `session_id`는 세션 id(= 포트 문자열).

## 웹 UI가 이미 제공하는 것 (에이전트는 신경 쓰지 않아도 됨)

- 방송 검색/추출(`/api/search`, `/api/grab`)은 웹 서버(nginx+Flask)가 처리한다.
  에이전트는 m3u8 URL을 받기만 하면 된다.
- 사이트 PIN 인증은 웹 페이지 진입 시에만 있고, 에이전트 통신에는 관여하지 않는다.

## 에이전트 구현 체크리스트

- [ ] 127.0.0.1:17300 HTTP 서버 (외부 바인드 금지)
- [ ] OPTIONS 프리플라이트 + CORS 헤더 (위 참조)
- [ ] GET /agent/info, /agent/status (슬롯=포트 1:1, 상태 세션 매핑)
- [ ] POST /agent/sessions/{id}/start|stop|restart (id = 포트 문자열)
- [ ] GET/PUT /agent/config (슬롯 수 즉시 반영 — 세션 생성/제거, m3u8_url 변경 시 재시작)
- [ ] GET /agent/logs
