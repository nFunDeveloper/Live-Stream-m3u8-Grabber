import logging

import requests

from platform_modules.platform_default import PlatformDefault


logger = logging.getLogger(__name__)


class Pandalive(PlatformDefault):
    platform = "PandaliveParser"
    version = "1.0.0"

    api_url = "https://api.pandalive.co.kr/v1/live/play"
    index_url = "https://api.pandalive.co.kr/v1/live/index"
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
            return {"m3u8_url": ""}

        live_info = self.__request_live_info(user_id)
        logger.info(
            "[pandalive] live info result=%s message=%s media=%s",
            live_info.get("result"),
            live_info.get("message"),
            live_info.get("media", {}),
        )
        media = live_info.get("media") or {}
        member = live_info.get("member") or {}
        info = {
            "m3u8_url": "",
            "title": media.get("title") or "",
            "streamer_name": self.first_of(member, "userNick") or self.first_of(media, "userNick", "userId") or user_id,
            "category": "",
            "started_at": self.first_of(media, "defaultStartDate", "openDate") or "",
            "viewers": media.get("userCount") or media.get("viewerCount"),
            "thumbnail": self.first_of(media, "defaultThumbnail", "thumbnailUrl", "thumbnail") or "",
        }

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

            return info

        if not media.get("isLive"):
            logger.warning("[pandalive] stream not live response=%s", live_info)
            return info

        playlist_url = self.__select_playlist_url(live_info.get("PlayList", {}), normalized_quality)
        if not playlist_url:
            logger.warning("[pandalive] playlist url not found response=%s", live_info)
            return info

        if normalized_quality == "auto":
            info["m3u8_url"] = playlist_url
            return info

        headers = {
            **self.headers,
            "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
        }
        variant_url = self.get_variant_url_from_master(playlist_url, normalized_quality, headers)
        info["m3u8_url"] = variant_url or playlist_url
        return info

    def get_recommendations(self, limit=12):
        """팬더라이브 메인 라이브 인덱스. 시청자가 많은 대략의 순서로 내려온다."""
        response = self.session.get(self.index_url, headers=self.headers, timeout=8)
        response.raise_for_status()
        items = (response.json() or {}).get("list") or []

        results = []
        for item in items:
            user_id = item.get("userId") or ""
            if not user_id:
                continue
            width = item.get("sizeWidth") or 0
            height = item.get("sizeHeight") or 0
            results.append({
                'platform': 'pandalive',
                'streamer_id': user_id,
                'streamer_name': item.get('userNick') or user_id,
                'title': item.get('title') or '',
                'category': (item.get('category') if isinstance(item.get('category'), str) else '') or '',
                'viewers': item.get('user'),
                'thumbnail': item.get('thumbUrl') or '',
                'started_at': item.get('startTime') or '',
                'url': f'{self.origin}/live/{user_id}',
                # 인덱스에 해상도가 실려 온다 (예: 1920x1080)
                'resolution': f"{width}x{height}" if width and height else '',
            })
            if len(results) >= limit:
                break
        return results

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
