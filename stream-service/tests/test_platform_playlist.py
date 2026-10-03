import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from platform_modules.pandalive import Pandalive
from platform_modules.platform_default import PlatformDefault
from platform_modules.popkon import Popkon
from platform_modules.soop import Soop


MASTER_PLAYLIST = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=8000000,RESOLUTION=1920x1080,NAME="1080p"
1080p/stream.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720,NAME="720p"
720p/stream.m3u8
"""


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self.ok = status_code < 400
        if isinstance(payload, str):
            self.text = payload
            self._json = None
        else:
            self.text = ""
            self._json = payload

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)

    def get(self, url, headers=None, timeout=None):
        return FakeResponse(self.responses.pop(0))

    def post(self, url, headers=None, data=None, timeout=None):
        return FakeResponse(self.responses.pop(0))


class VariantSelectionTests(unittest.TestCase):
    def setUp(self):
        self.platform = PlatformDefault()
        self.platform.session = FakeSession([MASTER_PLAYLIST])

    def test_selects_variant_by_name(self):
        url = self.platform.get_variant_url_from_master(
            "https://cdn.example.com/master.m3u8", "1080p"
        )
        self.assertEqual(url, "https://cdn.example.com/1080p/stream.m3u8")

    def test_selects_variant_by_height(self):
        url = self.platform.get_variant_url_from_master(
            "https://cdn.example.com/master.m3u8", "720p"
        )
        self.assertEqual(url, "https://cdn.example.com/720p/stream.m3u8")

    def test_returns_empty_when_quality_missing(self):
        url = self.platform.get_variant_url_from_master(
            "https://cdn.example.com/master.m3u8", "144p"
        )
        self.assertEqual(url, "")


class PandaliveTests(unittest.TestCase):
    @staticmethod
    def _live_info():
        return {
            "result": True,
            "media": {"isLive": True, "title": "판다 방송", "userNick": "판다스트리머"},
            "PlayList": {
                "hls": [
                    {"url": "https://cdn.example.com/master.m3u8", "name": "1080p", "sort": 1}
                ]
            },
        }

    def test_auto_returns_master_playlist(self):
        platform = Pandalive()
        platform.session = FakeSession([self._live_info()])
        info = platform.get_live("streamer", "auto")
        self.assertEqual(info["m3u8_url"], "https://cdn.example.com/master.m3u8")

    def test_auto_includes_metadata(self):
        platform = Pandalive()
        platform.session = FakeSession([self._live_info()])
        info = platform.get_live("streamer", "auto")
        self.assertEqual(info["title"], "판다 방송")
        self.assertEqual(info["streamer_name"], "판다스트리머")

    def test_quality_returns_variant(self):
        platform = Pandalive()
        platform.session = FakeSession([self._live_info(), MASTER_PLAYLIST])
        info = platform.get_live("streamer", "1080p")
        self.assertEqual(info["m3u8_url"], "https://cdn.example.com/1080p/stream.m3u8")

    def test_permission_required_raises_permission_error(self):
        platform = Pandalive()
        platform.session = FakeSession([
            {"result": False, "message": "성인 인증이 필요합니다.",
             "errorData": {"code": "needAdult"}}
        ])
        with self.assertRaises(PermissionError):
            platform.get_live("streamer", "auto")


class PopkonTests(unittest.TestCase):
    def test_invalid_stream_key_raises_value_error(self):
        with self.assertRaises(ValueError):
            Popkon().get_live("123", "720p")


class ChzzkSearchTests(unittest.TestCase):
    """라이브 제목 검색 + 채널 검색(live-detail 검증) 병합 동작을 확인한다"""

    @staticmethod
    def _fake_requests(route):
        class _Fake:
            def get(self, url, headers=None, params=None, timeout=None):
                return FakeResponse(route(url))

        return _Fake()

    def test_search_merges_title_and_channel_results(self):
        from unittest.mock import patch
        from platform_modules import chzzk as chzzk_module

        def route(url):
            if 'search/lives' in url:
                return {"content": {"data": [{
                    "live": {"liveTitle": "게임 방송", "liveCategoryValue": "게임",
                             "concurrentUserCount": 5, "liveImageUrl": "", "openDate": ""},
                    "channel": {"channelId": "AAA", "channelName": "채널A"},
                }]}}
            if 'search/channels' in url:
                return {"content": {"data": [
                    {"channel": {"channelId": "AAA", "channelName": "채널A"}},  # 중복
                    {"channel": {"channelId": "BBB", "channelName": "텐코 시부키"}},
                ]}}
            if 'channels/BBB/live-detail' in url:
                return {"content": {"status": "OPEN", "liveTitle": "시부키 방송",
                                    "channel": {"channelId": "BBB", "channelName": "텐코 시부키"},
                                    "concurrentUserCount": 4282, "openDate": "",
                                    "liveImageUrl": "", "liveCategoryValue": "게임"}}
            raise AssertionError(f"unexpected url: {url}")

        fake = self._fake_requests(route)
        with patch.object(chzzk_module, 'requests', fake):
            results = chzzk_module.Chzzk().search_lives("시부키", limit=8)

        ids = [item['streamer_id'] for item in results]
        self.assertEqual(ids, ["AAA", "BBB"])
        shibuki = results[1]
        self.assertEqual(shibuki['streamer_name'], "텐코 시부키")
        self.assertEqual(shibuki['viewers'], 4282)
        self.assertEqual(shibuki['url'], "https://chzzk.naver.com/live/BBB")

    def test_search_skips_offline_channels(self):
        from unittest.mock import patch
        from platform_modules import chzzk as chzzk_module

        def route(url):
            if 'search/lives' in url:
                return {"content": {"data": []}}
            if 'search/channels' in url:
                return {"content": {"data": [
                    {"channel": {"channelId": "OFF", "channelName": "오프라인 채널"}},
                ]}}
            if 'channels/OFF/live-detail' in url:
                return {"content": {"status": "CLOSE"}}
            raise AssertionError(f"unexpected url: {url}")

        fake = self._fake_requests(route)
        with patch.object(chzzk_module, 'requests', fake):
            results = chzzk_module.Chzzk().search_lives("오프라인", limit=8)

        self.assertEqual(results, [])


class SoopTests(unittest.TestCase):
    """SOOP는 .co.kr CNAME이 끊겨 있어 .com 으로 폴백해야 한다"""

    # SOOP master는 화질명(NAME=hd)과 끝의 쉼표가 붙은 상대 경로로 내려온다
    SOOP_MASTER = """#EXTM3U
