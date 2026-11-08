"""플랫폼이 지금 실제로 스트림을 내줄 수 있는지 확인한다.

라이브 목록 API가 플랫폼마다 제각각이라, "지금 방송 중인 방송 몇 개"를 먼저 구한 뒤
프론트가 정말 타는 경로(플랫폼 모듈 -> SSRF 허용 목록 -> 플레이리스트 읽기)를 그대로
한 번씩 돌려본다. 이 셋 중 하나라도 막히면 그 플랫폼은 지금 쓸 수 없는 것으로 본다.

확인은 매일 06시(APP_TZ, 기본 Asia/Seoul)에 한 번만 돌리고 그 결과를 파일에
보관한다. 새벽에는 라이브 방송이 적어 실패로 돌아올 수 있으므로, 실패한 플랫폼은
성공할 때까지 1시간마다 그 플랫폼만 다시 확인한다. 자정부터 06시 전까지는
전일 결과를 그대로 보여준다.
"""

import fcntl
import json
import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from stream_proxy import (
    ProxyError,
    ProxyForbidden,
    is_allowed_url,
    open_stream,
    read_playlist,
)


logger = logging.getLogger(__name__)

# 매일 이 시각(APP_TZ 기준)에 전체 점검을 한 번 돌린다.
DAILY_CHECK_HOUR = 6
# 전체 점검에서 실패한 플랫폼은 이 간격마다 다시 확인한다(성공할 때까지).
RETRY_INTERVAL_SECONDS = 3600
# 백그라운드 점검 스레드가 잠들어 있는 시간. 요청이 없어도 시각이 바뀌면 점검한다.
CHECK_LOOP_SECONDS = 60

# 점검 결과가 담기는 파일. gunicorn 워커가 같이 쓴다. 기본값은 컨테이너 안 /tmp
# 여서 재시작하면 첫 요청이 다시 점검한다(상태는 하루짜리라 영속이 필요 없다).
STATE_ENV = "HEALTH_STATE_FILE"

# 한 플랫폼이 여러 번 연속 실패해도 다른 방송은 될 수 있다.
# 후보 몇 개를 뽑아 하나라도 성공하면 그 플랫폼은 사용 가능한 것으로 본다.
SAMPLE_SIZE = 3

# 검색 API로 라이브 방송을 찾을 수 있는 플랫폼은 이 키워드 중 하나를 쓴다.
# 어떤 키워드가 방송이 하나도 없는 시기가 있을 수 있어 번갈아 시도한다.
SAMPLE_KEYWORDS = ("게임", "Minecraft", "롤", "BJ")

Pandalive_API = "https://api.pandalive.co.kr"
POPKON_API = "https://prod-api.rink.kr"

Pandalive_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "ko",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://www.pandalive.co.kr",
    "Referer": "https://www.pandalive.co.kr/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
    "X-Device-Info": '{"t":"webPc","v":"1.0","ui":0}',
}

POPKON_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://www.popkontv.com",
    "Referer": "https://www.popkontv.com/live-more",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    ),
}

_state_lock = threading.Lock()
_started = False


def _now():
    """APP_TZ(기본 Asia/Seoul) 기준 현재 시각.

    컨테이너는 기본값이 UTC라서 그대로 쓰면 한국의 06시에 점검되지 않는다.
    auth_guard 와 같은 방식이다(의존성 순환을 피해 자체 복사).
    """
    name = os.getenv("APP_TZ", "Asia/Seoul").strip() or "Asia/Seoul"
    try:
        tz = ZoneInfo(name)
    except Exception:
        logger.warning("[health] 알 수 없는 시간대 %s — Asia/Seoul 로 대신한다", name)
        tz = ZoneInfo("Asia/Seoul")
    return datetime.now(tz)


def _date_str(day):
    return day.strftime("%Y-%m-%d")


def _dawn_epoch(now):
    """now 와 같은 날의 전체 점검 시각(06:00)을 epoch 초로 환산한다."""
    return now.replace(hour=DAILY_CHECK_HOUR, minute=0, second=0, microsecond=0).timestamp()


def _state_path():
    return os.getenv(STATE_ENV, "/tmp/ls-grabber-health.json")


def _load_state():
    """상태 파일을 읽는다. 없거나 깨져 있으면 None."""
    path = _state_path()
    with _state_lock:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return None
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            raw = os.read(fd, 1 << 20)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


def _save_state(state):
    """상태 파일을 덮어쓴다. 워커가 겹쳐도 파일 락 때문에 내용이 섞이지 않는다."""
    path = _state_path()
    payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
    with _state_lock:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _is_fresh(state, now):
    """저장된 결과를 지금 보여줘도 되는지.

    06시 전에는 전일(또는 이른 시각에 만든 당일) 결과를 그대로 쓰고,
    06시가 지나면 오늘 점검 결과만 믿는다.
    """
    if not state or not state.get("date") or not state.get("results"):
        return False
    if now.timestamp() < _dawn_epoch(now):
        yesterday = _date_str(now.date() - timedelta(days=1))
        return state["date"] in {_date_str(now.date()), yesterday}
    return state["date"] == _date_str(now.date())


