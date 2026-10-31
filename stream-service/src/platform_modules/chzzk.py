import base64
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
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
                m3u8_url = self.__get_track_url(selected_track, master_m3u8_url)

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

    def check_status(self, streamer_id):
        content = self.__fetch_live_detail(streamer_id)
        is_live = content.get('status') == 'OPEN'
        return {
            'is_live': is_live,
            'viewers': content.get('concurrentUserCount') if is_live else None,
            'title': (content.get('liveTitle') or '') if is_live else '',
        }

    def search_lives(self, keyword, limit=8):
        # 1) 라이브 제목 검색
        results = self.__search_live_titles(keyword, limit)
        seen = {item['streamer_id'] for item in results}

        # 2) 채널명 검색 보완 — 실명인증 방송 등 일부 방송은 라이브 검색 인덱스에서
        # 누락되지만 채널 검색에는 나온다. live-detail로 방송 중 여부를 확인해 합친다.
        channel_results = self.__search_channels(keyword, limit=limit)
        for item in channel_results:
            if item['streamer_id'] not in seen:
                seen.add(item['streamer_id'])
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    def get_recommendations(self, limit=12):
        """치지직 메인 라이브 피드. 검색 API와 달리 시청자 많은 순으로 정렬돼 온다."""
        # 오프셋 0의 첫 페이지 — 치지직이 정해둔 대기열 순서(인기 위주)를 받는다.
        response = requests.get(
            'https://api.chzzk.naver.com/service/v1/lives',
            headers=self.headers,
            params={'offset': 0, 'size': limit},
            timeout=8,
        )
        response.raise_for_status()
        items = (response.json().get('content') or {}).get('data') or []

        results = []
        for item in items:
            # 검색 응답과 달리 live/채널이 한 객체로 바로 온다
            channel = item.get('channel') or {}
            channel_id = channel.get('channelId') or ''
            if not channel_id:
                continue
            thumbnail = (item.get('liveImageUrl') or item.get('defaultThumbnailImageUrl') or '')
            results.append({
                'platform': 'chzzk',
                'streamer_id': channel_id,
                'streamer_name': channel.get('channelName') or '',
                'title': item.get('liveTitle') or '',
                'category': item.get('liveCategoryValue') or '',
                'viewers': item.get('concurrentUserCount'),
                'thumbnail': thumbnail.replace('{type}', '480'),
                'started_at': item.get('openDate') or '',
                'url': f'https://chzzk.naver.com/live/{channel_id}',
            })

        # 라이브 피드에는 해상도가 없다. 각 방송의 live-detail(encodingTrack)에서
        # 최고 해상도를 읽어 채운다. 건수가 제한적이어서 제한된 풀로 병렬로 읽고,
        # 실패한 항목은 비워 둔다 (해상도 배지 없이 나가는 게 응답 실패보다 낫다).
        with ThreadPoolExecutor(max_workers=min(8, max(len(results), 1))) as pool:
            futures = {
                pool.submit(self.__max_track_resolution, item['streamer_id']): index
                for index, item in enumerate(results)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    results[index]['resolution'] = future.result()
                except Exception:
                    results[index]['resolution'] = ''
        return results

    def __max_track_resolution(self, channel_id):
        """live-detail 의 encodingTrack 가장 높은 videoWidth x videoHeight."""
        content = self.__fetch_live_detail(channel_id) or {}
        raw = content.get('livePlaybackJson')
        if not raw:
            return ''
        media = json.loads(raw).get('media') or []
        tracks = [
            track
            for m in media
            for track in (m.get('encodingTrack') or [])
        ]
        best = max(tracks, key=lambda t: (t.get('videoHeight') or 0), default=None)
        if not best or not best.get('videoHeight'):
            return ''
        return f"{best.get('videoWidth') or 0}x{best.get('videoHeight')}"

    def __search_live_titles(self, keyword, limit):
        response = requests.get(
            'https://api.chzzk.naver.com/service/v1/search/lives',
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

    def __search_channels(self, keyword, limit):
        response = requests.get(
            'https://api.chzzk.naver.com/service/v1/search/channels',
            headers=self.headers,
            params={'keyword': keyword, 'offset': 0, 'size': limit},
            timeout=6,
        )
        response.raise_for_status()
        data = response.json().get('content', {}).get('data') or []
        channel_ids = [
            (item.get('channel') or {}).get('channelId')
            for item in data
            if (item.get('channel') or {}).get('channelId')
        ]
        if not channel_ids:
            return []

        results = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(self.__fetch_live_detail, cid): cid for cid in channel_ids}
            for future in as_completed(futures):
                channel_id = futures[future]
                content = future.result()
                if content.get('status') != 'OPEN':
                    continue
                info = self.__build_info(content)
                results.append({
                    'platform': 'chzzk',
                    'streamer_id': channel_id,
                    'streamer_name': info['streamer_name'],
                    'title': info['title'],
                    'category': info['category'],
                    'viewers': info['viewers'],
                    'thumbnail': info['thumbnail'],
                    'started_at': info['started_at'],
                    'url': f'https://chzzk.naver.com/live/{channel_id}',
                })
        return results

    def __fetch_live_detail(self, channel_id):
        try:
            url = f'https://api.chzzk.naver.com/service/v3.2/channels/{channel_id}/live-detail'
            headers = {**self.headers, 'Referer': f'https://chzzk.naver.com/live/{channel_id}'}
            response = requests.get(url, headers=headers, timeout=6)
            response.raise_for_status()
            return response.json().get('content') or {}
        except Exception:
            logger.exception("[chzzk] live-detail check failed channel=%s", channel_id)
            return {}

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

    def __get_track_url(self, track, master_m3u8_url=""):
        if track.get("path"):
            return track["path"]

        p2p_path = track.get("p2pPath") or track.get("p2pPathUrlEncoding") or ""
        if not p2p_path:
            return ""

        # p2pPath 쿼리에 base64 로 감싼 실제 CDN 주소가 있다. 여기에 hdnts 토큰까지
        # 들어 있어 이걸 그대로 쓰는 게 확실하다.
        embedded = self.__decode_embedded_url(p2p_path)
        if embedded:
            return embedded

        # 없으면 마스터 플레이리스트가 쓴 호스트에 경로만 덧붙인다. 실제 CDN은
        # fcdn-/nvelop- 등으로 갈리므로 호스트를 하드코딩하면 400이 난다.
        origin = self.__origin_of(master_m3u8_url) or self.origin_stream_url
        return origin + p2p_path

    @staticmethod
    def __origin_of(url):
        if not url:
            return ""
        scheme, sep, rest = url.partition("//")
        if not sep or not rest:
            return ""
        host = rest.split("/", 1)[0].split("?", 1)[0]
        return f"{scheme}//{host}" if host else ""

    @staticmethod
    def __decode_embedded_url(p2p_path):
        """p2pPath 안에 cdn_url 로 끼워 넣은 절대 주소를 풀어낸다."""
        if "cdn_url=" not in p2p_path:
            return ""
        encoded = p2p_path.split("cdn_url=", 1)[1].split("&", 1)[0]
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""
        return decoded if decoded.startswith(("http://", "https://")) else ""

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

            # variant 경로 앞에는 Akamai 토큰이 붙어 있어 "1080p/" 로 시작하지 않는다.
            # 경로 조각 하나하나를 놓고 화질 이름과 맞춘다.
            # (구식 startswith 검사로는 어떤 화질도 못 찾는다.)
            if quality not in variant_path.split("/"):
                continue

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