#EXT-X-STREAM-INF:NAME=hd,BANDWIDTH=777600,RESOLUTION=960x540
auth_playlist.m3u8?aid=HD_AID,
#EXT-X-STREAM-INF:NAME=sd,BANDWIDTH=345600,RESOLUTION=640x360
auth_playlist.m3u8?aid=SD_AID,
"""

    def test_falls_back_to_com_when_co_kr_unresolvable(self):
        import requests
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        tried = []
        error_type = requests.RequestException  # patch 후에도 실제 예외 타입 유지

        class _Fake:
            def get(self, url, headers=None, timeout=None):
                tried.append(url)
                if 'sooplive.co.kr' in url:
                    raise error_type("Name or service not known")
                return FakeResponse({"result": "1", "view_url": "https://cdn.test/auth.m3u8"})

        with patch.object(soop_module, 'requests', _Fake()):
            body = soop_module.Soop()._Soop__get_soop_broad_url(297561449, "hd")

        self.assertTrue(any('sooplive.co.kr' in url for url in tried))
        self.assertTrue(any('sooplive.com' in url for url in tried))
        self.assertEqual(body["view_url"], "https://cdn.test/auth.m3u8")

    def test_returns_empty_when_every_host_fails(self):
        import requests
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        error_type = requests.RequestException

        class _Fake:
            def get(self, url, headers=None, timeout=None):
                raise error_type("Name or service not known")

        with patch.object(soop_module, 'requests', _Fake()):
            body = soop_module.Soop()._Soop__get_soop_broad_url(297561449, "hd")

        self.assertEqual(body, {})

    def test_selects_variant_by_resolution(self):
        platform = Soop()
        platform.session = FakeSession([self.SOOP_MASTER])
        url = platform.get_variant_url_from_master(
            "https://pc.test/auth_master_playlist.m3u8?aid=MASTER", "540p",
            Soop.playlist_headers,
        )
        # 쉼표가 제거되고 master aid가 아닌 variant 자체 aid를 유지한다
        self.assertEqual(
            url, "https://pc.test/auth_playlist.m3u8?aid=HD_AID"
        )

    def test_returns_empty_for_unavailable_resolution(self):
        platform = Soop()
        platform.session = FakeSession([self.SOOP_MASTER])
        url = platform.get_variant_url_from_master(
            "https://pc.test/auth_master_playlist.m3u8?aid=MASTER", "1080p",
            Soop.playlist_headers,
        )
        self.assertEqual(url, "")


if __name__ == "__main__":
    unittest.main()
