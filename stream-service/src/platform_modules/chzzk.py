import requests
from platform_modules.platform_default import PlatformDefault
import json
import logging
import os
from urllib.parse import urljoin


logger = logging.getLogger(__name__)


class Chzzk(PlatformDefault):
    platform = "ChzzkParser"
    version = "1.0.0"

    headers = {
        "Origin": "https://chzzk.naver.com",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    }
    quality_list = {
        'auto': "auto",
        '144p': "144p",
        '360p': "360p",
        '480p': "480p",
        '540p': "480p",
        '720p': "720p",
        '1080p': "1080p",
        '1440p': "1440p",
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
        self.__log_step("start", {"chzzk_id": chzzk_id, "quality": quality})
        req = self.__request_stream_info(chzzk_id, quality)
        self.__log_step("live-detail json response", req)

        if "content" not in req or "livePlaybackJson" not in req["content"]:
            self.__log_step("missing livePlaybackJson", req)
            return ""

        live_playback_json = json.loads(req["content"]["livePlaybackJson"])
        self.__log_step("parsed livePlaybackJson", live_playback_json)

        media = live_playback_json.get("media", [])
        self.__log_step("media candidates", media)
        if len(media) < 2:
            self.__log_step("media candidate missing", {"media_count": len(media)})
            return ""

        normalized_quality = self.quality_list.get(quality)
        if not normalized_quality:
            self.__log_step("unsupported requested quality", {"quality": quality})
            return ""

        if normalized_quality == 'auto':
            m3u8_url = media[1]["path"]
            self.__log_step("auto quality selected", {"m3u8_url": m3u8_url})
        else:
            master_m3u8_url = media[1]["path"]
            quality_jsons = media[1].get("encodingTrack", [])
            self.__log_step("encoding tracks", quality_jsons)

            selected_track = self.__find_encoding_track(quality_jsons, normalized_quality)
            if not selected_track:
                self.__log_step(
                    "encoding track not found",
                    {
                        "requested_quality": quality,
                        "normalized_quality": normalized_quality,
                        "available_qualities": [
                            track.get("encodingTrackId") for track in quality_jsons
                        ],
                    },
                )
                return ""

            self.__log_step("selected encoding track", selected_track)
            m3u8_url = selected_track.get("path", "")

            if not m3u8_url:
                m3u8_url = self.__get_variant_url_from_master(master_m3u8_url, normalized_quality)

            if not m3u8_url:
                m3u8_url = self.__get_track_url(selected_track)

            if not m3u8_url:
                self.__log_step(
                    "quality URL not found",
                    {
                        "requested_quality": quality,
                        "normalized_quality": normalized_quality,
                    },
                )
                m3u8_url = ""
        self.__log_step("final m3u8_url", {"m3u8_url": m3u8_url})
        return m3u8_url

    def __request_stream_info(self, chzzk_id, quality='540p'):
        url = f'https://api.chzzk.naver.com/service/v3.2/channels/{chzzk_id}/live-detail'
        headers = {**self.headers, "Referer": f"https://chzzk.naver.com/live/{chzzk_id}"}
        self.__log_step("request live-detail", {"url": url, "headers": headers})
        # form_data = f"bid={soop_id}&type=aid&pwd=&player_type=html5&stream_type=common&quality={self.quality_list[quality]}&mode=landing&from_api=0&is_revive=false"

        response = requests.get(url, headers=headers, timeout=10)
        self.__log_step(
            "live-detail http response",
            {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "text": response.text,
            },
        )
        response.raise_for_status()
        return response.json()

    def __find_encoding_track(self, tracks, quality):
        for track in tracks:
            if track.get("encodingTrackId") == quality:
                return track

        return None

    def __get_track_url(self, track):
        if track.get("path"):
            return track["path"]

        if track.get("p2pPathUrlEncoding"):
            return self.origin_stream_url + track["p2pPathUrlEncoding"]

        if track.get("p2pPath"):
            return self.origin_stream_url + track["p2pPath"]

        return ""

    def __get_variant_url_from_master(self, master_m3u8_url, quality):
        response = requests.get(master_m3u8_url, headers=self.headers, timeout=10)
        self.__log_step(
            "master playlist response",
            {
                "url": master_m3u8_url,
                "status_code": response.status_code,
                "text": response.text,
            },
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
            if variant_path.startswith("#"):
                continue

            if variant_path.startswith(f"{quality}/"):
                variant_url = urljoin(master_m3u8_url, variant_path)
                self.__log_step(
                    "selected master playlist variant",
                    {
                        "quality": quality,
                        "stream_info": line,
                        "variant_path": variant_path,
                        "variant_url": variant_url,
                    },
                )
                return variant_url

        self.__log_step("master playlist variant not found", {"quality": quality})
        return ""

    def __log_step(self, step, payload):
        max_chars = int(os.getenv("CHZZK_LOG_RESPONSE_MAX", "50000"))
        try:
            message = json.dumps(payload, ensure_ascii=False, indent=2)
        except TypeError:
            message = str(payload)

        if max_chars > 0 and len(message) > max_chars:
            message = f"{message[:max_chars]}\n...<truncated {len(message) - max_chars} chars>"

        logger.info("[chzzk] %s\n%s", step, message)
