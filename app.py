import requests
from flask import Flask, redirect, request

from platform_modules.soop import Soop

app = Flask(__name__)

platforms = {
    'soop': Soop(),
    'afreeca': Soop(),  # Assuming Soop can handle Afreeca streams
}

@app.route('/<path:platform_name>/<path:streamer_id>/<path:quality>', methods=['GET'])
def get_live(platform_name, streamer_id, quality='540p'):
    if platform_name not in platforms:
        return "Platform not supported", 404
    
    platform = platforms[platform_name]
    m3u8_url = platform.get_live(streamer_id, quality)
    
    if not m3u8_url:
        return "Live stream not found", 404
    
    return redirect(m3u8_url, code=302)

@app.route('/url', methods=['GET'])
def auto_url_parser():
    params = request.args
    url = params.get('url')
    if not url:
        return "URL parameter is required", 400
    return url

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=9999)
