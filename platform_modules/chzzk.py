import requests
from platform_modules.platform_default import PlatformDefault
import json


class Chzzk(PlatformDefault):
    platform = "ChzzkParser"
    version = "1.0.0"

    headers = {
        "Origin": "https://chzzk.naver.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
    quality_list = {
        '360p': "sd",
        '540p': "hd",
        '720p': "hd4k",
        '1080p': "original",
        'auto': "auto",
    }
    origin_stream_url = "https://livecloud.pstatic.net"

    def __init__(self):
        super().__init__()

    def get_platform(self):
        return self.platform

    def get_version(self):
        return self.version

    def get_live(self, chzzk_id, quality='540p'):
        super().get_live()
        req = self.__request_stream_info(chzzk_id, quality)
        live_playback_json = json.loads(req["content"]["livePlaybackJson"])
        print("TEST", live_playback_json)
        if quality == 'auto':
            m3u8_url = live_playback_json["media"][1]["path"]
        else:
            quality_jsons = live_playback_json["media"][1]["encodingTrack"]
            selected_json_index = list(map(lambda x: x["encodingTrackId"], quality_jsons)).index(quality)
            if selected_json_index != -1:
                print(quality_jsons[selected_json_index])
                m3u8_url = self.origin_stream_url + quality_jsons[selected_json_index]["p2pPathUrlEncoding"]
            else:
                m3u8_url = ""
        print("m3u8_url", m3u8_url)
        return m3u8_url

    def __request_stream_info(self, chzzk_id, quality='540p'):
        url = f'https://api.chzzk.naver.com/service/v3.2/channels/{chzzk_id}/live-detail'
        print(url, {**self.headers, "Referer": f"https://chzzk.naver.com/live/{chzzk_id}"})
        # form_data = f"bid={soop_id}&type=aid&pwd=&player_type=html5&stream_type=common&quality={self.quality_list[quality]}&mode=landing&from_api=0&is_revive=false"

        response = requests.get(url, headers={**self.headers, "Referer": f"https://chzzk.naver.com/live/{chzzk_id}"})
        return response.json()
