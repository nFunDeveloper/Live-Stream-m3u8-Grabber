# M3U8 Grabber

한국 라이브 스트리밍 플랫폼의 M3U8 스트림 URL을 추출하고, 내장 HLS 플레이어에서 바로 확인할 수 있는 웹 서비스입니다.

## 주요 기능

- **실시간 방송 검색**: 상단 검색 바에서 키워드로 방송 중인 채널을 즉시 검색 (치지직·ci.me 지원)
- **원클릭 추출**: 방송 URL 입력 시 M3U8 주소와 방송 정보(제목, 스트리머명, 카테고리, 시작 시각, 시청자 수)를 함께 추출
- **내장 플레이어**: hls.js 기반 즉시 재생, CORS 차단 시 M3U8 복사로 폴백
- **검색 히스토리**: 사이드바에 누적, 클릭하면 즉시 재조회, 그룹으로 드래그 가능
- **그룹**: 자주 보는 방송인을 그룹으로 묶어 클릭 한 번에 재조회
- 히스토리·그룹은 **브라우저(localStorage)에만 저장**되며 서버에는 기록되지 않습니다.

## 지원 플랫폼

| 플랫폼 | 도메인 패턴 |
|--------|-------------|
| 치지직 (Chzzk) | `chzzk.naver.com/live/{id}` |
| SOOP (구 AfreecaTV) | `play.sooplive.co.kr/{id}` |
| ci.me | `ci.me/@{slug}/live` |
| 팬더라이브 | `pandalive.co.kr/play/{id}` |
| 팝콘TV | `popkontv.com/live/view?castId=...` |

---

## 프로젝트 구조

```
LiveStreamM3U8Grabber/
├── docker-compose.yaml              # 프로덕션 compose
├── docker-compose.dev.yaml          # 개발 compose
├── nginx/
│   ├── nginx.prod.conf              # 프로덕션 nginx 설정
│   ├── nginx.dev.conf               # 개발 nginx 설정
│   └── Dockerfile.dev               # 개발용 nginx 이미지
├── stream-service/
│   ├── Dockerfile.backend           # Flask API 전용 (gunicorn, Node.js 없음)
│   ├── Dockerfile.nginx             # 프로덕션 nginx (빌드된 dist/ COPY)
│   ├── requirements.txt
│   ├── tests/                       # 단위 테스트 (python -m unittest discover -s tests)
│   └── src/
│       ├── app.py                   # Flask API 서버
│       ├── platform_modules/        # 플랫폼별 M3U8/메타데이터 추출 모듈
│       │   ├── chzzk.py
│       │   ├── soop.py
│       │   ├── cime.py
│       │   ├── pandalive.py
│       │   └── popkon.py
│       └── ui/                      # React 프론트엔드
│           ├── src/
│           │   ├── App.jsx          # 레이아웃 & 추출 플로우
│           │   ├── components/      # Sidebar(히스토리/그룹), PlayerPanel
│           │   └── lib/             # localStorage 저장소, 플랫폼 메타
│           ├── dist/                # 빌드 결과물 (레포에 포함)
│           ├── vite.config.js
│           └── package.json
```

## 아키텍처

```
┌──────────────────────────────────────────┐
│            nginx (단일 포트)              │
├────────────────┬─────────────────────────┤
│  프로덕션       │  개발                    │
│  / → dist/     │  / → /develop/ 리다이렉트│
│  /api → Flask  │  /develop/ → Vite dev   │
│                │  /api → Flask            │
└────────────────┴─────────────────────────┘
```

- **프로덕션**: nginx가 빌드된 React 앱을 서빙하고, API 호출은 Flask 백엔드로 프록시
- **개발**: nginx가 `/develop/` 경로의 요청을 Vite 개발 서버(HMR)로 프록시

> ⚠️ **서버에서는 프론트엔드 빌드(`npm ci`, `npm run build`)를 절대 실행하지 않습니다.**
> 프론트엔드 빌드는 로컬에서 수행하고, 빌드 결과물(`dist/`)만 서버로 전송합니다.

---

## 개발 환경

### 사전 요구사항

- Docker & Docker Compose
- Node.js (로컬에서 프론트엔드 빌드 시)

### 실행 방법

```bash
# 개발 환경 기동
docker compose -f docker-compose.dev.yaml up --build
```

| 컨테이너 | 역할 |
|----------|------|
| `nginx` | 리버스 프록시 (단일 진입점) |
| `vite-dev` | React 개발 서버 (HMR 지원) |
| `backend` | Flask API 서버 |

### 접속 방법

| URL | 설명 |
|-----|------|
| `http://localhost:10000/` | 자동으로 `/develop/`으로 리다이렉트 |
| `http://localhost:10000/develop/` | React 개발 UI (코드 수정 시 자동 리로드) |
| `http://localhost:10000/api/grab?url=...` | Flask API |

### 비밀번호 잠금

