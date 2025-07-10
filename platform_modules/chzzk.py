import requests
from platform_modules.platform_default import PlatformDefault

class Chzzk(PlatformDefault):
    platform = "ChzzkParser"
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

    # def __path_parser(self, soop_id, quality):
    #     req = self.__request_soop_auth_info(soop_id, quality)
    #     auth_key = req["CHANNEL"]["AID"]
    #     m3u8_url = f"https://mobile-web.stream.sooplive.co.kr/live-stm-07/auth_playlist.m3u8?aid={auth_key}"
    #     print(req)
    #     return m3u8_url





# https://livecloud.pstatic.net/chzzk/lip2_kr/cflexnmss2u0002/gbweollm65qgnf5cgu028doge1ub03hbn19o/1080p/hdntl=exp=1752106321~acl=*%2Fgbweollm65qgnf5cgu028doge1ub03hbn19o%2F*~data=hdntl~hmac=0a28988b78c76121fcbaa67c2971305b771ac9b6f941ebed86c28a5bf76d865c/ovyow6qcmqv0nf2cwhrcnet1ub03hbmvyc_chunklist.m3u8?_HLS_msn=4725&_HLS_part=0

# 스트리머정보 가져오기 : https://api.chzzk.naver.com/service/v1/channels/dc7fb0d085cfbbe90e11836e3b85b784
# 방송정보 가져오기 : https://api.chzzk.naver.com/polling/v3.1/channels/dc7fb0d085cfbbe90e11836e3b85b784/live-status?includePlayerRecommendContent=true
