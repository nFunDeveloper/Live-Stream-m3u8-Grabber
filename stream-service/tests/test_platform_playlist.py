import base64
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from platform_modules import chzzk as chzzk_module
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
    def __init__(self, payload, status_code=200, headers=None):
        self.status_code = status_code
        self.ok = status_code < 400
        self.headers = headers or {}
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


class SoopSearchTests(unittest.TestCase):
    """SOOP 라이브 검색과 자동완성 보강 동작을 확인한다"""

    @staticmethod
    def _fake_requests(route):
        class _Fake:
            def get(self, url, headers=None, params=None, timeout=None):
                return FakeResponse(route(url, params))

        return _Fake()

    def test_search_maps_live_broadcast_fields(self):
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        def route(url, params):
            self.assertEqual(url, soop_module.Soop.search_api)
            if params.get('m') == 'searchHistory':
                return {"suggest_bj": [
                    {"user_id": "lshooooo", "user_nick": "이상호",
                     "station_logo": "https://logo/a.jpg"},
                ]}
            self.assertEqual(params['m'], 'liveSearch')
            self.assertEqual(params['szKeyword'], '롤')
            return {"TOTAL_CNT": "479", "REAL_BROAD": [{
                "broad_title": "롤ck 탑 vs 태민벨",
                "b_broad_title": "폴백 제목",
                "broad_img": "https://liveimg.sooplive.com/m/297588457",
                "station_name": "Justlikethat",
                "m_current_view_cnt": "2421",
                "broad_cate_name": "리그 오브 레전드",
                "broad_start": "2026-10-04 18:07:32",
                "user_id": "joey1114",
            }]}

        fake = self._fake_requests(route)
        with patch.object(soop_module, 'requests', fake):
            results = soop_module.Soop().search_lives("롤", limit=8)

        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item['platform'], 'soop')
        self.assertEqual(item['streamer_id'], 'joey1114')
        self.assertEqual(item['streamer_name'], 'Justlikethat')
        self.assertEqual(item['title'], '롤ck 탑 vs 태민벨')
        self.assertEqual(item['category'], '리그 오브 레전드')
        self.assertEqual(item['viewers'], 2421)
        self.assertEqual(item['started_at'], '2026-10-04 18:07:32')
        self.assertEqual(item['url'], 'https://play.sooplive.co.kr/joey1114')

    def test_search_falls_back_to_suggestion_profile(self):
        # 라이브 검색이 주는 이미지/닉네임이 비면 자동완성 후보로 채운다
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        def route(url, params):
            if params.get('m') == 'searchHistory':
                return {"suggest_bj": [
                    {"user_id": "abc", "user_nick": "자동완성닉",
                     "station_logo": "https://logo/x.jpg"},
                ]}
            return {"REAL_BROAD": [{"user_id": "abc", "broad_title": "방송",
                                    "m_current_view_cnt": "-"}]}

        fake = self._fake_requests(route)
        with patch.object(soop_module, 'requests', fake):
            results = soop_module.Soop().search_lives("방송", limit=8)

        self.assertEqual(results[0]['streamer_name'], '자동완성닉')
        self.assertEqual(results[0]['thumbnail'], 'https://logo/x.jpg')
        # '-' 같은 값은 숫자로 바꾸지 못하고 None이 된다
        self.assertIsNone(results[0]['viewers'])

    def test_search_survives_suggestion_failure(self):
        # 자동완성은 보조 정보라 실패해도 라이브 검색 결과는 그대로 낸다
        import requests
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        error_type = requests.RequestException  # patch 후에도 실제 예외 타입 유지

        def route(url, params):
            if params.get('m') == 'searchHistory':
                raise error_type("boom")
            return {"REAL_BROAD": [{"user_id": "abc", "broad_title": "방송",
                                    "station_name": "방송자", "m_current_view_cnt": "12"}]}

        fake = self._fake_requests(route)
        with patch.object(soop_module, 'requests', fake):
            results = soop_module.Soop().search_lives("방송", limit=8)

        self.assertEqual([item['streamer_name'] for item in results], ['방송자'])

    def test_search_respects_limit_and_skips_missing_user_id(self):
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        def route(url, params):
            if params.get('m') == 'searchHistory':
                return {"suggest_bj": []}
            return {"REAL_BROAD": [
                {"broad_title": "user_id 없는 항목"},
                {"user_id": "one", "broad_title": "첫째"},
                {"user_id": "two", "broad_title": "둘째"},
            ]}

        fake = self._fake_requests(route)
        with patch.object(soop_module, 'requests', fake):
            results = soop_module.Soop().search_lives("검색", limit=2)

        self.assertEqual([item['streamer_id'] for item in results], ['one', 'two'])


