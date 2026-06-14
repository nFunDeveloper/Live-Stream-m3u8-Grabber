import logging
from urllib.parse import urljoin

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

        variant_url = self.__get_variant_url_from_master(playback_url, normalized_quality)
        return variant_url or playback_url

    def __request_live_info(self, channel_slug):
        url = f"https://ci.me/api/app/channels/{channel_slug}/live"
        headers = {**self.headers, "Referer": f"https://ci.me/@{channel_slug}/live"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()

    def __get_variant_url_from_master(self, master_m3u8_url, quality):
        headers = {
            **self.headers,
            "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
            "Origin": "https://ci.me",
        }
        response = requests.get(master_m3u8_url, headers=headers, timeout=10)
        logger.info(
            "[cime] master playlist response url=%s status_code=%s",
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

            if quality == "auto" or self.__stream_info_matches_quality(line, quality):
                variant_url = urljoin(master_m3u8_url, variant_path)
                logger.info(
                    "[cime] selected variant quality=%s stream_info=%s variant_url=%s",
                    quality,
                    line,
                    variant_url,
                )
                return variant_url

        logger.warning("[cime] playlist variant not found quality=%s", quality)
        return ""

    def __stream_info_matches_quality(self, stream_info, quality):
        return (
            f'NAME="{quality}' in stream_info
            or f'VIDEO="{quality}' in stream_info
            or f"x{quality.removesuffix('p')}" in stream_info
        )
