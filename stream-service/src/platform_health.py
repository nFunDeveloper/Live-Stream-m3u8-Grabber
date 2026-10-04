"""플랫폼이 지금 실제로 스트림을 내줄 수 있는지 확인한다.

라이브 목록 API가 플랫폼마다 제각각이라, "지금 방송 중인 방송 몇 개"를 먼저 구한 뒤
프론트가 정말 타는 경로(플랫폼 모듈 -> SSRF 허용 목록 -> 플레이리스트 읽기)를 그대로
한 번씩 돌려본다. 이三者 중 하나라도 막히면 그 플랫폼은 지금 쓸 수 없는 것으로 본다.
"""

import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from stream_proxy import (
    ProxyError,
    ProxyForbidden,
    is_allowed_url,
    open_stream,
    read_playlist,
)


logger = logging.getLogger(__name__)

# 같은 결과를 너무 자주 다시 만들지 않�� 않도록 짧게 캐시한다.
# 플랫폼 상태는 몇 분 안에 바뀌지 않지만, 매 페이지 로드마다 5개 플랫폼을
# 전부 붙잡고 있으면 업���림에 부담이 된다.
CACHE_TTL_SECONDS = 300

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

_cache = {}
_cache_lock = threading.Lock()


def get_health(platforms, force=False):
    """플랫폼별 사용 가능 여부를 돌려준다. 결과는 짧은 시간 동안 캐시된다."""
    if not force:
        with _cache_lock:
            cached = _cache.get("checked_at")
            if cached and time.monotonic() - cached < CACHE_TTL_SECONDS:
                return _cache["results"]

    names = [name for name in platforms if name != "afreeca"]  # SOOP 별칭이라 같은 플랫폼이다
    results = {}
    with ThreadPoolExecutor(max_workers=max(len(names), 1)) as pool:
        futures = {pool.submit(_probe_platform, name, platforms[name]): name for name in names}
        for future in as_completed(futures):
            results[futures[future]] = future.result()

    # 요청 응답 순서가 매번 달라지므로 항상 등록 순서로 정리한다
    ordered = {name: results.get(name, {"ok": False, "reason": "확인하지 못했습니다"}) for name in names}

    with _cache_lock:
        _cache["checked_at"] = time.monotonic()
        _cache["results"] = ordered
    return ordered


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