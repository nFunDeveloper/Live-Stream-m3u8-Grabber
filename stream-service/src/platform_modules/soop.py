import logging
import re

import requests
from platform_modules.platform_default import PlatformDefault


logger = logging.getLogger(__name__)

# DNS 실패나 타임아웃 등 전송 계층 오류를 호스트 폴백 기준으로 삼는다
REQUEST_ERROR = requests.RequestException


class Soop(PlatformDefault):
    platform = "SoopParser"
    version = "1.0.0"

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    # master/variant 플레이리스트는 SOOP 플레이어 Referer가 있어야 응답한다
    playlist_headers = {
        'Referer': 'https://play.sooplive.co.kr/',
        'Origin': 'https://play.sooplive.co.kr',
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        ),
    }
    # livestream-manager.sooplive.co.kr 은 CNAME 대상의 A 레코드가 없어 해석에 실패한다.
    # 정식 도메인을 먼저 시도하고 전송 오류가 나면 .com 으로 폴백한다.
    resource_managers = (
        'https://livestream-manager.sooplive.co.kr',
        'https://livestream-manager.sooplive.com',
    )
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
        # master variant 매칭에는 원본 해상도 키(예: 540p)가 필요하고,
        # SOOP 화질명(예: hd)은 broad_key 요청에만 쓴다.
        requested_quality = quality
        selected_quality = self.quality_list.get(quality)
        if not selected_quality:
            logger.warning("[soop] unsupported quality=%s", quality)
            return {"m3u8_url": ""}

        broadcast_info = self.__get_soop_broadcast_info(soop_id, self.headers)
        logger.info("[soop] broadcast info=%s", broadcast_info)

        data = broadcast_info.get("data") or {}
        info = {
            "m3u8_url": "",
            "title": self.first_of(data, "title", "broad_title") or "",
            "streamer_name": self.first_of(data, "user_nick", "nick") or "",
            "category": self.first_of(data, "cate_name", "category_name") or "",
            "started_at": self.first_of(data, "broad_start", "broad_start_date") or "",
            "viewers": data.get("broad_cnt") or data.get("viewer_cnt"),
            "thumbnail": self.first_of(data, "broad_thumb", "broad_thumbnail") or "",
        }

        if broadcast_info.get("result") != 1 or "data" not in broadcast_info:
            logger.warning("[soop] live broadcast not found response=%s", broadcast_info)
            return info

        broad_key = data["origianl_broad_no"]
        broad_url = self.__get_soop_broad_url(broad_key, selected_quality)
        logger.info("[soop] broad url=%s", broad_url)

        if broad_url.get("result") != "1" or "view_url" not in broad_url:
            logger.warning("[soop] stream assign failed response=%s", broad_url)
            return info

        auth_info = self.__request_soop_auth_info(soop_id, selected_quality, self.headers)
        logger.info("[soop] auth info=%s", auth_info)

        auth_key = auth_info.get("CHANNEL", {}).get("AID")
        if not auth_key:
            logger.warning("[soop] auth key not found response=%s", auth_info)
            return info

        # SOOP는 broad_key에 붙인 quality를 무시하고 항상 기본 화질을 내려준다.
        # 실제 화질은 master 플레이리스트의 variant에 있으므로 직접 선택한다.
        if selected_quality != "original":
            master_url = self.__get_soop_master_url(broad_key, auth_key)
            if master_url:
                variant_url = self.get_variant_url_from_master(
                    master_url, requested_quality, self.playlist_headers
                )
                if variant_url:
                    info["m3u8_url"] = variant_url
                    logger.info(
                        "[soop] master variant selected quality=%s m3u8_url=%s",
                        requested_quality,
                        variant_url,
                    )
                    return info

            logger.warning(
                "[soop] variant not found quality=%s, fallback to default stream",
                requested_quality,
            )

        info["m3u8_url"] = broad_url["view_url"] + f"?aid={auth_key}"
        logger.info("[soop] m3u8_url=%s", info["m3u8_url"])
        return info

    def __request_soop_auth_info(self, soop_id, quality='hd', headers=headers):
        url = f'https://live.sooplive.co.kr/afreeca/player_live_api.php'  # ?bjid={soop_id}'
        form_data = f"bid={soop_id}&type=aid&pwd=&player_type=html5&stream_type=common&quality={quality}&mode=landing&from_api=0&is_revive=false"
        response = requests.post(url, headers=headers, data=form_data, timeout=10)
        response.raise_for_status()
        return response.json()

    # http://localhost:9999/detect/auto?url=https://play.sooplive.co.kr/jdm1197/285810318
    def __get_soop_broad_url(self, broad_key, quality='hd'):
        last_error = None
        for host in self.resource_managers:
            url = (
                f"{host}/broad_stream_assign.html"
                f"?return_type=gs_cdn_mobile_web&use_cors=true"
                f"&cors_origin_url=play.sooplive.com"
                f"&broad_key={broad_key}-common-{quality}-hls&player_mode=live"
            )
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                return response.json()
            except REQUEST_ERROR as error:
                # DNS 실패나 타임아웃이면 다음 호스트를 시도한다
                logger.warning("[soop] stream assign host failed host=%s error=%s", host, error)
                last_error = error

        logger.warning("[soop] stream assign failed for all hosts error=%s", last_error)
        return {}

    def __get_soop_master_url(self, broad_key, auth_key):
        """변형(variant)이 담긴 master 플레이리스트 주소를 구한다. 실패하면 빈 문자열."""
        last_error = None
        for host in self.resource_managers:
            url = (
                f"{host}/broad_stream_assign.html"
                f"?return_type=gs_cdn_pc_web&use_cors=true"
                f"&cors_origin_url=play.sooplive.co.kr"
                f"&broad_key={broad_key}-common-master-hls&player_mode=landing"
            )
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                body = response.json()
            except (REQUEST_ERROR, ValueError) as error:
                logger.warning("[soop] master assign host failed host=%s error=%s", host, error)
                last_error = error
                continue

            if body.get("result") != "1" or "view_url" not in body:
                logger.warning("[soop] master assign rejected response=%s", body)
                return ""

            # master 플레이리스트는 aid 쿼리가 있어야 응답한다
            return f"{body['view_url']}?aid={auth_key}"

        logger.warning("[soop] master assign failed for all hosts error=%s", last_error)
        return ""

    @staticmethod
    def _stream_info_matches_quality(stream_info, quality):
        # SOOP master는 NAME=hd/sd 처럼 화질명으로 표기한다.
        # RESOLUTION(예: 960x540)으로 판정한다.
        match = re.search(r"RESOLUTION=(\d+)x(\d+)", stream_info)
        if match:
            return int(match.group(2)) == int(quality.removesuffix("p"))
        return PlatformDefault._stream_info_matches_quality(stream_info, quality)

    @staticmethod
    def _clean_variant_path(variant_path):
        # SOOP master의 variant URL은 끝에 쉼표가 붙어 내려온다
        return variant_path.rstrip(",").strip()

    def __get_soop_broadcast_info(self, soop_id, headers=headers):
        url = f"https://api.m.sooplive.co.kr/broad/a/watch?bjid={soop_id}"
        form_data = f"bj_id={soop_id}&agent=web&confirm_adult=false&player_type=webm&mode=live"
        response = requests.post(url, headers=headers, data=form_data, timeout=10)
        response.raise_for_status()
        return response.json()
