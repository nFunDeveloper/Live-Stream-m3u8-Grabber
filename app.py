import requests
from flask import Flask, redirect, request
from urllib.parse import urlparse

from platform_modules.chzzk import Chzzk
from platform_modules.soop import Soop

app = Flask(__name__)

platforms = {
    'soop': Soop(),
    'afreeca': Soop(),  # Assuming Soop can handle Afreeca streams
    'chzzk': Chzzk(),
}

auto_parsing_db = {
    'chzzk.naver.com': ("chzzk", 2),
    'play.sooplive.co.kr': ("soop", 1)
}

@app.route("/")
def index():
    return "OK"

@app.route('/<path:platform_name>/<path:streamer_id>/<path:quality>', methods=['GET'])
def get_live(platform_name, streamer_id, quality='540p'):
    return redirect(get_m3u8(platform_name, streamer_id, quality), code=302)


def get_m3u8(platform_name, streamer_id, quality='540p'):
    if platform_name not in platforms:
        return "Platform not supported", 404

    platform = platforms[platform_name]
    m3u8_url = platform.get_live(streamer_id, quality)

    if not m3u8_url:
        return "Live stream not found", 404

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
    print(parsed_url)
    if parsed_url.hostname in auto_parsing_db:
        path_split = parsed_url.path.split('/')
        detected_platform = auto_parsing_db[parsed_url.hostname]

        # print(detected_platform[0], path_split[detected_platform[1]], quality)
        m3u8_url = get_m3u8(detected_platform[0], path_split[detected_platform[1]], quality)

        return redirect(m3u8_url, code=302)

    return "알 수 없는 오류", 400

# http://localhost:9999/detect/1080p?url=https://play.sooplive.co.kr/madaomm/285690872
# http://localhost:9999/detect/1080p?url=https://chzzk.naver.com/live/8fd39bb8de623317de90654718638b10
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9999)