def _retry_due(state, now):
    """오늘 점검에서 실패한 플랫폼이 있으면 1시간마다 다시 확인한다.

    자정~06시는 전일 결과만 보여주는 시간이라 재시도하지 않는다.
    """
    if now.timestamp() < _dawn_epoch(now):
        return False
    if not any(not result.get("ok") for result in state["results"].values()):
        return False
    retried_at = state.get("retried_at") or 0
    return now.timestamp() - retried_at >= RETRY_INTERVAL_SECONDS


def _ordered(results, names):
    """응답은 항상 등록 순서로. 아직 점검하지 못한 플랫폼은 사유를 채운다."""
    return {
        name: results.get(name, {"ok": False, "reason": "확인하지 못했습니다"})
        for name in names
    }


def _probe_names(names, platforms):
    """주어진 플랫폼 이름들을 병렬로 실제로 받아본다."""
    results = {}
    with ThreadPoolExecutor(max_workers=max(len(names), 1)) as pool:
        futures = {pool.submit(_probe_platform, name, platforms[name]): name for name in names}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def get_health(platforms, force=False):
    """플랫폼별 사용 가능 여부를 돌려준다.

    매일 06시에 전체를 한 번 점검하고, 실패한 플랫폼은 성공할 때까지 1시간마다
    다시 확인한다. 그 사이에는 저장된 결과를 네트워크 없이 돌려준다.
    `force=True`는 저장본을 무시하고 전체를 다시 점검한다(라우트의 ?force=1).
    """
    names = [name for name in platforms if name != "afreeca"]  # SOOP 별칭이라 같은 플랫폼이다
    now = _now()
    state = _load_state()

    if not force and _is_fresh(state, now):
        if _retry_due(state, now):
            return _retry_failed(state, names, platforms, now)
        return _ordered(state["results"], names)

    results = _probe_names(names, platforms)
    _save_state({
        "date": _date_str(now.date()),
        "retried_at": now.timestamp(),
        "results": results,
    })
    logger.info(
        "[health] 전체 점검 완료 date=%s ok=%s",
        _date_str(now.date()), [n for n, r in results.items() if r.get("ok")],
    )
    return _ordered(results, names)


def _retry_failed(state, names, platforms, now):
    """실패한 플랫폼만 다시 점검해 저장된 결과와 합친다."""
    failed = [name for name in names if not state["results"].get(name, {}).get("ok")]
    if not failed:
        return _ordered(state["results"], names)
    logger.info("[health] 실패 플랫폼 재시도 %s", failed)
    retried = _probe_names(failed, platforms)
    merged = dict(state["results"])
    merged.update(retried)
    _save_state({
        "date": state["date"],
        "retried_at": now.timestamp(),
        "results": merged,
    })
    return _ordered(merged, names)


def start_daily_check(platforms):
    """백그라운드에서 매일 점검을 돌린다. app.py 가 platforms 를 정의한 뒤 한 번 부른다."""
    global _started
    if _started:
        return
    _started = True
    threading.Thread(
        target=_check_loop, args=(platforms,), name="health-check", daemon=True,
    ).start()


def _check_loop(platforms):
    """60초마다 시각을 확인한다.

    06시가 지나면 전체 점검을 돌리고, 그 뒤로는 1시간마다 실패 플랫폼만 다시 본다.
    워커마다 한 스레드씩 돌지만 상태 파일로 결과를 공유한다.
    """
    while True:
        time.sleep(CHECK_LOOP_SECONDS)
        try:
            get_health(platforms)
        except Exception:
            logger.exception("[health] 자동 점검 중 오류")


def _probe_platform(name, platform):
    try:
        candidates = _sample_streamers(name, platform)
    except Exception:
        logger.exception("[health] sampling failed platform=%s", name)
        return {"ok": False, "reason": "라이브 방송 목록을 가져오지 못했습니다"}

    if not candidates:
        return {"ok": False, "reason": "지금 방송 중인 방송이 없습니다"}

    last_reason = "스트림을 재생할 수 없습니다"
    for streamer_id in candidates:
        reason = _probe_stream(platform, streamer_id)
        if reason is None:
            logger.info("[health] platform=%s ok streamer=%s", name, streamer_id)
            return {"ok": True, "reason": ""}
        last_reason = reason

    logger.warning("[health] platform=%s unavailable reason=%s", name, last_reason)
    return {"ok": False, "reason": last_reason}


