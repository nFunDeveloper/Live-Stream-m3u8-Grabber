import os
import logging
from flask import Flask, redirect, request
from urllib.parse import parse_qs, urlparse

from platform_modules.chzzk import Chzzk
from platform_modules.cime import Cime
from platform_modules.pandalive import Pandalive
from platform_modules.popkon import Popkon
from platform_modules.soop import Soop

app = Flask(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

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
            m3u8_url = get_m3u8(platform_name, streamer_id, quality)
            
            if not m3u8_url:
                logger.warning(
                    "[grab] m3u8 not found platform=%s streamer_id=%s quality=%s",
                    platform_name,
                    streamer_id,
                    quality,
                )
                return {"error": "Live stream not found or quality unsupported"}, 404
                
            logger.info("[grab] success m3u8_url=%s", m3u8_url)
            return {
                "m3u8_url": m3u8_url,
                "platform": platform_name,
                "streamer_id": streamer_id,
                "quality": quality
            }
        except ValueError:
            logger.exception("[grab] unsupported quality quality=%s", quality)
            return {"error": f"Requested quality '{quality}' is not supported by this stream"}, 400
        except PermissionError as e:
            logger.warning("[grab] stream access denied: %s", e)
            return {"error": str(e)}, 403
        except Exception as e:
            logger.exception("[grab] failed to grab stream")
            return {"error": f"Failed to grab stream: {str(e)}"}, 500

    logger.warning("[grab] unsupported hostname=%s", parsed_url.hostname)
    return {"error": "Unsupported platform or invalid URL"}, 400

@app.route('/<path:platform_name>/<path:streamer_id>/<path:quality>', methods=['GET'])
def get_live(platform_name, streamer_id, quality='540p'):
    try:
        m3u8_url = get_m3u8(platform_name, streamer_id, quality)
    except PermissionError as e:
        logger.warning("[get_live] stream access denied: %s", e)
        return {"error": str(e)}, 403
    return redirect(m3u8_url, code=302)


def get_m3u8(platform_name, streamer_id, quality='540p'):
    if platform_name not in platforms:
        logger.warning("[get_m3u8] unknown platform=%s", platform_name)
        return None

    platform = platforms[platform_name]
    logger.info(
        "[get_m3u8] platform=%s streamer_id=%s quality=%s",
        platform_name,
        streamer_id,
        quality,
    )
    m3u8_url = platform.get_live(streamer_id, quality)

    return m3u8_url


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
        if not m3u8_url:
            return "Live stream not found", 404

        return redirect(m3u8_url, code=302)

    return "알 수 없는 오류", 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
