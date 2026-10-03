import logging
from urllib.parse import urljoin

import requests


logger = logging.getLogger(__name__)


class PlatformDefault:
    platform = "default"
    version = "1.0.0"

    def __init__(self):
        pass

    def get_platform(self):
        return self.platform

    def get_version(self):
        return self.version

    def get_live(self):
        print(f"Get Live Stream Platform: {self.platform}, Version: {self.version}")

    @staticmethod
    def first_of(source, *keys):
        for key in keys:
            value = source.get(key)
            if value:
                return value
        return None

    def get_variant_url_from_master(self, master_m3u8_url, quality, headers=None):
        session = getattr(self, "session", requests)
        response = session.get(
            master_m3u8_url,
            headers=headers or getattr(self, "headers", None),
            timeout=10,
        )
        logger.info(
            "[playlist] master playlist response url=%s status_code=%s",
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

            if self._stream_info_matches_quality(line, quality):
                variant_url = urljoin(
                    master_m3u8_url, self._clean_variant_path(variant_path)
                )
                logger.info(
                    "[playlist] selected variant quality=%s stream_info=%s variant_url=%s",
                    quality,
                    line,
                    variant_url,
                )
                return variant_url

        logger.warning("[playlist] playlist variant not found quality=%s", quality)
        return ""

    @staticmethod
    def _stream_info_matches_quality(stream_info, quality):
        height = quality.removesuffix("p")
        return (
            f'NAME="{quality}' in stream_info
            or f'VIDEO="{quality}' in stream_info
            or f"x{height}" in stream_info
        )

    @staticmethod
    def _clean_variant_path(variant_path):
        # 기본값은 그대로 쓰고, 일부 플랫폼만 응답을 정리한다
        return variant_path
