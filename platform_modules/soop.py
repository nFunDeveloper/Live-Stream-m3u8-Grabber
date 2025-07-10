import requests
from platform_modules.platform_default import PlatformDefault

class Soop(PlatformDefault):
    platform = "SoopParser"
    version = "1.0.0"

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    quality_list = {
        '360p': "sd",
        '540p': "hd",
        '720p': "hd4k",
        '1080p': "original",
        'auto': "auto",
    }
    def __init__(self):
        super().__init__()

    def get_platform(self):
        return self.platform

    def get_version(self):
        return self.version

    def get_live(self, soop_id, quality='540p'):
        req = self.__request_soop_auth_info(soop_id, quality, self.headers)
        auth_key = req["CHANNEL"]["AID"]
        m3u8_url = f"https://mobile-web.stream.sooplive.co.kr/live-stm-07/auth_playlist.m3u8?aid={auth_key}"
        return m3u8_url

    def __request_soop_auth_info(self, soop_id, quality='540p', headers=headers):
        url = f'https://live.sooplive.co.kr/afreeca/player_live_api.php?bjid={soop_id}'
        form_data = f"bid={soop_id}&type=aid&pwd=&player_type=html5&stream_type=common&quality={self.quality_list[quality]}&mode=landing&from_api=0&is_revive=false"
        response = requests.post(url, headers=headers, data=form_data)
        return response.json()