앱을 열면 가운데 인증번호 4자리 입력창이 뜨고, 통과해야 본 화면이 열린다.
승인된 관계자만 쓸 수 있어야 하는 앱이라 주소를 알면 아무나 방송을 추출할 수
있어서 막는 것이다. 통과한 뒤에는 서명된 세션 쿠키로 기억되므로 새로고침해도
다시 묻지 않는다(30일).

| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `APP_PASSWORD` | `1322` | 화면을 여는 인증번호. 숫자 4자리여야 화면과 맞는다 |
| `APP_SECRET_KEY` | 고정 기본값 | 세션 쿠키 서명 키. 바꾸면 전원이 다시 인증번호를 쳐야 한다 |
| `APP_STATE_FILE` | `/state/auth.json` | 잠금 횟수·nonce가 저장되는 파일 (운영은 볼륨에 둔다) |

```bash
APP_PASSWORD='1234' docker compose -f docker-compose.dev.yaml up -d --build backend
```

- 입력창은 4칸이므로 `APP_PASSWORD` 가 4자리가 아니면 시작 로그에 경고로 남는다.
- 입력 칸은 `type="password"` 로 마스킹된다. 화면에 어깨너머로 보이는 일도,
  브라우저가 폼 값을 되짚어 보여주는 일도 없다. 숫자 키패드는 `inputMode="numeric"`
  으로 그대로 유지된다.

#### 인증번호는 평문으로 오가지 않는다

로그인할 때 서버가 일회용 `nonce`를 내주고, 브라우저는 `sha256(인증번호 + ":" + nonce)`
값만 보냅니다. 서버는 nonce 를 즉시 버리기 때문에 같은 증명을 다시 보낼 수 없습니다.

```
GET  /api/auth/challenge  →  {"nonce":"9f2c...","expires_in":60}
POST /api/auth/login      →  {"nonce":"9f2c...","proof":"3a71..."}   // sha256 결과만
```

- `sha256`은 `src/ui/src/lib/sha256.js`로 직접 계산한다. Web Crypto의
  `crypto.subtle` 은 보안 컨텍스트(HTTPS) 에서만 노출되므로 HTTP로 열어둔
  배포 환경에서는 쓸 수 없다.
- 이렇게 하면 회선을 지켜보는 사람은 비밀번호도, 재사용 가능한 토큰도 얻지 못한다.
  다만 HTTP로는 중간인이 요청을 그대로 넘길 수 있다. 인터넷에 노출할 계획이면
  nginx에 HTTPS를 씌워야 이 잠금이 완성된다.

#### 실패 횟수와 잠금

| 횟수 | 동작 |
|------|------|
| 1~4회 틀림 | "N회 더 틀리면 잠깁니다" 안내만 표시 |
| 5회째 | 10분 잠금 |
| 잠금 후 다시 실패 | 20분 → 40분 → 80분 … 2배씩, 최대 24시간 |
| 성공 | 누적 횟수·잠금 기록 전부 초기화 |

- 잠금은 워커가 2개인 gunicorn에서도 흔들리지 않도록 상태 파일(`APP_STATE_FILE`)에
  기록하고 `flock` 으로 워커를 건너 공유한다.

#### 알아서 잠기는 경우

| 걸림 | 동작 |
|------|------|
| 마우스·키보드·스크롤·터치를 1시간 동안 안 건드림 | 알아서 잠금 |
| 오른쪽 위 자물쇠 버튼 | 바로 잠금 |

- 잠겨도 앱은卸载되지 않는다. 잠금창이 화면 위에 덮이고 뒤쪽 앱에는 `inert` 만
  걸린다. 다시 인증번호를 치면 재생 중이던 영상, 멀티뷰, 검색창에 쳐둔 주소,
  사이드바 기록이 그대로 살아있다.
- 잠글 때 서버에 `/api/auth/logout` 을 먼저 보내므로, 브라우저를 그냥 닫아도
  서버 측 세션은 끝난다.
- **강력 새로고침만 잠기는 것은 할 수 없다.** 새로고침 종류를 가르는 표준 수단이
  Navigation Timing 의 `transferSize` / `responseStatus` 인데, 이 앱은 nginx가
  매번 200을 새로 만들어 주기 때문에 일반 새로고침과 강력 새로고침이 구분되지 않는다.
  측정 결과 둘 다 `type: "reload"`, `transferSize: 300`, `responseStatus: 200` 이었다.
  대신 자물쇠 버튼을 뒀다.

#### 그 외

- `APP_PASSWORD`를 비우면 잠금이 꺼지고 로그에 경고가 남는다. 테스트도 이 상태를 쓴다.
- 잠금 여부는 프론트가 아니라 백엔드가 강제한다. 잠그지 않은 상태로 `/api/grab`을
  직접 불러도 401이 돌아온다.

### 개발 시 주의사항

- `docker-compose.dev.yaml` 전환 후 **반드시 `--build` 포함** 실행
- 코드 수정 시 `/develop/` 페이지가 자동 리로드됨 (HMR)
- `vite.config.js`의 `VITE_BASE=/develop/`은 `docker-compose.dev.yaml`에서 환경변수로 주입

---

