# 화질 매트릭스 테스트 가이드

플랫폼별 화질 선택이 실제로 동작하는지 점검하는 절차. 치지직이 특정 화질 URL을
못 만들어 404를 내던 문제(커밋 dd54d2f)를 비롯해, 플랫폼이 응답 형식을 바꿨을 때
이 테스트가 먼저 잡아낸다.

## 빠른 실행

```bash
# 1) 개발 서버 기동 (backend 가 소스를 이미지에 굽는다 — restart 로는 반영 안 됨)
cd <repo>
docker compose -f docker-compose.dev.yaml up -d --build backend
docker compose -f docker-compose.dev.yaml up -d          # nginx/vite 상태 재확인 (위 명령이 놓칠 때가 있다)

# 2) 매트릭스 실행 — 외부 의존성 없음 (urllib 만 사용)
python3 stream-service/tests/quality_matrix_probe.py               # 전체 플랫폼
python3 stream-service/tests/quality_matrix_probe.py --platform chzzk
python3 stream-service/tests/quality_matrix_probe.py --pin 1322    # PIN 변경 시
python3 stream-service/tests/quality_matrix_probe.py --base http://127.0.0.1:10000
```

출력 판정:

| 표기 | 의미 |
|---|---|
| `OK` + `/1080p/` 같은 접미어 | 주소에 화질이 직접 담긴 chunklist — 화질 선택이 실제로 작동 |
| `OK` + `RESOLUTION=...` 나열 | master 플레이리스트를 돌려준 것. ABR가 알아서 고르는 경로 |
| `404` / `no-url` | 백엔드가 화질 주소를 못 만들었다 — 조합 로직 문제 |
| `500` + Read timed out | 상위 CDN이 느리거나 죽은 것. 재시도로 확인 (코드 문제 아님) |
| `채널 없음` | 지금 라이브 방송이 없어 검증 불가. 실험 실패이지 버그가 아니다 |

## 깊이 디버깅 (플랫폼 모듈 단독)

HTTP 경로를 건너뛰고 모듈만 확인할 때. venv 는 임시로 만들어 쓴다(/tmp 는 지워진다).

```bash
python3 -m venv /tmp/probe-venv
/tmp/probe-venv/bin/pip install requests flask
```

```python
import sys, os, logging, subprocess
sys.path.insert(0, "<repo>/stream-service/src")
logging.disable(logging.INFO)          # chzzk.py 은 CHZZK_LOG_RESPONSE_MAX 로 대량 로깅
from platform_modules.chzzk import Chzzk
info = Chzzk().get_live("<채널ID>", "1080p")
url = info.get("m3u8_url", "")
print("m3u8_url:", url or "(빈 URL = 404)")
# 실제로 열리는지
if url:
    print(subprocess.run(["curl","-s","-o","/dev/null","-w","%{http_code}", url],
        headers=["User-Agent: Mozilla/5.0"], capture_output=True).stdout)
```

## 채널 ID 얻기

```bash
curl -s "http://127.0.0.1:10000/api/search?q=게임"   # 로그인 필요
# results[].platform / streamer_id / url
```

## 플랫폼별 알려진 상수와 함정

**국내 경로 원칙** — 라이브 스트림(재생 바이트)은 국내 경로에서 받아야 한다.
SOOP assign 의 cors_origin_url 를 play.sooplive.co.kr 로 걸어야 국내 CDN
(pc-web/mobile-web.stream.sooplive.co.kr) 이 배정된다. play.sooplive.com 을 걸면
같은 요청이 해외 CDN(.com)을 돌려준다(실측). 추천 목록 SOOP 소스도 한국어
정적 파일(ko_KR)만 쓴다 — en_US 는 국제 서비스 파일이라 금지.

**치지직 (chzzk)** — `encodingTrack`의 영상 트랙 `path`는 비어 있고(audioOnly만 채움),
마스터 variant 앞에 Akamai 토큰(`hdntl=...`)이 붙어 있어 화질 조각이 경로 중간에 온다.
매칭은 `quality in variant_path.split("/")` — `startswith` 로 쓰면 전부 실패.
p2pPath 쿼리의 `cdn_url=<base64>` 이 실제 CDN 주소(hdnts 토큰 포함) — 폴백 쓸 수 있다.
CDN 호스트는 방송마다 다르다(nvelop-/fcdn-/ex-nlive-streaming.navercdn.com) — 하드코딩 금지.

**SOOP (soop)** — master의 실측 최댓값은 960x540/640x360 (66개 방송 전부).
방송자 원본이 1920x1080@8000kbps인 채널에서 원본 assign(original/hd4k/hd/sd ×
pc_web/mobile_web × cors .com/.co.kr × player_mode live/landing/dash)을 모두
시험했으나 전부 동일한 960x540 chunklist를 돌려준다 — assign 은 요청 화질을
무시한다(soop.py 주석 참조). 국내(.co.kr)와 해외(.com) 접속 차이는 없음.
`livestream-manager.sooplive.co.kr`은 DNS가 실패한다. `.com`만 동작.
특정 화질(540p)이 간혈적으로 `pc-web.stream.sooplive.co.kr` 타임아웃/500 — 임시성.
방송 정보의 `viewpreset`(품질 목록)과 `resolution`(방송자 원본)이 권위 있는 원천.
고해상도는 로그인 인증이 붙은 시청 세션에서만 열릴 가능성(검증 미완).

**cime/pandalive/popkon** — master 플레이리스트의 `RESOLUTION`에서 variant를 고른다
(platform_default._stream_info_matches_quality: NAME/VIDEO 속성, x<높이>). 실측 최대
1920x1010이라 1080p 정확 매칭은 불가 — 요청하면 ABR(master)로 폴백하도록 UI가 숨긴다.

**pandalive/popkon** — 라이브 채널이 늘 적다. "채널 없음"은 버그가 아니고 재시도 대상.
검색 키워드를 넓혀도 0이면 그 시간대에 생태계에 라이브가 없는 것.

## 주의

- 인증: 개발 PIN 기본 1322. 로그인은 `/api/auth/challenge` → `sha256(핀:nonce)`.
  필드는 `proof`(password 가 아니다). 실패하면 attempts_left 소진.
- 멀티뷰와 화질 캡(`MULTIVIEW_MAX_HEIGHT=480`)은 별개. 매트릭스는 단일 재생 기준으로
  본 것이므로 멀티뷰 상한이 화면에 나온 480p 와 혼동하지 않는다.
- 운영 배포는 서버에서 빌드하지 않고 rsync + `docker compose up -d --build` — README 참조.
- 서버에 테스트 결과 흔적(잠금 기록)이 남을 수 있다. 오류 시도 반복 말 것.