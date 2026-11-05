"""앱 전체를 인증번호 하나로 잠그는 가드.

이 앱은 승인된 관계자만 쓸 수 있어야 한다. 다만 주소만 알면 누구나 방송을 추출할 수
있으므로, 처음 접속했을 때 인증번호를 한 번 확인한 뒤 서명된 세션 쿠키로 그 기억을
유지한다.

인증번호는 평문으로 보내지 않는다. 로그인할 때마다 서버가 일회용 nonce를 내주고,
브라우저는 `sha256(인증번호 + ":" + nonce)` 만 보내며 서버는 같은 값을 직접 계산해
비교한다. 따라서 회선에는 인증번호도, 그것을 그대로 쓴 재사용 토큰도 오르지 않는다.

인증번호는 상태 파일(`APP_STATE_FILE`)에 날짜별로 보관한다. 매일 00시(`APP_TZ`,
기본 Asia/Seoul)에 6자리 랜덤 번호를 새로 만들고, 관리용 텔레그램
(`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`)으로 알려준다. 방송이 새벽까지 이어지므로
로그인은 당일자와 전일자 두 인증번호를 모두 허용한다. 잠금 자체는 `APP_AUTH=off`로
끌 수 있다(개발·테스트용).
"""

import fcntl
import hashlib
import json
import logging
import os
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from flask import jsonify, request, session

from stream_proxy import verify_share_token

logger = logging.getLogger(__name__)

# 더 이상 쓰이지 않는 환경변수. 아직 남아 있으면 시작 시 경고로 알린다.
PASSWORD_ENV = "APP_PASSWORD"
SECRET_ENV = "APP_SECRET_KEY"
STATE_ENV = "APP_STATE_FILE"
AUTH_ENV = "APP_AUTH"
TZ_ENV = "APP_TZ"
TELEGRAM_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ENV = "TELEGRAM_CHAT_ID"

# 로그인에 필요한 대화만 세션 없이 열어둔다. 나머지는 전부 잠금 대상이다.
# 프론트엔드 정적 파일은 nginx가 직접 서빙하므로 여기에 걸리지 않는다.
PUBLIC_PATHS = {"/api/auth/session", "/api/auth/challenge", "/api/auth/login"}

# 화면은 숫자 6자리 칸으로 받는다. 인증번호도 같은 길이로 만든다.
PIN_LENGTH = 6

# nonce는 한 번만 쓸 수 있고, 이 시간 안에 쓰지 않으면 버린다.
NONCE_TTL_SECONDS = 60
MAX_NONCES = 4096

# 이만큼 틀리면 잠긴다. 이후에는 실패를 세지 않고 잠금만 반복해서 건다.
MAX_ATTEMPTS = 5
# 첫 잠금은 10분. 다음부터는 2배씩 늘려 최대 하루까지는다.
BASE_LOCKOUT_MINUTES = 10
MAX_LOCKOUT_MINUTES = 24 * 60

# 자정 갱신 점검 주기. 백그라운드 스레드가 이 간격으로 날짜를 확인한다.
ROTATION_INTERVAL_SECONDS = 30
# 텔레그램 발송 제한. 한 번 갱신될 때마다 최대 이만큼만 기다린다.
TELEGRAM_TIMEOUT_SECONDS = 10
TELEGRAM_RETRIES = 3
TELEGRAM_RETRY_DELAY_SECONDS = 2

_state_lock = threading.Lock()
_rotation_started = False


def is_enabled():
    """잠금은 `APP_AUTH=off` 로만 끈다. 기본값은 켜짐이다."""
    return os.getenv(AUTH_ENV, "on").strip().lower() not in {"off", "0", "false", "no"}


def _state_path():
    return os.getenv(STATE_ENV, "/tmp/ls-grabber-auth.json")


