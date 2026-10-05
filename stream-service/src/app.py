import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify, redirect, request, stream_with_context
from urllib.parse import parse_qs, urlparse

from platform_modules.chzzk import Chzzk
from platform_modules.cime import Cime
from platform_modules.pandalive import Pandalive
from platform_modules.popkon import Popkon
from platform_modules.soop import Soop
from platform_health import get_health
import auth_guard
from auth_guard import install as install_auth_guard
from stream_proxy import (
    ProxyError,
    ProxyForbidden,
    build_proxy_url,
    is_probably_playlist,
    open_stream,
    read_playlist,
)

app = Flask(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

# 비밀번호로 잠근 뒤에야 어떤 API든 닿을 수 있게 한다.
install_auth_guard(app)
if not auth_guard.is_enabled():
    logger.warning(
        "[auth] APP_PASSWORD 가 비어 있어 비밀번호 잠금이 꺼져 있다."
        " 외부에 노출되는 곳이라면 반드시 설정할 것"
    )

platforms = {
    'soop': Soop(),
    'afreeca': Soop(),  # Assuming Soop can handle Afreeca streams
    'chzzk': Chzzk(),
    'cime': Cime(),
    'pandalive': Pandalive(),
    'popkon': Popkon(),
}

auto_parsing_db = {
    'chzzk.naver.com': ("chzzk", 2),
    'm.chzzk.naver.com': ("chzzk", 2),
    'ci.me': ("cime", 1),
    'www.pandalive.co.kr': ("pandalive", 2),
    'm.pandalive.co.kr': ("pandalive", 2),
    'pandalive.co.kr': ("pandalive", 2),
    'www.popkontv.com': ("popkon", None),
    'm.popkontv.com': ("popkon", None),
    'popkontv.com': ("popkon", None),
    'play.sooplive.com': ("soop", 1),
    'play.sooplive.co.kr': ("soop", 1)
}


def no_store(payload):
    """m3u8 URL에는 만료 토큰이 들어 있어 브라우저가 캐시하면 재시도가 무의미해진다."""
    response = jsonify(payload)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response


@app.route('/api/grab', methods=['GET'])
def grab_api():
    url = request.args.get('url')
    quality = request.args.get('quality', 'auto')
    logger.info("[grab] request url=%s quality=%s", url, quality)
    if not url:
        return {"error": "URL parameter is required"}, 400

    parsed_url = urlparse(url)
    logger.info(
        "[grab] parsed_url scheme=%s hostname=%s path=%s",
        parsed_url.scheme,
        parsed_url.hostname,
        parsed_url.path,
    )
    if parsed_url.hostname in auto_parsing_db:
        path_split = parsed_url.path.split('/')
        detected_platform = auto_parsing_db[parsed_url.hostname]
        platform_name = detected_platform[0]
        logger.info(
            "[grab] detected platform=%s path_split=%s streamer_id_index=%s",
            platform_name,
            path_split,
            detected_platform[1],
        )

        # URL 경로 검증
        try:
            streamer_id = _extract_streamer_id(parsed_url, detected_platform)
            if not streamer_id:
                logger.warning("[grab] invalid URL format path_split=%s", path_split)
                return {"error": "Invalid streamer URL format"}, 400

            logger.info("[grab] streamer_id=%s", streamer_id)
            info = get_stream_info(platform_name, streamer_id, quality)

            if not info or not info.get("m3u8_url"):
                logger.warning(
                    "[grab] m3u8 not found platform=%s streamer_id=%s quality=%s",
                    platform_name,
                    streamer_id,
                    quality,
                )
                return {"error": "Live stream not found or quality unsupported"}, 404

            logger.info("[grab] success m3u8_url=%s", info["m3u8_url"])
            return no_store({
                "m3u8_url": info["m3u8_url"],
                # 앱 안에서 재생할 때만 쓰는 프록시 경로. 복사/표시는 원본을 쓴다.
                "playback_url": build_proxy_url(info["m3u8_url"]),
                "platform": platform_name,
                "streamer_id": streamer_id,
                "quality": quality,
                "title": info.get("title") or "",
                "streamer_name": info.get("streamer_name") or "",
                "category": info.get("category") or "",
                "started_at": info.get("started_at") or "",
                "viewers": info.get("viewers"),
                "thumbnail": info.get("thumbnail") or "",
            })
        except ValueError as e:
            logger.warning("[grab] invalid request: %s", e)
            return {"error": str(e)}, 400
        except PermissionError as e:
            logger.warning("[grab] stream access denied: %s", e)
            return {"error": str(e)}, 403
        except Exception as e:
            logger.exception("[grab] failed to grab stream")
            return {"error": f"Failed to grab stream: {str(e)}"}, 500

    logger.warning("[grab] unsupported hostname=%s", parsed_url.hostname)
    return {"error": "Unsupported platform or invalid URL"}, 400


def _segment_content_type(target):
    """세그먼트 응답에 쓸 Content-Type. 확장자를 기준으로 결정한다."""
    path = urlparse(target).path.lower()
    if path.endswith('.ts'):
        return 'video/mp2t'
    if path.endswith('.m4s') or path.endswith('.m4v') or path.endswith('.mp4'):
        return 'video/mp4'
    return 'application/octet-stream'


@app.route('/api/stream', methods=['GET'])
def stream_proxy_api():
    """CORS에 막힌 플랫폼의 플레이리스트/세그먼트를 대신 받아준다.

    복사 버튼이 주는 원본 URL은 그대로 두고, 앱 안에서 재생할 때만 이 경로를 쓴다.
    """
    target = request.args.get('u')
    if not target:
        return {"error": "u parameter is required"}, 400

    try:
        upstream = open_stream(target, range_header=request.headers.get('Range'))
    except ProxyForbidden:
        logger.warning("[stream] rejected host url=%s", target)
        return {"error": "Host is not allowed"}, 403
    except ProxyError as e:
        logger.warning("[stream] upstream failed url=%s error=%s", target, e)
        return {"error": "Upstream request failed"}, 502

    content_type = upstream.headers.get('Content-Type', '')
    # 치지직 동시시청 초과(6번째)는 마스터 요청 자체를 403으로 거절한다.
    # 그대로 두면 hls.js가 치명적이지 않은 오류로 삼켜 재시도 UI가 뜨지 않는다.
    if upstream.status_code in (401, 403, 429):
        upstream.close()
        logger.warning("[stream] upstream rejected status=%s url=%s", upstream.status_code, target)
        return {"error": "Concurrent stream limit reached or access denied"}, 502

    try:
        if not is_probably_playlist(
            target, content_type, upstream.headers.get('Content-Length')
        ):
            # 세그먼트는 재작성할 게 없으므로 그대로 흘려보낸다.
            # SOOP은 세그먼트에도 m3u8 타입을 주므로 그대로 넘기면 브라우저가
            # 재생목록으로 오해하므로 실제 확장자에 맞는 타입으로 바꿔준다.
            def generate():
                try:
                    yield from upstream.iter_content(chunk_size=64 * 1024)
                finally:
                    upstream.close()

            response = Response(
                stream_with_context(generate()),
                status=upstream.status_code,
                content_type=_segment_content_type(target),
            )
            length = upstream.headers.get('Content-Length')
            if length:
                response.headers['Content-Length'] = length
            content_range = upstream.headers.get('Content-Range')
            if content_range:
                response.headers['Content-Range'] = content_range
            return response

        playlist = read_playlist(upstream, target)
        upstream.close()
        return Response(playlist, content_type='application/vnd.apple.mpegurl')
    except ProxyError as e:
        upstream.close()
        logger.warning("[stream] playlist read failed url=%s error=%s", target, e)
        return {"error": str(e)}, 502
    except Exception:
        upstream.close()
        logger.exception("[stream] failed to proxy url=%s", target)
        return {"error": "Failed to proxy stream"}, 500


@app.route('/api/platforms/health', methods=['GET'])
def platforms_health_api():
    """지금은 실제로 스트림을 받을 수 있는 플랫폼만 골라낸다."""
    results = get_health(platforms, force=request.args.get('force') == '1')
    return no_store({
        'platforms': [
            {'platform': name, 'ok': state['ok'], 'reason': state['reason']}
            for name, state in results.items()
        ]
    })


@app.route('/api/search', methods=['GET'])
def search_api():
    query = (request.args.get('q') or '').strip()
    if not query:
        return {"results": []}

    # search_lives를 구현한 플랫폼만 병렬로 조회한다
    searchable = [
        (name, platform)
        for name, platform in platforms.items()
        if hasattr(platform, 'search_lives')
    ]
    logger.info("[search] query=%s platforms=%s", query, [name for name, _ in searchable])

    def run_search(name, platform):
        try:
            return platform.search_lives(query, limit=8)
        except Exception:
            logger.exception("[search] platform=%s query=%s failed", name, query)
            return []

    results = []
    with ThreadPoolExecutor(max_workers=max(len(searchable), 1)) as pool:
        futures = [pool.submit(run_search, name, platform) for name, platform in searchable]
        for future in as_completed(futures):
            results.extend(future.result())

    # SOOP는 soop 과 afreeca 두 별칭으로 등록돼 있어 같은 방송이 두 번 들어온다
    deduped = {}
    for item in results:
        deduped.setdefault((item.get('platform'), item.get('streamer_id')), item)
    results = list(deduped.values())

    results.sort(key=lambda item: item.get('viewers') or 0, reverse=True)
    return {"results": results}


@app.route('/api/status', methods=['POST'])
def status_api():
    body = request.get_json(silent=True) or {}
    entries = [
        (entry.get('platform') or '', entry.get('streamer_id') or '')
        for entry in (body.get('entries') or [])
        if entry.get('platform') and entry.get('streamer_id')
    ]
    entries = list(dict.fromkeys(entries))  # 중복 제거

    def run_check(platform_name, streamer_id):
        platform = platforms.get(platform_name)
        if platform is None or not hasattr(platform, 'check_status'):
            return {'platform': platform_name, 'streamer_id': streamer_id, 'is_live': None}
        try:
            status = platform.check_status(streamer_id)
            return {'platform': platform_name, 'streamer_id': streamer_id, **status}
        except Exception:
            logger.exception("[status] check failed platform=%s streamer=%s", platform_name, streamer_id)
            return {'platform': platform_name, 'streamer_id': streamer_id, 'is_live': None}

    statuses = []
    with ThreadPoolExecutor(max_workers=min(max(len(entries), 1), 8)) as pool:
        futures = [pool.submit(run_check, platform_name, streamer_id) for platform_name, streamer_id in entries]
        for future in as_completed(futures):
            statuses.append(future.result())

    return {"statuses": statuses}


@app.route('/<path:platform_name>/<path:streamer_id>/<path:quality>', methods=['GET'])
def get_live(platform_name, streamer_id, quality='540p'):
    try:
        m3u8_url = get_m3u8(platform_name, streamer_id, quality)
    except PermissionError as e:
        logger.warning("[get_live] stream access denied: %s", e)
        return {"error": str(e)}, 403
    except ValueError as e:
        logger.warning("[get_live] invalid request: %s", e)
        return {"error": str(e)}, 400
    except Exception:
        logger.exception("[get_live] failed to grab stream")
        return {"error": "Failed to grab stream"}, 500

    if not m3u8_url:
        logger.warning(
            "[get_live] m3u8 not found platform=%s streamer_id=%s quality=%s",
            platform_name,
            streamer_id,
            quality,
        )
        return {"error": "Live stream not found or quality unsupported"}, 404

    return redirect(m3u8_url, code=302)


def get_stream_info(platform_name, streamer_id, quality='540p'):
    if platform_name not in platforms:
        logger.warning("[get_stream_info] unknown platform=%s", platform_name)
        return None

    platform = platforms[platform_name]
    logger.info(
        "[get_stream_info] platform=%s streamer_id=%s quality=%s",
        platform_name,
        streamer_id,
        quality,
    )
    return platform.get_live(streamer_id, quality)


def get_m3u8(platform_name, streamer_id, quality='540p'):
    info = get_stream_info(platform_name, streamer_id, quality)
    return (info or {}).get("m3u8_url") or ""


def _extract_streamer_id(parsed_url, detected_platform):
    platform_name, path_index = detected_platform
    if platform_name == "popkon":
        query = parse_qs(parsed_url.query)
        cast_id = (query.get("castId") or [""])[0]
        partner_code = (query.get("partnerCode") or [""])[0]
        if cast_id and partner_code:
            return f"{cast_id}|{partner_code}"

        return ""

    path_split = parsed_url.path.split('/')
    if path_index is None or len(path_split) <= path_index:
        return ""

    return path_split[path_index]


@app.route('/detect/<path:quality>', methods=['GET'])
def auto_url_parser(quality):
    params = request.args
    url = params.get('url')
    if not url:
        return "URL parameter is required", 400
    if not quality:
        return "Quality parameter(q) is required", 400

    parsed_url = urlparse(url)
    if parsed_url.hostname in auto_parsing_db:
        detected_platform = auto_parsing_db[parsed_url.hostname]
        streamer_id = _extract_streamer_id(parsed_url, detected_platform)
        if not streamer_id:
            return "Invalid streamer URL format", 400

        try:
            m3u8_url = get_m3u8(detected_platform[0], streamer_id, quality)
        except PermissionError as e:
            logger.warning("[detect] stream access denied: %s", e)
            return {"error": str(e)}, 403
        except ValueError as e:
            logger.warning("[detect] invalid request: %s", e)
            return {"error": str(e)}, 400
        except Exception:
            logger.exception("[detect] failed to grab stream")
            return {"error": "Failed to grab stream"}, 500
        if not m3u8_url:
            return "Live stream not found", 404

        return redirect(m3u8_url, code=302)

    return "알 수 없는 오류", 400


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
