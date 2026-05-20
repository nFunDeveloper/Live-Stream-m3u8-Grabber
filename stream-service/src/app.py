import os
import logging
from flask import Flask, redirect, request, send_from_directory
from urllib.parse import urlparse

from platform_modules.chzzk import Chzzk
from platform_modules.soop import Soop

# 빌드된 React 앱 경로 설정 (app.py 기준 ui/dist)
# Docker 빌드 시 /app/ui/dist 로 복사됨
static_folder_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ui', 'dist')
app = Flask(__name__, static_folder=static_folder_path, static_url_path='/ui')
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

platforms = {
    'soop': Soop(),
    'afreeca': Soop(),  # Assuming Soop can handle Afreeca streams
    'chzzk': Chzzk(),
}

auto_parsing_db = {
    'chzzk.naver.com': ("chzzk", 2),
    'play.sooplive.com': ("soop", 1),
    'play.sooplive.co.kr': ("soop", 1)
}

@app.route("/")
def index():
    return redirect("/ui")

@app.route('/ui')
@app.route('/ui/<path:path>')
def serve_ui(path='index.html'):
    if not os.path.exists(app.static_folder):
        return "Frontend build not found. Please build the UI project first.", 404
    
    # SPA 라우팅 대응: 존재하지 않는 파일 요청 시 index.html 서빙
    target_path = os.path.join(app.static_folder, path)
    if not os.path.isfile(target_path):
        return send_from_directory(app.static_folder, 'index.html')
        
    return send_from_directory(app.static_folder, path)

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
            streamer_id_idx = detected_platform[1]
            if len(path_split) <= streamer_id_idx:
                logger.warning("[grab] invalid URL format path_split=%s", path_split)
                return {"error": "Invalid streamer URL format"}, 400
                
            streamer_id = path_split[streamer_id_idx]
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
        except Exception as e:
            logger.exception("[grab] failed to grab stream")
            return {"error": f"Failed to grab stream: {str(e)}"}, 500

    logger.warning("[grab] unsupported hostname=%s", parsed_url.hostname)
    return {"error": "Unsupported platform or invalid URL"}, 400

@app.route('/<path:platform_name>/<path:streamer_id>/<path:quality>', methods=['GET'])
def get_live(platform_name, streamer_id, quality='540p'):
    return redirect(get_m3u8(platform_name, streamer_id, quality), code=302)


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
        path_split = parsed_url.path.split('/')
        detected_platform = auto_parsing_db[parsed_url.hostname]

        m3u8_url = get_m3u8(detected_platform[0], path_split[detected_platform[1]], quality)
        if not m3u8_url:
            return "Live stream not found", 404

        return redirect(m3u8_url, code=302)

    return "알 수 없는 오류", 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9999)