@contextmanager
def _locked_state():
    """시도 횟수·nonce·날짜별 인증번호를 담은 상태 파일을 단독으로 연다.

    gunicorn 워커가 둘이라 프로세스마다 따로 세면 잠금을 뚫을 수 있다. 파일 락으로
    워커를 건너 같은 기록을 공유한다. 로그인할 때만 읽고 쓰므로 부하가 문제가 되지 않는다.
    """
    path = _state_path()
    with _state_lock:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            raw = os.read(fd, 1 << 20)
            state = json.loads(raw) if raw else {}
            state.setdefault("clients", {})
            state.setdefault("nonces", {})
            state.setdefault("passwords", {})
            yield state
            payload = json.dumps(state).encode("utf-8")
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _now():
    """APP_TZ(기본 Asia/Seoul) 기준 현재 시각.

    컨테이너는 기본값이 UTC라서 그대로 쓰면 한국의 00시에 갱신되지 않는다.
    """
    name = os.getenv(TZ_ENV, "Asia/Seoul").strip() or "Asia/Seoul"
    try:
        tz = ZoneInfo(name)
    except Exception:
        logger.warning("[auth] 알 수 없는 시간대 %s — Asia/Seoul 로 대신한다", name)
        tz = ZoneInfo("Asia/Seoul")
    return datetime.now(tz)


def _date_str(now=None):
    return (now or _now()).strftime("%Y-%m-%d")


def ensure_today_password():
    """오늘자 인증번호를 상태 파일에 보장하고 오래된 날짜를 지운다.

    (갱신했는지, 오늘 인증번호, 어제 인증번호)를 돌려준다. 갱신에 성공한 쪽만
    텔레그램을 보내도록 했으므로, 워커 둘이 동시에 돌아도 발송은 한 번만 된다.
    """
    today = _date_str()
    yesterday = _date_str(_now() - timedelta(days=1))
    with _locked_state() as state:
        passwords = state["passwords"]
        rotated = today not in passwords
        if rotated:
            passwords[today] = f"{secrets.randbelow(10 ** PIN_LENGTH):0{PIN_LENGTH}d}"
        # 방송이 새벽까지 이어지므로 어제 것은 하루 더 남긴다.
        for date in [d for d in passwords if d not in (today, yesterday)]:
            passwords.pop(date, None)
        today_pin = passwords[today]
        yesterday_pin = passwords.get(yesterday)

    if rotated:
        logger.info("[auth] 인증번호 갱신 date=%s pin=%s", today, today_pin)
        _notify_async(today, today_pin, yesterday_pin)
    return rotated, today_pin, yesterday_pin


def _valid_passwords():
    """로그인에 쓸 수 있는 인증번호. 오늘과 어제, 상태가 비면 오늘 것을 만든다."""
    _, today_pin, yesterday_pin = ensure_today_password()
    pins = [today_pin]
    if yesterday_pin:
        pins.append(yesterday_pin)
    return pins


def _build_message(date, today_pin, yesterday_pin):
    lines = [f"🔑 인증번호 갱신 ({date})", f"오늘: {today_pin}"]
    if yesterday_pin:
        lines.append(f"어제: {yesterday_pin} (오늘 24시까지 함께 유효)")
    return "\n".join(lines)


def _notify_sync(date, today_pin, yesterday_pin):
    """텔레그램으로 새 인증번호를 보낸다.

    못 보내도 갱신은 멈추지 않는다. 새 비밀번호는 이미 로그에 남아 있으니
    `docker logs` 로 되돌아올 수 있다.
    """
    token = os.getenv(TELEGRAM_TOKEN_ENV, "").strip()
    chat_id = os.getenv(TELEGRAM_CHAT_ENV, "").strip()
    if not token or not chat_id:
        logger.warning(
            "[auth] 텔레그램 미설정(%s/%s) — 인증번호는 로그에만 남는다 pin=%s",
            TELEGRAM_TOKEN_ENV, TELEGRAM_CHAT_ENV, today_pin,
        )
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": _build_message(date, today_pin, yesterday_pin)}
    for attempt in range(1, TELEGRAM_RETRIES + 1):
        try:
            response = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT_SECONDS)
            if response.ok:
                logger.info("[auth] 텔레그램 발송 완료 date=%s", date)
                return True
            logger.warning(
                "[auth] 텔레그램 응답 %s attempt=%s body=%s",
                response.status_code, attempt, response.text[:200],
            )
        except requests.RequestException as exc:
            logger.warning("[auth] 텔레그램 발송 실패 attempt=%s err=%s", attempt, exc)
        if attempt < TELEGRAM_RETRIES:
            time.sleep(TELEGRAM_RETRY_DELAY_SECONDS)
    logger.warning("[auth] 텔레그램 최종 실패 — 인증번호는 로그에 있다 pin=%s", today_pin)
    return False


