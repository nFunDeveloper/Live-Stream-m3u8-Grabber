"""앱 전체를 비밀번호 하나로 잠그는 가드.

이 앱은 승인된 관계자만 쓸 수 있어야 한다. 다만 주소만 알면 누구나 방송을 추출할 수
있으므로, 처음 접속했을 때 비밀번호를 한 번 확인한 뒤 서명된 세션 쿠키로 그 기억을
유지한다.

비밀번호는 평문으로 보내지 않는다. 로그인할 때마다 서버가 일회용 nonce를 내주고,
브라우저는 `sha256(비밀번호 + ":" + nonce)` 만 보내며 서버는 같은 값을 직접 계산해
비교한다. 따라서 회선에는 비밀번호도, 그것을 그대로 쓴 재사용 토큰도 오르지 않는다.

비밀번호는 코드에 넣지 않고 APP_PASSWORD 환경변수로 받는다. 값이 비어 있으면 잠금을
건지 않는다. 설정을 잊지 않도록 꺼져 있을 때는 시작 로그에 경고를 남긴다.
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
from datetime import timedelta

from flask import jsonify, request, session

logger = logging.getLogger(__name__)

PASSWORD_ENV = "APP_PASSWORD"
SECRET_ENV = "APP_SECRET_KEY"
STATE_ENV = "APP_STATE_FILE"

# 로그인에 필요한 대화만 세션 없이 열어둔다. 나머지는 전부 잠금 대상이다.
# 프론트엔드 정적 파일은 nginx가 직접 서빙하므로 여기에 걸리지 않는다.
PUBLIC_PATHS = {"/api/auth/session", "/api/auth/challenge", "/api/auth/login"}

# nonce는 한 번만 쓸 수 있고, 이 시간 안에 쓰지 않으면 버린다.
NONCE_TTL_SECONDS = 60
MAX_NONCES = 4096

# 이만큼 틀리면 잠긴다. 이후에는 실패를 세지 않고 잠금만 반복해서 건다.
MAX_ATTEMPTS = 5
# 첫 잠금은 10분. 다음부터는 2배씩 늘려 최대 하루까지는다.
BASE_LOCKOUT_MINUTES = 10
MAX_LOCKOUT_MINUTES = 24 * 60

_state_lock = threading.Lock()


def is_enabled():
    return bool(os.getenv(PASSWORD_ENV, "").strip())


def _state_path():
    return os.getenv(STATE_ENV, "/tmp/ls-grabber-auth.json")


@contextmanager
def _locked_state():
    """시도 횟수와 nonce를 담은 상태 파일을 단독으로 연다.

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
            yield state
            payload = json.dumps(state).encode("utf-8")
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _client_key():
    # nginx가 같은 브라우저를 프록시하므로 remote_addr 만으로는 요청자를 구분할 수
    # 없다. 원본 IP가 있으면 그걸 보고, 없으면 그냥 전역 잠금을 건다.
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or request.remote_addr or "unknown"


def _lockout_minutes(lockouts):
    """잠금 횟수가 늘어갈수록 기다리는 시간이 2배씩 늘어난다."""
    minutes = BASE_LOCKOUT_MINUTES * (2 ** max(lockouts - 1, 0))
    return min(minutes, MAX_LOCKOUT_MINUTES)


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


def _expected_proof(nonce):
    """서버가 직접 계산하는 정답. 브라우저와 똑같은 식을 쓴다."""
    password = os.getenv(PASSWORD_ENV, "")
    return hashlib.sha256(f"{password}:{nonce}".encode("utf-8")).hexdigest()


def install(app):
    """앱에 세션 기반 잠금을 건다. app.py 에서 한 번만 호출한다."""
    app.config.update(
        SECRET_KEY=os.getenv(SECRET_ENV) or "insecure-dev-secret",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # 새로고침마다 다시 치지 않도록 한 달 정도 기억한다.
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    )

    @app.before_request
    def _require_password():
        if not is_enabled() or request.path in PUBLIC_PATHS:
            return None
        if session.get("authed"):
            return None
        return jsonify({"error": "Unauthorized", "auth_required": True}), 401

    @app.route("/api/auth/session", methods=["GET"])
    def auth_session():
        return {"authed": bool(session.get("authed")), "enabled": is_enabled()}

    @app.route("/api/auth/challenge", methods=["GET"])
    def auth_challenge():
        """비밀번호를 담지 않은 일회용 값을 내준다."""
        if not is_enabled():
            return {"enabled": False}
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
        # nonce는 검증成败과 무관하게 한 번만 쓸 수 있다. 틀렸어도 다시 안 된다.
        nonce = body.get("nonce")
        proof = body.get("proof")
        if not _take_nonce(nonce):
            logger.warning("[auth] stale or reused nonce client=%s", key)
            return jsonify({"error": "stale_nonce"}), 400

        # 길이 차이로 비교 시간이 새지 않도록 상수 시간 비교를 쓴다.
        if not isinstance(proof, str) or not secrets.compare_digest(proof, _expected_proof(nonce)):
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