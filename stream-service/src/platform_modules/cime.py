import logging

import requests

from platform_modules.platform_default import PlatformDefault


logger = logging.getLogger(__name__)


class Cime(PlatformDefault):
    platform = "CimeParser"
    version = "1.0.0"

    headers = {
        "Accept": "application/json",
        "Referer": "https://ci.me/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
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

    def get_platform(self):
        return self.platform

    def get_version(self):
        return self.version

    def get_live(self, channel_slug, quality="auto"):
        super().get_live()
        normalized_quality = self.quality_list.get(quality)
        if not normalized_quality:
            logger.warning("[cime] unsupported quality=%s", quality)
            return ""

        channel_slug = channel_slug.lstrip("@")
        live_info = self.__request_live_info(channel_slug)
        logger.info("[cime] live info=%s", live_info)

        if live_info.get("code") != 200 or "data" not in live_info:
            logger.warning("[cime] live info not found response=%s", live_info)
            return ""

        playback_url = (
            live_info["data"].get("playbackUrl")
            or live_info["data"].get("playback", {}).get("url")
        )
        if not playback_url:
            logger.warning("[cime] playback url not found response=%s", live_info)
            return ""

        if normalized_quality == "auto":
            return playback_url

        headers = {
            **self.headers,
            "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
            "Origin": "https://ci.me",
        }
        variant_url = self.get_variant_url_from_master(playback_url, normalized_quality, headers)
        return variant_url or playback_url

    def __request_live_info(self, channel_slug):
        url = f"https://ci.me/api/app/channels/{channel_slug}/live"
        headers = {**self.headers, "Referer": f"https://ci.me/@{channel_slug}/live"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
