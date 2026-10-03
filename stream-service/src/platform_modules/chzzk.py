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

        content = req.get("content") or {}
        info = self.__build_info(content)

        if "livePlaybackJson" not in content:
            self.__log_step("missing livePlaybackJson", req)
            return info

        live_playback_json = json.loads(content["livePlaybackJson"])
        self.__log_step("parsed livePlaybackJson", live_playback_json)

        media = live_playback_json.get("media", [])
        self.__log_step("media candidates", media)
        if not media:
            self.__log_step("media candidate missing", {"media_count": len(media)})
            return info

        # 일부 방송(스포츠 중계 등)은 media 후보가 1개뿐일 수 있다
        main_media = media[1] if len(media) >= 2 else media[0]

        normalized_quality = self.quality_list.get(quality)
        if not normalized_quality:
            self.__log_step("unsupported requested quality", {"quality": quality})
            return info

        if normalized_quality == 'auto':
            info["m3u8_url"] = main_media["path"]
            self.__log_step("auto quality selected", {"m3u8_url": info["m3u8_url"]})
        else:
            master_m3u8_url = main_media["path"]
            quality_jsons = main_media.get("encodingTrack", [])
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
                return info

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
            info["m3u8_url"] = m3u8_url
        self.__log_step("final m3u8_url", {"m3u8_url": info["m3u8_url"]})
        return info

    @staticmethod
    def __build_info(content):
        channel = content.get("channel") or {}
        # liveImageUrl은 image_{type}.jpg 템플릿으로 내려온다
        thumbnail = (content.get("liveImageUrl") or content.get("defaultThumbnailImageUrl") or "")
        return {
            "m3u8_url": "",
            "title": content.get("liveTitle") or "",
            "streamer_name": channel.get("channelName") or "",
            "category": content.get("liveCategoryValue") or content.get("liveCategory") or "",
            "started_at": content.get("openDate") or "",
            "viewers": content.get("concurrentUserCount"),
            "thumbnail": thumbnail.replace("{type}", "1080"),
        }

    def search_lives(self, keyword, limit=8):
        url = 'https://api.chzzk.naver.com/service/v1/search/lives'
        response = requests.get(
            url,
            headers=self.headers,
            params={'keyword': keyword, 'offset': 0, 'size': limit},
            timeout=6,
        )
        response.raise_for_status()
        data = response.json().get('content', {}).get('data') or []

        results = []
        for item in data:
            live = item.get('live') or {}
            channel = item.get('channel') or {}
            channel_id = channel.get('channelId') or ''
            if not channel_id:
                continue
            thumbnail = (live.get('liveImageUrl') or live.get('defaultThumbnailImageUrl') or '')
            results.append({
                'platform': 'chzzk',
                'streamer_id': channel_id,
                'streamer_name': channel.get('channelName') or '',
                'title': live.get('liveTitle') or '',
                'category': live.get('liveCategoryValue') or '',
                'viewers': live.get('concurrentUserCount'),
                'thumbnail': thumbnail.replace('{type}', '480'),
                'started_at': live.get('openDate') or '',
                'url': f'https://chzzk.naver.com/live/{channel_id}',
            })
        return results

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