def _probe_stream(platform, streamer_id):
    """프론트와 똑같은 경로로 스트림을 한 번 받아본다. 문제가 없으면 None."""
    try:
        info = platform.get_live(streamer_id, "auto") or {}
    except PermissionError:
        # 성인 인증 방송은 열람 자체가 막힌다. 플랫폼 문제로 세면 안 된다.
        return "시청 제한이 걸린 방송입니다"
    except Exception:
        logger.warning("[health] get_live failed streamer=%s", streamer_id, exc_info=True)
        return "방송 정보를 가져오지 못했습니다"

    url = info.get("m3u8_url")
    if not url:
        return "라이브 스트림이 나오지 않습니다"

    # 허용 목록에 없으면 브라우저에서는 CORS로 막히므로 재생되지 않는다
    if not is_allowed_url(url):
        return "스트림 호스트가 차단되어 있습니다"

    try:
        upstream = open_stream(url)
        try:
            playlist = read_playlist(upstream, url)
        finally:
            upstream.close()
    except ProxyForbidden:
        return "스트림 호스트가 차단되어 있습니다"
    except ProxyError as error:
        # 서명된 URL이 그대로 들어 있으므로 사용자에게 보여줄 문구로는 남기지 않는다
        logger.warning("[health] stream fetch failed url=%s error=%s", url, error)
        return "스트림을 받지 못했습니다"
    except Exception:
        logger.warning("[health] playlist read failed url=%s", url, exc_info=True)
        return "스트림을 받지 못했습니다"

    # master에는 #EXT-X-STREAM-INF, media에는 #EXTINF가 있다. 어느 쪽이든
    # 프록시로 다시 쓰인 경로가 있어야 브라우저가 따라갈 수 있다.
    if "/api/stream?u=" not in playlist:
        return "재생목록 내용이 올바르지 않습니다"
    if "#EXT-X-STREAM-INF" not in playlist and "#EXTINF" not in playlist:
        return "재생목록 내용이 올바르지 않습니다"
    return None


def _sample_streamers(name, platform):
    if name == "pandalive":
        return _sample_pandalive()
    if name == "popkon":
        return _sample_popkon()
    if hasattr(platform, "search_lives"):
        return _sample_by_search(platform)
    return []


def _sample_by_search(platform):
    """치지직/SOOP/ci.me — 검색 API는 방송 중인 것만 돌려준다."""
    for keyword in random.sample(SAMPLE_KEYWORDS, len(SAMPLE_KEYWORDS)):
        try:
            results = platform.search_lives(keyword, limit=8) or []
        except Exception:
            logger.warning("[health] search failed keyword=%s", keyword, exc_info=True)
            continue

        ids = [item["streamer_id"] for item in results if item.get("streamer_id")]
        if ids:
            return random.sample(ids, min(SAMPLE_SIZE, len(ids)))
    return []


def _sample_pandalive():
    response = requests.post(
        f"{Pandalive_API}/v1/live/index",
        headers=Pandalive_HEADERS,
        data={
            "sortType": "hot",
            "orderBy": "hot",
            "onlyNewBj": "N",
            "onlyRealTimeYN": "Y",
            "page": 1,
            "viewerType": "all",
        },
        timeout=6,
    )
    response.raise_for_status()
    entries = response.json().get("list") or []

    ids = [e.get("userId") for e in entries if e.get("isLive") and e.get("userId")]
    if not ids:
        # 목록이 비었으면 랜덤 방송 하나를 직접 받는 API로 한 번 더 시도한다
        rand = requests.get(
            f"{Pandalive_API}/v1/live/getMediaRand",
            headers=Pandalive_HEADERS,
            timeout=6,
        )
        rand.raise_for_status()
        media_id = (rand.json() or {}).get("mediaUserId")
        ids = [media_id] if media_id else []

    return random.sample(ids, min(SAMPLE_SIZE, len(ids)))


def _sample_popkon():
    response = requests.post(
        f"{POPKON_API}/broadcast/v3.1/livelist",
        headers={
            **POPKON_HEADERS,
            "ClientKey": _popkon_client_key(),
        },
        json={
            "castListTarget": 0,
            "main": True,
            "pageNum": 1,
            "pageSize": 30,
            "partnerCode": "P-00001",
            "signId": "",
            "sortType": 2,
            "chrFanPchrgBrdcExpyn": True,
        },
        timeout=6,
    )
    response.raise_for_status()
    entries = (response.json().get("data") or {}).get("list") or []

    # 성인/비공개 방송은 인증 없이 열리지 않아 검사 대상으로 삼지 않는다
    keys = [
        f"{item['signId']}|{item['partnerCode']}"
        for item in entries
        if item.get("signId") and item.get("partnerCode")
        and str(item.get("isAdult", "0")) == "0"
        and str(item.get("isPrivate", "0")) == "0"
    ]
    return random.sample(keys, min(SAMPLE_SIZE, len(keys)))


def _popkon_client_key():
    # 코드에 박힌 기본값과 같고, 배포 환경에서는 환경변수로 덮어쓴다
    return os.getenv(
        "POPKON_CLIENT_KEY",
        "Client FpAhe6mh8Qtz116OENBmRddbYVirNKasktdXQiuHfm88zRaFydTsFy63tzkdZY0u",
    )