## 운영 환경

### 로컬 프로덕션 빌드 & 실행

```bash
# 1. 프론트엔드 빌드 (Node.js 필요)
cd stream-service/src/ui
npm install && npm run build    # → dist/ 생성

# 2. 프로덕션 기동
cd ../../..
docker compose up -d --build
```

### 서버 배포

```bash
# 1. 로컬에서 프론트엔드 빌드
cd stream-service/src/ui
npm install && npm run build

# 2. 소스코드 + dist/ 서버로 전송
rsync -avz --delete \
  --exclude='.git' --exclude='node_modules' --exclude='__pycache__' --exclude='.env' \
  ./ oracle:workspace/Live-Stream_m3u8_Grabber/

# 3. 서버에서 Docker 빌드 & 기동
ssh oracle
cd workspace/Live-Stream_m3u8_Grabber
sudo docker compose up -d --build
```

`dist/` 를 저장소에 들여 보내기 때문에 **서버에서 Node를 돌릴 필요가 없다.**
프론트엔드를 서버에서 빌드하지 않는 것이 이 저장소의 규칙이다.

#### `.env` (서버에 한 번만 만들어 둔다)

`rsync` 는 `.env` 를 건너뛰므로 서버에 직접 만들어 둔다. 지우면 인증번호가
기본값 `1322` 로, 서명 키는 everyone-knows 값으로 돌아간다.

```bash
cd workspace/Live-Stream_m3u8_Grabber
umask 077
printf 'APP_PASSWORD=1322\nAPP_SECRET_KEY=%s\n' "$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" > .env
```

- `APP_SECRET_KEY` 를 바꾸면 접속해 있던 모두가 다시 인증번호를 쳐야 한다.
- 실패 횟수·nonce 는 `auth-state` 볼륨의 `/state/auth.json` 에 남는다.
  컨테이너 안 `/tmp` 에 두면 재시작할 때 잠금 기록이 사라진다.

#### 되돌리기

배포 전 상태는 `~/workspace/.backups/live-stream_<타임스탬프>/` 에 남는다.
문제가 생기면 그 디렉터리로 되돌리고 이전 이미지로 다시 올린다.

```bash
cd ~/workspace
cp -a .backups/live-stream_<타임스탬프>/Live-Stream_m3u8_Grabber/. Live-Stream_m3u8_Grabber/
cd Live-Stream_m3u8_Grabber && sudo docker compose up -d --build
```

### 접속 방법

| URL | 설명 |
|-----|------|
| `https://stream.xxs.kr/` | 운영 UI (Let's Encrypt 인증서, nginx → 10000) |
| `https://stream.xxs.kr/api/grab?url=...` | Flask API |

> 서버의 nginx가 `stream.xxs.kr` → `localhost:10000`(컨테이너 nginx)으로 넘긴다.
> 운영 nginx 설정이 원래 방문자의 IP 를 넘겨야 잠금 횟수가 사람별로 따로 센다.
> `X-Forwarded-For` 를 빠뜨리면 모든 요청이 컨테이너 IP 로 보여서 한 사람의
> 실수가 남까지 잠근다.

### 컨테이너 구성

| 컨테이너 | 역할 | 포트 |
|----------|------|------|
| `nginx` | 정적 파일 서빙 + API 프록시 | 10000 → 80 |
| `backend` | Flask API 전용 | 10000 (내부) |

---

## API

### GET `/api/grab`

M3U8 스트림 URL을 추출합니다.

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `url` | ✅ | 스트리밍 채널 URL |
| `quality` | ❌ | 화질 (기본: `auto`) — `auto`, `1080p`, `720p`, `540p`, `480p`, `360p`, `144p` |

**응답 예시:**
```json
{
  "m3u8_url": "https://...",
  "platform": "chzzk",
  "streamer_id": "channel_id",
  "quality": "auto",
  "title": "방송 제목",
  "streamer_name": "채널명",
  "category": "게임/카테고리",
  "started_at": "2026-10-03 08:09:20",
  "viewers": 10240,
  "thumbnail": "https://..."
}
```

> 메타데이터 필드는 플랫폼별로 제공 범위가 다를 수 있습니다.

### GET `/api/search`

방송 중인 채널을 키워드로 검색합니다. `search_lives`를 구현한 플랫폼(치지직, ci.me)만 병렬 조회하며, 결과는 시청자 수 내림차순입니다.

| 파라미터 | 필수 | 설명 |
|----------|------|------|
| `q` | ✅ | 검색 키워드 |

### GET `/<platform>/<streamer_id>/<quality>`

레거시 엔드포인트. M3U8 URL로 302 리다이렉트합니다.

### GET `/detect/<quality>?url=...`

URL을 자동 감지하여 M3U8 URL로 302 리다이렉트합니다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 백엔드 | Python 3.12, Flask |
| 프론트엔드 | React 19, Vite 8, Tailwind CSS, HeroUI |
| HLS 재생 | hls.js |
| 리버스 프록시 | nginx |
| 컨테이너 | Docker, Docker Compose |
