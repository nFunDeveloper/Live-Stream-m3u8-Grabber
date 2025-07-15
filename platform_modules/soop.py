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
        super().get_live()
        # req = self.__request_soop_auth_info(soop_id, quality, self.headers)
        req = self.__get_soop_broadcast_info(soop_id, self.headers)
        print("Soop API response: {}".format(req))
        # auth_key = req["CHANNEL"]["AID"]
        auth_key = req["data"]["hls_authentication_key"]
        broad_key = req["data"]["origianl_broad_no"]
        broad_url = self.__get_soop_broad_url(broad_key)
        m3u8_url = broad_url["view_url"] + f"?aid={auth_key}"
        # m3u8_url = f"https://mobile-web.stream.sooplive.co.kr/live-stm-07/auth_playlist.m3u8?aid={auth_key}"
        return m3u8_url

    def __request_soop_auth_info(self, soop_id, quality='540p', headers=headers):
        url = f'https://live.sooplive.co.kr/afreeca/player_live_api.php'  # ?bjid={soop_id}'
        form_data = f"bid={soop_id}&type=aid&pwd=&player_type=html5&stream_type=common&quality={self.quality_list[quality]}&mode=landing&from_api=0&is_revive=false"
        response = requests.post(url, headers=headers, data=form_data)
        return response.json()

    # http://localhost:9999/detect/auto?url=https://play.sooplive.co.kr/jdm1197/285810318
    def __get_soop_broad_url(self, broad_key):
        # url = f"https://livestream-manager.sooplive.co.kr/broad_stream_assign.html?return_type=gs_cdn_pc_web&use_cors=true&cors_origin_url=play.sooplive.co.kr&broad_key=285810318-common-master-hls&player_mode=landing"
        url = f"https://livestream-manager.sooplive.co.kr/broad_stream_assign.html?return_type=gs_cdn_mobile_web&use_cors=true&cors_origin_url=play.sooplive.co.kr&broad_key={broad_key}-common-hd-hls&player_mode=live"
        response = requests.get(url)
        print("Soop Broad API response: {}".format(response.text))
        return response.json()

    def __get_soop_broadcast_info(self, soop_id, headers=headers):
        url = f"https://api.m.sooplive.co.kr/broad/a/watch?bjid={soop_id}"
        form_data = f"bj_id={soop_id}&agent=web&confirm_adult=false&player_type=webm&mode=live"
        response = requests.post(url, headers=headers, data=form_data)
        return response.json()

# https://mobile-web.stream.sooplive.co.kr/live-stm-08/auth_playlist.m3u8?aid=.A32.pxqRXFPZNcY9Qg1.Xv8pB4hrEuT7YLVCVmfYSBn5xJ29hCFQQf3RGcB8-PwKHcGBNKmO0Zco9TTmtdbzzDAsLfbSQ4nnausfxkkhIwfm-rilDripar8vloMc7tVANFFEtpxfmuodGGtYb1j6GGqzlBooc1c2KKSLM1yGtSQSmKKTZnV5v2CkDglItec7G4_ZltKatgZ0ZCTBPRTp
# https://mobile-web.stream.sooplive.co.kr/live-stm-08/auth_playlist.m3u8?aid=.A32.pxqRXFPZNcY9Qg1.Xv8pB4hrEuT7YLVCVmfYSLMZ2a5yrBl4UipMHiQ2q9wLwRoh1NqObIpWFCjZftkt-gY8DTqIvXXxmmZKcY0ZKINTVU2mfLq6K4PxSqTXvspMBL2lyAirnuTS9geUVG4Qx9kCOtAdu01Ym4YwSY1vZy1whvYkVhFnn6QMkbx0GZ0JiaAWJt1Czitn0SvbEJyb
