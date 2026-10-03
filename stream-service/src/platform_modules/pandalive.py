import logging
from urllib.parse import urljoin

import requests

from platform_modules.platform_default import PlatformDefault


logger = logging.getLogger(__name__)


class Pandalive(PlatformDefault):
    platform = "PandaliveParser"
    version = "1.0.0"

    api_url = "https://api.pandalive.co.kr/v1/live/play"
    origin = "https://www.pandalive.co.kr"
    headers = {
        "Accept": "*/*",
        "Accept-Language": "ko",
        "Origin": origin,
        "Referer": f"{origin}/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "X-Device-Info": '{"t":"webPc","v":"1.0","ui":0}',
    }
    quality_list = {
        "auto": "auto",
        "360p": "360p",
        "480p": "480p",
        "540p": "480p",
        "720p": "720p",
        "1080p": "1080p",
    }

    def __init__(self):
        super().__init__()
        self.session = requests.Session()

    def get_platform(self):
        return self.platform

    def get_version(self):
        return self.version

    def get_live(self, user_id, quality="auto"):
        super().get_live()
        normalized_quality = self.quality_list.get(quality)
        if not normalized_quality:
            logger.warning("[pandalive] unsupported quality=%s", quality)
            return ""

        live_info = self.__request_live_info(user_id)
        logger.info(
            "[pandalive] live info result=%s message=%s media=%s",
            live_info.get("result"),
            live_info.get("message"),
            live_info.get("media", {}),
        )
        if not live_info.get("result"):
            message = live_info.get("message") or "Live stream is not available."
            error_code = live_info.get("errorData", {}).get("code")
            logger.warning(
                "[pandalive] stream unavailable code=%s message=%s response=%s",
                error_code,
                message,
                live_info,
            )
            if error_code in ("needAdult", "needLogin", "needPw", "needCoin", "needFan"):
                raise PermissionError(message)

            return ""

        if not live_info.get("media", {}).get("isLive"):
            logger.warning("[pandalive] stream not live response=%s", live_info)
            return ""

        playlist_url = self.__select_playlist_url(live_info.get("PlayList", {}), normalized_quality)
        if not playlist_url:
            logger.warning("[pandalive] playlist url not found response=%s", live_info)
            return ""

        if normalized_quality == "auto":
            return playlist_url

        variant_url = self.__get_variant_url_from_master(playlist_url, normalized_quality)
        return variant_url or playlist_url

    def __request_live_info(self, user_id):
        headers = {
            **self.headers,
            "Referer": f"{self.origin}/play/{user_id}",
        }
        response = self.session.post(
            self.api_url,
            headers=headers,
            data={"userId": user_id, "action": "watch"},
            timeout=10,
        )
        try:
            body = response.json()
        except ValueError:
            response.raise_for_status()
            return {}

        if not response.ok and not isinstance(body, dict):
            response.raise_for_status()

        return body

    def __select_playlist_url(self, playlist, quality):
        candidates = []
        for key in ("hls3", "hls2", "hls"):
            candidates.extend(playlist.get(key) or [])

        if not candidates:
            return ""

        for candidate in sorted(candidates, key=lambda item: item.get("sort", 999)):
            candidate_url = candidate.get("url")
            if not candidate_url:
                continue

            if quality == "auto" or self.__candidate_matches_quality(candidate, quality):
                logger.info(
                    "[pandalive] selected playlist quality=%s candidate=%s",
                    quality,
                    candidate,
                )
                return candidate_url

        logger.info("[pandalive] falling back to first playlist candidate=%s", candidates[0])
        return candidates[0].get("url", "")

    def __candidate_matches_quality(self, candidate, quality):
        name = str(candidate.get("name", "")).lower()
        height = quality.removesuffix("p")
        return quality.lower() in name or height in name

    def __get_variant_url_from_master(self, master_m3u8_url, quality):
        headers = {
            **self.headers,
            "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
        }
        response = self.session.get(master_m3u8_url, headers=headers, timeout=10)
        logger.info(
            "[pandalive] master playlist response url=%s status_code=%s",
            master_m3u8_url,
            response.status_code,
        )
        response.raise_for_status()

        lines = [
            line.strip()
            for line in response.text.splitlines()
            if line.strip() and not line.startswith("#EXTM3U")
        ]
        for index, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF"):
                continue

            variant_path = lines[index + 1] if index + 1 < len(lines) else ""
            if not variant_path or variant_path.startswith("#"):
                continue

            if self.__stream_info_matches_quality(line, quality):
                variant_url = urljoin(master_m3u8_url, variant_path)
                logger.info(
                    "[pandalive] selected variant quality=%s stream_info=%s variant_url=%s",
                    quality,
                    line,
                    variant_url,
                )
                return variant_url

        logger.warning("[pandalive] playlist variant not found quality=%s", quality)
        return ""

    def __stream_info_matches_quality(self, stream_info, quality):
        height = quality.removesuffix("p")
        return f'NAME="{quality}' in stream_info or f"x{height}" in stream_info