def _notify_async(date, today_pin, yesterday_pin):
    """발송은 데몬 스레드로 떼어낸다. 로그인 화면을 텔레그램 응답만큼은 기다리게 하지 않는다."""
    threading.Thread(
        target=_notify_sync,
        args=(date, today_pin, yesterday_pin),
        name="auth-telegram",
        daemon=True,
    ).start()


def _rotation_loop():
    """자정이 바뀌면 새 인증번호를 만들고 텔레그램으로 보낸다.

    아무도 접속하지 않는 새벽에도 00시에 알림이 나가도록 백그라운드에서 돈다.
    워커마다 한 스레드씩 돌지만 상태 파일 flock 때문에 실제로 갱신·발송은
    한 쪽만 한다.
    """
    while True:
        time.sleep(ROTATION_INTERVAL_SECONDS)
        try:
            if is_enabled():
                ensure_today_password()
        except Exception:
            logger.exception("[auth] 인증번호 점검 중 오류")


def _start_rotation_thread():
    global _rotation_started
    if _rotation_started:
        return
    _rotation_started = True
    threading.Thread(target=_rotation_loop, name="auth-rotation", daemon=True).start()


def _client_key():
    # nginx가 같은 브라우저를 프록시하므로 remote_addr 만으로는 요청자를 구분할 수
    # 없다. 원본 IP가 있으면 그걸 보고, 없으면 그냥 전역 잠금을 건다.
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or request.remote_addr or "unknown"


def _lockout_minutes(lockouts):
    """잠금 횟수가 늘어갈수록 기다리는 시간이 2배씩 늘어난다."""
    minutes = BASE_LOCKOUT_MINUTES * (2 ** max(lockouts - 1, 0))
    return min(minutes, MAX_LOCKOUT_MINUTES)


def _stream_share_ok():
    """프록시 링크의 서명이 요청의 u 주소에 유효한지.

    request.args 는 이미 디코드된 값이라 여기서 다시 unquote 하면 안 된다.
    스트림 URL 은 Akamai 토큰(%2F 등)이 그대로 들어가 있어 이중 디코드면
    주소가 변조돼 서명 대조가 실패한다(실측).
    """
    target = request.args.get('u', '')
    token = request.args.get('k', '')
    return verify_share_token(target, token)


def _peek_block(client):
    """현재 잠겨 있는지, 얼마나 남았는지 본다."""
    with _locked_state() as state:
        record = state["clients"].get(client)
        if not record:
            return 0, 0
        blocked_until = record.get("blocked_until", 0)
        if blocked_until <= time.time():
            return 0, record.get("lockouts", 0)
        return int(blocked_until - time.time()), record.get("lockouts", 0)


def _record_failure(client):
    """실패를 쌓고, 한도를 넘으면 잠근다. (잠긴 총 시간, 현재 잠금 남은 초)를 돌려준다."""
    with _locked_state() as state:
        record = state["clients"].setdefault(client, {"failures": 0, "lockouts": 0})
        record["failures"] = record.get("failures", 0) + 1
        if record["failures"] < MAX_ATTEMPTS:
            remaining = MAX_ATTEMPTS - record["failures"]
            return 0, remaining, record.get("lockouts", 0)

        record["lockouts"] = record.get("lockouts", 0) + 1
        record["failures"] = 0
        seconds = _lockout_minutes(record["lockouts"]) * 60
        record["blocked_until"] = time.time() + seconds
        return seconds, 0, record["lockouts"]


def _clear_client(client):
    """맞으면 누적 기록을 전부 지운다."""
    with _locked_state() as state:
        state["clients"].pop(client, None)


def _issue_nonce():
    nonce = secrets.token_hex(16)
    now = time.time()
    with _locked_state() as state:
        nonces = state["nonces"]
        for expired in [n for n, t in nonces.items() if t <= now]:
            nonces.pop(expired, None)
        # 혹시 순간 요청이 몰리면 가장 오래된 것부터 버린다.
        while len(nonces) >= MAX_NONCES:
            nonces.pop(next(iter(nonces)))
        nonces[nonce] = now + NONCE_TTL_SECONDS
    return nonce