class SoopStatusTests(unittest.TestCase):
    """SOOP 방송 상태 확인 동작을 확인한다"""

    @staticmethod
    def _fake_requests(payload):
        class _Fake:
            def post(self, url, headers=None, data=None, timeout=None):
                return FakeResponse(payload)

        return _Fake()

    def _check(self, payload):
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        fake = self._fake_requests(payload)
        with patch.object(soop_module, 'requests', fake):
            return soop_module.Soop().check_status('b13246')

    def test_reports_live_with_viewers_and_title(self):
        status = self._check({"result": 1, "data": {
            "broad_status": "BROADING",
            "broad_title": "엘든링 밤의통치자",
            "view_cnt": 5066,
        }})

        self.assertEqual(status, {
            'is_live': True,
            'viewers': 5066,
            'title': '엘든링 밤의통치자',
        })

    def test_reports_offline_when_no_broadcast(self):
        # 방송이 없는 채널도 data 안에 user_nick 만 담아 돌아온다
        status = self._check({"result": -1, "data": {"user_nick": "[KU]윤아"}})

        self.assertEqual(status, {'is_live': False, 'viewers': None, 'title': ''})

    def test_paused_broadcast_is_not_live(self):
        # 일시정지된 방송도 result 가 1 이라 상태 문자열까지 같이 봐야 한다
        status = self._check({"result": 1, "data": {
            "broad_status": "PAUSED",
            "broad_title": "일시정지",
            "view_cnt": 12,
        }})

        self.assertEqual(status, {'is_live': False, 'viewers': None, 'title': ''})

    def test_viewer_count_is_parsed_when_not_a_number(self):
        status = self._check({"result": 1, "data": {
            "broad_status": "BROADING",
            "view_cnt": "1,234",
        }})

        self.assertEqual(status['viewers'], 1234)


class SoopTests(unittest.TestCase):
    """SOOP는 .co.kr CNAME이 끊겨 있어 .com 으로 폴백해야 한다"""

    @staticmethod
    def _fake_requests(route):
        class _Fake:
            def get(self, url, headers=None, params=None, timeout=None):
                return FakeResponse(route(url))

        return _Fake()

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
                # 관리자 호스트의 DNS 실패만 흉내 낸다. cors 파라미터도 .co.kr 를
                # 담게 되었으므로(국내 원칙) 문자열 전체가 아니라 호스트로 판별한다
                if 'livestream-manager.sooplive.co.kr' in url:
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

    def test_recommendations_served_from_korean_list(self):
        import requests
        from unittest.mock import patch
        from platform_modules import soop as soop_module

        def route(url):
            # 국내 원칙: ko_KR 목록만 쓴다. 외국(en_US) 파일을 부르면 실패로 간다
            assert "/pc/ko_KR/" in url, f"외국 경로 사용됨: {url}"

            def item(user_id, nick, view, m_view, title="제목", reso="1920x1080"):
                return {
                    "broad_no": f"{user_id}no", "user_id": user_id,
                    "user_nick": nick, "broad_title": title,
                    "current_view_cnt": str(view), "m_current_view_cnt": str(m_view),
                    "broad_resolution": reso, "category_name": "게임",
                    "broad_thumb": "//liveimg.sooplive.com/m/1",
                }

            # 같은 방송이 두 섹션에 걸쳐 중복 노출되는 형태 (SOOP 실제 동작)
            return {"DATA": [
                {"SECTION_CODE": "POP_LIVE_01", "DATA": [
                    item("aaa", "가방사", 800, 100),
                    item("bbb", "나가는", 4000, 200),
                    item("", "아이디없음", 9999, 0),      # user_id 없는 항목은 버린다
                ]},
                {"SECTION_CODE": "POP_PREVIEW", "DATA": [
                    item("aaa", "가방사", 800, 100),      # 중복 broad_no → 한 번만
                    item("ccc", "다중공백", 900, 50),
                ]},
            ]}

        fake = self._fake_requests(route)
        with patch.object(soop_module, 'requests', fake):
            results = soop_module.Soop().get_recommendations(limit=8)

        self.assertEqual([r['streamer_id'] for r in results], ["bbb", "ccc", "aaa"])  # 시청자 내림
        top = results[0]
        self.assertEqual(top['viewers'], 4200)                 # PC+모바일 합산
        self.assertEqual(top['url'], "https://play.sooplive.co.kr/bbb")  # 국내 도메인
        self.assertEqual(top['thumbnail'], "https://liveimg.sooplive.com/m/1")  # 스킴 보정


