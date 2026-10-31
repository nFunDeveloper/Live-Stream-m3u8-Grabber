import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

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
            return {"m3u8_url": ""}

        channel_slug = channel_slug.lstrip("@")
        live_info = self.__request_live_info(channel_slug)
        logger.info("[cime] live info=%s", live_info)

        data = live_info.get("data") or {}
        channel = data.get("channel") or {}
        category = data.get("category") or {}
        info = {
            "m3u8_url": "",
            "title": data.get("title") or "",
            "streamer_name": channel.get("name") or channel.get("slug") or channel_slug,
            "category": category.get("name") or "",
            "started_at": data.get("openedAt") or "",
            "viewers": data.get("curViewerCnt"),
            "thumbnail": data.get("imageUrl") or "",
        }

        if live_info.get("code") != 200 or "data" not in live_info:
            logger.warning("[cime] live info not found response=%s", live_info)
            return info

        playback_url = (
            data.get("playbackUrl")
            or (data.get("playback") or {}).get("url")
        )
        if not playback_url:
            logger.warning("[cime] playback url not found response=%s", live_info)
            return info

        if normalized_quality == "auto":
            info["m3u8_url"] = playback_url
            return info

        headers = {
            **self.headers,
            "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
            "Origin": "https://ci.me",
        }
        variant_url = self.get_variant_url_from_master(playback_url, normalized_quality, headers)
        info["m3u8_url"] = variant_url or playback_url
        return info

    def check_status(self, channel_slug):
        live_info = self.__request_live_info(channel_slug.lstrip('@'))
        data = live_info.get('data') or {}
        is_live = data.get('state') == 'ACTIVE'
        return {
            'is_live': is_live,
            'viewers': data.get('curViewerCnt') if is_live else None,
            'title': (data.get('title') or '') if is_live else '',
        }

    def search_lives(self, keyword, limit=8):
        url = 'https://ci.me/api/app/search'
        headers = {**self.headers, 'Referer': 'https://ci.me/'}
        response = requests.get(
            url,
            headers=headers,
            params={'query': keyword, 'filter': 'LIVE'},
            timeout=6,
        )
        response.raise_for_status()
        sections = (response.json().get('data') or {}).get('sections') or []

        results = []
        for section in sections:
            if section.get('type') != 'LIVE':
                continue
            for item in section.get('items') or []:
                channel = item.get('channel') or {}
                slug = channel.get('slug')
                if not slug:
                    continue
                results.append({
                    'platform': 'cime',
                    'streamer_id': slug,
                    'streamer_name': channel.get('name') or slug,
                    'title': item.get('title') or '',
                    'category': (item.get('category') or {}).get('name') or '',
                    'viewers': item.get('curViewerCnt'),
                    'thumbnail': item.get('imageUrl') or '',
                    'started_at': item.get('openedAt') or '',
                    'url': f'https://ci.me/@{slug}/live',
                })
                if len(results) >= limit:
                    return results
        return results

    def get_recommendations(self, limit=12):
        """ci.me 메인의 인기 라이브. sort=POPULAR 만 서버 정렬로 내려온다.

        목록 응답에는 해상도가 없다. 각 항목의 master 플레이리스트(playback.url)
        를 열어 RESOLUTION 중 가장 높은 것을 해상도로 채운다 — 몇 건 안 되므로
        병렬로 읽고, 실패한 항목만 비워 둔다.
        """
        response = requests.get(
            'https://ci.me/api/app/lives',
            headers={**self.headers, 'Referer': 'https://ci.me/'},
            params={'sort': 'POPULAR'},
            timeout=8,
        )
        response.raise_for_status()
        sections = ((response.json() or {}).get('data') or {}).get('sections') or []

        results = []
        for section in sections:
            if section.get('type') != 'LIVE':
                continue
            for item in section.get('items') or []:
                channel = item.get('channel') or {}
                slug = channel.get('slug')
                if not slug:
                    continue
                results.append({
                    'platform': 'cime',
                    'streamer_id': slug,
                    'streamer_name': channel.get('name') or slug,
                    'title': item.get('title') or '',
                    'category': (item.get('category') or {}).get('name') or '',
                    'viewers': item.get('curViewerCnt'),
                    'thumbnail': item.get('imageUrl') or '',
                    'started_at': item.get('openedAt') or '',
                    'url': f'https://ci.me/@{slug}/live',
                    'master_url': (item.get('playback') or {}).get('url') or '',
                })
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

        with ThreadPoolExecutor(max_workers=min(6, max(len(results), 1))) as pool:
            futures = {
                pool.submit(self.__max_resolution, item.pop('master_url', '')): index
                for index, item in enumerate(results)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index]['resolution'] = future.result()
                except Exception:
                    results[index]['resolution'] = ''
        return results

    def __max_resolution(self, master_url):
        """master 플레이리스트가 알려주는 variant 중 가장 높은 해상도."""
        if not master_url:
            return ""
        headers = {
            **self.headers,
            "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
            "Origin": "https://ci.me",
        }
        response = requests.get(master_url, headers=headers, timeout=8)
        response.raise_for_status()
        heights = re.findall(r"RESOLUTION=(\d+)x(\d+)", response.text or "")
        if not heights:
            return ""
        best = max(heights, key=lambda pair: int(pair[1]))
        return f"{best[0]}x{best[1]}"

    def __request_live_info(self, channel_slug):
        url = f"https://ci.me/api/app/channels/{channel_slug}/live"
        headers = {**self.headers, "Referer": f"https://ci.me/@{channel_slug}/live"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
