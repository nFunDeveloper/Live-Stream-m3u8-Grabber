"""앱 전체를 비밀번호 하나로 잠그는 가드.

이 앱은 집 안에서만 쓰는 개인용 도구라 회원가입 같은 것은 없다. 다만 주소만 알면
누구나 방송을 추출할 수 있으므로, 처음 접속했을 때 비밀번호를 한 번 물어본 뒤
서명된 세션 쿠키로 그 기억을 유지한다.

비밀번호는 코드에 넣지 않고 APP_PASSWORD 환경변수로 받는다. 값이 비어 있으면 잠금을
건리지 않는다. 테스트와 로컬 개발에서 환경변수 설정하기를 잊지 않도록, 꺼져 있을
때는 시작 로그에 경고로 남긴다.
"""

import logging
import os
import secrets
import threading
import time
from datetime import timedelta

from flask import jsonify, request, session

logger = logging.getLogger(__name__)

PASSWORD_ENV = "APP_PASSWORD"
SECRET_ENV = "APP_SECRET_KEY"

# 로그인 화면만 세션 없이 열어둔다. 나머지는 전부 잠금 대상이다.
# 프론트엔드 정적 파일은 nginx가 직접 서빙하므로 여기에 걸리지 않는다.
PUBLIC_PATHS = {"/api/auth/session", "/api/auth/login"}

# 실패가 반복되면 같은 주소에서 계속 시도하는 걸 늦춘다.
MAX_ATTEMPTS = 5
LOCK_SECONDS = 60

_attempts = {}
_attempts_lock = threading.Lock()


def is_enabled():
    return bool(os.getenv(PASSWORD_ENV, "").strip())


def _client_key():
    # nginx가 같은 브라우저를 프록시하므로.remote_addr 만으로는 요청자를 구분할
    # 수 없다. 원본 IP가 있으면 그걸 보고, 없으면 그냥 전역 잠금을 건다.
    forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    return forwarded or request.remote_addr or "unknown"


def _lock_remaining(key):
    with _attempts_lock:
        record = _attempts.get(key)
        if not record:
            return 0
        failures, locked_until = record
        if locked_until > time.monotonic():
            return int(locked_until - time.monotonic())
        if failures < MAX_ATTEMPTS:
            return 0
        # 잠금이 끝났으면 기록을 비워 다시 정상적으로 시도하게 한다.
        _attempts.pop(key, None)
        return 0


def _record_failure(key):
    with _attempts_lock:
        failures, locked_until = _attempts.get(key, (0, 0))
        failures += 1
        locked_until = time.monotonic() + LOCK_SECONDS if failures >= MAX_ATTEMPTS else 0
        _attempts[key] = (failures, locked_until)
        return failures, int(locked_until) if locked_until else 0


def _clear_failures(key):
    with _attempts_lock:
        _attempts.pop(key, None)


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

    @app.route("/api/auth/login", methods=["POST"])
    def auth_login():
        expected = os.getenv(PASSWORD_ENV, "").strip()
        key = _client_key()

        remaining = _lock_remaining(key)
        if remaining:
            logger.warning("[auth] locked out client=%s retry_in=%ss", key, remaining)
            return jsonify({
                "error": "too_many_attempts",
                "retry_after": remaining,
            }), 429

        body = request.get_json(silent=True) or {}
        given = body.get("password") or ""
        # 길이 차이로 비교 시간이 새지 않도록 상수 시간 비교를 쓴다.
        if not secrets.compare_digest(str(given), expected):
            failures, retry_after = _record_failure(key)
            logger.warning("[auth] wrong password client=%s failures=%s", key, failures)
            return jsonify({"error": "invalid_password", "retry_after": retry_after}), 401

        _clear_failures(key)
        session.clear()
        session["authed"] = True
        session.permanent = True
        logger.info("[auth] logged in client=%s", key)
        return {"ok": True}

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        session.clear()
        return {"ok": True}