class ChzzkQualitySelectionTests(unittest.TestCase):
    """치지직이 1080p 같은 특정 화질을 골라내지 못하던 문제의 회귀 테스트.

    치지직은 live-detail 의 encodingTrack 에 영상 트랙 path 를 비워 두고, 마스터
    플레이리스트의 variant 앞에 Akamai 토큰(hdntl=...)을 붙여 보낸다. 토큰이
    경로 앞을 막으므로 "1080p/" 로 시작하는지 보는 구식 검사로는 어떤 화질도
    찾을 수 없었다.
    """

    MASTER = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:10\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=8384000,RESOLUTION=1920x1080\n"
        "hdntl=exp=1~acl=*%2Fabc%2F*~hmac=aa11/1080p/chunklist.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=3192000,RESOLUTION=1280x720\n"
        "hdntl=exp=1~acl=*%2Fabc%2F*~hmac=aa11/720p/chunklist.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1692000,RESOLUTION=852x480\n"
        "hdntl=exp=1~acl=*%2Fabc%2F*~hmac=aa11/480p/chunklist.m3u8\n"
    )

    @staticmethod
    def _live_detail(path_prefix="nvelop-livecloud.pstatic.net", embed_cdn_url=""):
        """영상 트랙 path 가 비어 있는 실제 응답 형태를 만든다.

        embed_cdn_url 이 있으면 첫 트랙(1080p)의 p2pPath 에 base64 로 감싼 실제
        CDN 주소를 끼워 넣는다 — 치지직이 하는 방식 그대로.
        """
        tracks = []
        for index, (height, bitrate) in enumerate(
            (("1080p", 8192000), ("720p", 3000000), ("480p", 1000000))
        ):
            tracks.append({
                "encodingTrackId": height,
                "path": "",
                "p2pPath": f"/chzzk/lip2_kr/abc/{height}_playlist.m3u8",   # 토큰 없음
                "videoWidth": 1920 if height == "1080p" else 1280,
                "videoHeight": 1080 if height == "1080p" else 720,
            })
        if embed_cdn_url:
            wrapped = base64.b64encode(embed_cdn_url.encode()).decode()
            tracks[0]["p2pPath"] = f"/chzzk/1080p/pl.m3u8?cdn_url={wrapped}"
        return {
            "content": {
                "status": "OPEN",
                "liveTitle": "테스트 방송",
                "channel": {"channelId": "CCC", "channelName": "테스터"},
                "livePlaybackJson": json.dumps({
                    "media": [{
                        "path": f"https://{path_prefix}/chzzk/master.m3u8",
                        "encodingTrack": tracks,
                    }]
                }),
            }
        }

    @staticmethod
    def _fake_requests(route):
        class _Fake:
            def get(self, url, headers=None, params=None, timeout=None):
                return FakeResponse(route(url))

        return _Fake()

    def test_selects_variant_hidden_behind_akamai_token(self):
        from unittest.mock import patch

        def route(url):
            if "live-detail" in url:
                return self._live_detail()
            if url.endswith("master.m3u8"):
                return self.MASTER
            raise AssertionError(f"unexpected url: {url}")

        fake = self._fake_requests(route)
        with patch.object(chzzk_module, "requests", fake):
            info = chzzk_module.Chzzk().get_live("CCC", "1080p")

        variant = info["m3u8_url"]
        self.assertTrue(variant.startswith("https://nvelop-livecloud.pstatic.net/"))
        self.assertIn("/1080p/chunklist.m3u8", variant)

    def test_falls_back_to_cdn_url_hidden_in_p2p_path(self):
        from unittest.mock import patch

        # 마스터에서 화질을 못 찾는 경우(예: 목록이 비어 있을 때) cdn_url 로 되돌아간다
        detail = self._live_detail(
            embed_cdn_url="https://real-cdn.example.com/chzzk/1080p/playlist.m3u8?hdnts=token",
        )

        def route(url):
            if "live-detail" in url:
                return detail
            if url.endswith("master.m3u8"):
                return ""   # variant 가 하나도 없다
            raise AssertionError(f"unexpected url: {url}")

        fake = self._fake_requests(route)
        with patch.object(chzzk_module, "requests", fake):
            info = chzzk_module.Chzzk().get_live("CCC", "1080p")

        self.assertEqual(info["m3u8_url"],
                         "https://real-cdn.example.com/chzzk/1080p/playlist.m3u8?hdnts=token")

    def test_track_url_uses_master_host_when_cdn_url_missing(self):
        platform = chzzk_module.Chzzk()
        track = {"path": "", "p2pPath": "/chzzk/720p/pl.m3u8"}
        url = platform._Chzzk__get_track_url(track, "https://fcdn-livecloud.pstatic.net/master.m3u8")
        self.assertEqual(url, "https://fcdn-livecloud.pstatic.net/chzzk/720p/pl.m3u8")

    def test_kr_only_broadcast_without_playback_raises_clear_error(self):
        """국내 전용(스포츠 공식 중계) 방송은 서버가 국외면 livePlaybackJson 가
        None 로 온다(실측). 이때 500 이 아니라 알아들을 수 있는 오류로 빠진다."""
        from unittest.mock import patch
        from platform_modules import chzzk as chz

        def route(url):
            if "live-detail" in url:
                return {
                    "content": {
                        "status": "OPEN",
                        "krOnlyViewing": True,
                        "tvAppViewingPolicyType": "ALLOWED_FOR_CHEAT_KEY_ONLY",
                        "livePlaybackJson": None,
                        "previewPlaybackJson": None,
                        "channel": {"channelId": "SP", "channelName": "치지직 배구 중계"},
                        "liveTitle": "V리그 중계",
                    }
                }
            raise AssertionError(f"unexpected url: {url}")

        fake = self._fake_requests(route)
        with patch.object(chz, 'requests', fake):
            with self.assertRaises(ValueError) as ctx:
                chz.Chzzk().get_live("SP", "auto")
        self.assertIn("국내", str(ctx.exception))

    def test_decodes_embedded_cdn_url(self):
        platform = chzzk_module.Chzzk()
        encoded = base64.b64encode(b"https://cdn.example.com/x.m3u8?hdnts=t1").decode()
        self.assertEqual(
            platform._Chzzk__decode_embedded_url(f"/p/c.m3u8?cdn_url={encoded}"),
            "https://cdn.example.com/x.m3u8?hdnts=t1",
        )
        # 감싼 값이 URL 이 아니거나 깨진 base64 면 빈 문자열을 돌려준다
        self.assertEqual(platform._Chzzk__decode_embedded_url("/p/c.m3u8?cdn_url=!!"), "")
        self.assertEqual(platform._Chzzk__decode_embedded_url("/p/c.m3u8"), "")


if __name__ == "__main__":
    unittest.main()
