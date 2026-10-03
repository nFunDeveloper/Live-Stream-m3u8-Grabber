# M3U8 Grabber

한국 라이브 스트리밍 플랫폼의 M3U8 스트림 URL을 추출하고, 내장 HLS 플레이어에서 바로 확인할 수 있는 웹 서비스입니다.

## 주요 기능

- **원클릭 추출**: 방송 URL 입력 시 M3U8 주소와 방송 정보(제목, 스트리머명, 카테고리, 시작 시각, 시청자 수)를 함께 추출
- **내장 플레이어**: hls.js 기반 즉시 재생, CORS 차단 시 M3U8 복사로 폴백
- **검색 히스토리**: 사이드바에 플랫폼별로 누적, 클릭하면 즉시 재조회
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
  --exclude='.git' --exclude='node_modules' --exclude='__pycache__' \
  ./ oracle:workspace/Live-Stream_m3u8_Grabber/

# 3. 서버에서 Docker 빌드 & 기동
ssh oracle
cd workspace/Live-Stream_m3u8_Grabber
sudo docker compose up -d --build
```

### 접속 방법

| URL | 설명 |
|-----|------|
| `http://localhost:10000/` | 프로덕션 React UI |
| `http://localhost:10000/api/grab?url=...` | Flask API |

> 서버에서는 nginx 설정(`proxy_pass`)을 통해 외부 도메인으로 연결합니다.

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