def _take_nonce(nonce):
    """nonce를 받아서 즉시 없앤다. 한 번 쓰면 다시 못 쓴다."""
    if not nonce or not isinstance(nonce, str):
        return False
    with _locked_state() as state:
        expires_at = state["nonces"].pop(nonce, 0)
    return expires_at > time.time()


def _expected_proofs(nonce):
    """서버가 직접 계산하는 정답들(오늘·어제). 브라우저와 똑같은 식을 쓴다."""
    return [
        hashlib.sha256(f"{pin}:{nonce}".encode("utf-8")).hexdigest()
        for pin in _valid_passwords()
    ]


def install(app):
    """앱에 세션 기반 잠금을 건다. app.py 에서 한 번만 호출한다."""
    app.config.update(
        SECRET_KEY=os.getenv(SECRET_ENV) or "insecure-dev-secret",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # 새로고침마다 다시 치지 않도록 한 달 정도 기억한다.
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    # 자정 갱신은 요청이 없어도 돌도록 백그라운드에서 시작한다.
    _start_rotation_thread()

    @app.before_request
    def _require_password():
        if not is_enabled() or request.path in PUBLIC_PATHS:
            return None
        if session.get("authed"):
            return None

        # 프록시 스트림 링크는 앱 밖(플레이어, 다른 브라우저)에서 붙여넣어 쓰는
        # 일이 있다. 세션 쿠키가 없어도 그 주소의 서명된 토큰이 유효하면 그
        # 주소 한 건만 통과시킨다. 서명이 없거나 옳지 않으면 401 이다.
        if request.path == "/api/stream" and _stream_share_ok():
            return None

        return jsonify({"error": "Unauthorized", "auth_required": True}), 401

    @app.route("/api/auth/session", methods=["GET"])
    def auth_session():
        # 날짜가 바뀐 뒤 첫 방문에서도 오늘 인증번호가 미리 준비되도록 한다.
        if is_enabled():
            ensure_today_password()
        return {"authed": bool(session.get("authed")), "enabled": is_enabled()}

    @app.route("/api/auth/challenge", methods=["GET"])
    def auth_challenge():
        """인증번호를 담지 않은 일회용 값을 내준다."""
        if not is_enabled():
            return {"enabled": False}
        ensure_today_password()
        return {"nonce": _issue_nonce(), "expires_in": NONCE_TTL_SECONDS}

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        key = _client_key()

        blocked_for, lockouts = _peek_block(key)
        if blocked_for:
            logger.warning("[auth] locked out client=%s remaining=%ss lockouts=%s", key, blocked_for, lockouts)
            return jsonify({
                "error": "too_many_attempts",
                "retry_after": blocked_for,
                "lockout_minutes": _lockout_minutes(lockouts),
                "lockouts": lockouts,
            }), 429

        body = request.get_json(silent=True) or {}
        # nonce는 검증 결과와 무관하게 한 번만 쓸 수 있다. 틀렸어도 다시 안 된다.
        nonce = body.get("nonce")
        proof = body.get("proof")
        if not _take_nonce(nonce):
            logger.warning("[auth] stale or reused nonce client=%s", key)
            return jsonify({"error": "stale_nonce"}), 400

        # 길이 차이로 비교 시간이 새지 않도록 상수 시간 비교를 쓴다.
        # 오늘과 어제 두 인증번호 중 하나와 맞으면 통과한다.
        valid = isinstance(proof, str) and any(
            secrets.compare_digest(proof, expected)
            for expected in _expected_proofs(nonce)
        )
        if not valid:
            seconds, attempts_left, lockouts = _record_failure(key)
            logger.warning(
                "[auth] wrong password client=%s lockouts=%s next_lockout=%ss",
                key, lockouts, seconds,
            )
            if seconds:
                logger.warning(
                    "[auth] client=%s 잠금 %s분 (%s회 연속 실패)",
                    key, _lockout_minutes(lockouts), lockouts,
                )
            return jsonify({
                "error": "invalid_password",
                "attempts_left": attempts_left,
                "lockout_minutes": _lockout_minutes(lockouts) if seconds else 0,
            }), 401

        _clear_client(key)
        session.clear()
        session["authed"] = True
        session.permanent = True
        logger.info("[auth] logged in client=%s", key)
        return {"ok": True}

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        session.clear()
        return {"ok": True}
