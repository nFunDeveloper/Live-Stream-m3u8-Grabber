import requests
from platform_modules.platform_default import PlatformDefault
import logging


logger = logging.getLogger(__name__)


class Soop(PlatformDefault):
    platform = "SoopParser"
    version = "1.0.0"

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    quality_list = {
        '360p': "sd",
        '540p': "hd",
        '480p': "hd",
        '720p': "hd4k",
        '1080p': "original",
        'auto': "original",
    }

    def __init__(self):
        super().__init__()

    def get_platform(self):
        return self.platform

    def get_version(self):
        return self.version

    def get_live(self, soop_id, quality='540p'):
        super().get_live()
        selected_quality = self.quality_list.get(quality)
        if not selected_quality:
            logger.warning("[soop] unsupported quality=%s", quality)
            return ""

        broadcast_info = self.__get_soop_broadcast_info(soop_id, self.headers)
        logger.info("[soop] broadcast info=%s", broadcast_info)

        if broadcast_info.get("result") != 1 or "data" not in broadcast_info:
            logger.warning("[soop] live broadcast not found response=%s", broadcast_info)
            return ""

        broad_key = broadcast_info["data"]["origianl_broad_no"]
        auth_info = self.__request_soop_auth_info(soop_id, selected_quality, self.headers)
        logger.info("[soop] auth info=%s", auth_info)

        auth_key = auth_info.get("CHANNEL", {}).get("AID")
        if not auth_key:
            logger.warning("[soop] auth key not found response=%s", auth_info)
            return ""

        broad_url = self.__get_soop_broad_url(broad_key, selected_quality)
        logger.info("[soop] broad url=%s", broad_url)

        if broad_url.get("result") != "1" or "view_url" not in broad_url:
            logger.warning("[soop] stream assign failed response=%s", broad_url)
            return ""

        m3u8_url = broad_url["view_url"] + f"?aid={auth_key}"
        logger.info("[soop] m3u8_url=%s", m3u8_url)
        return m3u8_url

    def __request_soop_auth_info(self, soop_id, quality='hd', headers=headers):
        url = f'https://live.sooplive.co.kr/afreeca/player_live_api.php'  # ?bjid={soop_id}'
        form_data = f"bid={soop_id}&type=aid&pwd=&player_type=html5&stream_type=common&quality={quality}&mode=landing&from_api=0&is_revive=false"
        response = requests.post(url, headers=headers, data=form_data, timeout=10)
        response.raise_for_status()
        return response.json()

    # http://localhost:9999/detect/auto?url=https://play.sooplive.co.kr/jdm1197/285810318
    def __get_soop_broad_url(self, broad_key, quality='hd'):
        # url = f"https://livestream-manager.sooplive.co.kr/broad_stream_assign.html?return_type=gs_cdn_pc_web&use_cors=true&cors_origin_url=play.sooplive.co.kr&broad_key=285810318-common-master-hls&player_mode=landing"
        url = f"https://livestream-manager.sooplive.co.kr/broad_stream_assign.html?return_type=gs_cdn_mobile_web&use_cors=true&cors_origin_url=play.sooplive.com&broad_key={broad_key}-common-{quality}-hls&player_mode=live"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()

    def __get_soop_broadcast_info(self, soop_id, headers=headers):
        url = f"https://api.m.sooplive.co.kr/broad/a/watch?bjid={soop_id}"
        form_data = f"bj_id={soop_id}&agent=web&confirm_adult=false&player_type=webm&mode=live"
        response = requests.post(url, headers=headers, data=form_data, timeout=10)
        response.raise_for_status()
        return response.json()

# https://mobile-web.stream.sooplive.co.kr/live-stm-08/auth_playlist.m3u8?aid=.A32.pxqRXFPZNcY9Qg1.Xv8pB4hrEuT7YLVCVmfYSBn5xJ29hCFQQf3RGcB8-PwKHcGBNKmO0Zco9TTmtdbzzDAsLfbSQ4nnausfxkkhIwfm-rilDripar8vloMc7tVANFFEtpxfmuodGGtYb1j6GGqzlBooc1c2KKSLM1yGtSQSmKKTZnV5v2CkDglItec7G4_ZltKatgZ0ZCTBPRTp
# https://mobile-web.stream.sooplive.co.kr/live-stm-08/auth_playlist.m3u8?aid=.A32.pxqRXFPZNcY9Qg1.Xv8pB4hrEuT7YLVCVmfYSLMZ2a5yrBl4UipMHiQ2q9wLwRoh1NqObIpWFCjZftkt-gY8DTqIvXXxmmZKcY0ZKINTVU2mfLq6K4PxSqTXvspMBL2lyAirnuTS9geUVG4Qx9kCOtAdu01Ym4YwSY1vZy1whvYkVhFnn6QMkbx0GZ0JiaAWJt1Czitn0SvbEJyb
