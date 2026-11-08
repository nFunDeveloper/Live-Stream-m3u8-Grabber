import hashlib
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from urllib.parse import quote
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

# 테스트는 기본적으로 잠금이 꺼진 상태를 쓴다. 잠금이 필요한 클래스는 setUp 에서
# APP_AUTH=on 으로 다시 켠다. (인증번호는 이제 APP_PASSWORD 가 아니라 상태 파일의
# 날짜별 키로 관리되므로, 잠금 스위치도 별도 환경변수로 바뀌었다)
os.environ["APP_AUTH"] = "off"

import app as app_module
import auth_guard
import platform_health
import stream_proxy


CHZZK_URL = "https://chzzk.naver.com/live/test_channel"

FAKE_INFO = {
    "m3u8_url": "https://cdn.example.com/master.m3u8",
    "title": "테스트 방송",
    "streamer_name": "테스트 스트리머",
    "category": "테스트 카테고리",
    "started_at": "2026-10-03 08:09:20",
    "viewers": 10240,
    "thumbnail": "https://cdn.example.com/thumb.jpg",
}


def fake_platform(**overrides):
    platform = Mock()
    platform.get_live.return_value = {**FAKE_INFO, **overrides}
    return platform


class GrabApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_missing_url_returns_400(self):
        response = self.client.get("/api/grab")
        self.assertEqual(response.status_code, 400)

    def test_unsupported_hostname_returns_400(self):
        response = self.client.get("/api/grab?url=https://example.com/live/abc")
        self.assertEqual(response.status_code, 400)

    def test_invalid_chzzk_path_returns_400(self):
        response = self.client.get("/api/grab?url=https://chzzk.naver.com/live")
        self.assertEqual(response.status_code, 400)

    def test_success_returns_metadata(self):
        with patch.dict(app_module.platforms, {"chzzk": fake_platform()}):
            response = self.client.get(f"/api/grab?url={CHZZK_URL}&quality=720p")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["m3u8_url"], "https://cdn.example.com/master.m3u8")
        self.assertEqual(body["platform"], "chzzk")
        self.assertEqual(body["streamer_id"], "test_channel")
        self.assertEqual(body["quality"], "720p")
        self.assertEqual(body["title"], "테스트 방송")
        self.assertEqual(body["streamer_name"], "테스트 스트리머")
        self.assertEqual(body["category"], "테스트 카테고리")
        self.assertEqual(body["started_at"], "2026-10-03 08:09:20")
        self.assertEqual(body["viewers"], 10240)
        self.assertEqual(body["thumbnail"], "https://cdn.example.com/thumb.jpg")

    def test_popkon_stream_key_uses_cast_and_partner_code(self):
        url = "https://www.popkontv.com/live/view?castId=123&partnerCode=ABC"
        platform = fake_platform()
        with patch.dict(app_module.platforms, {"popkon": platform}):
            response = self.client.get(f"/api/grab?url={quote(url, safe='')}")

        self.assertEqual(response.status_code, 200)
        platform.get_live.assert_called_once_with("123|ABC", "auto")

    def test_permission_error_returns_403(self):
        platform = fake_platform()
        platform.get_live.side_effect = PermissionError("성인 인증이 필요한 방송입니다.")
        with patch.dict(app_module.platforms, {"chzzk": platform}):
            response = self.client.get(f"/api/grab?url={CHZZK_URL}")

        self.assertEqual(response.status_code, 403)
        self.assertIn("성인 인증", response.get_json()["error"])

    def test_value_error_returns_400_with_message(self):
        platform = fake_platform()
        platform.get_live.side_effect = ValueError(
            "Popkon stream key must include castId and partnerCode."
        )
        url = "https://www.popkontv.com/live/view?castId=123&partnerCode=ABC"
        with patch.dict(app_module.platforms, {"popkon": platform}):
            response = self.client.get(f"/api/grab?url={quote(url, safe='')}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Popkon stream key must include castId and partnerCode.",
        )

    def test_empty_m3u8_returns_404(self):
        with patch.dict(app_module.platforms, {"chzzk": fake_platform(m3u8_url="")}):
            response = self.client.get(f"/api/grab?url={CHZZK_URL}")

        self.assertEqual(response.status_code, 404)


class LegacyRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_success_redirects_to_m3u8(self):
        with patch.dict(app_module.platforms, {"chzzk": fake_platform()}):
            response = self.client.get("/chzzk/test_channel/720p")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://cdn.example.com/master.m3u8")

    def test_empty_m3u8_returns_404(self):
        with patch.dict(app_module.platforms, {"chzzk": fake_platform(m3u8_url="")}):
            response = self.client.get("/chzzk/test_channel/720p")

        self.assertEqual(response.status_code, 404)

    def test_unknown_platform_returns_404(self):
        response = self.client.get("/nosuch/channel/720p")
        self.assertEqual(response.status_code, 404)

    def test_value_error_returns_400(self):
        platform = fake_platform()
        platform.get_live.side_effect = ValueError(
            "Popkon stream key must include castId and partnerCode."
        )
        with patch.dict(app_module.platforms, {"popkon": platform}):
            response = self.client.get("/popkon/123/720p")

        self.assertEqual(response.status_code, 400)


class DetectRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_success_redirects_to_m3u8(self):
        with patch.dict(app_module.platforms, {"chzzk": fake_platform()}):
            response = self.client.get(f"/detect/auto?url={CHZZK_URL}")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://cdn.example.com/master.m3u8")

    def test_not_live_returns_404(self):
        with patch.dict(app_module.platforms, {"chzzk": fake_platform(m3u8_url="")}):
            response = self.client.get(f"/detect/auto?url={CHZZK_URL}")

        self.assertEqual(response.status_code, 404)


class SearchApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_empty_query_returns_empty_results(self):
        response = self.client.get("/api/search")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"], [])

    def test_search_merges_results_from_searchable_platforms(self):
        chzzk = Mock(spec=app_module.Chzzk)
        chzzk.search_lives.return_value = [
            {"platform": "chzzk", "url": "https://chzzk.naver.com/live/a", "viewers": 10}
        ]
        cime = Mock(spec=app_module.Cime)
        cime.search_lives.return_value = [
            {"platform": "cime", "url": "https://ci.me/@b/live", "viewers": 30}
        ]
        soop = Mock(spec=app_module.Soop)
        soop.search_lives.return_value = [
            {"platform": "soop", "url": "https://play.sooplive.com/c", "viewers": 20}
        ]
        popkon = Mock(spec=app_module.Popkon)  # search_lives 미구현 플랫폼
        with patch.dict(
            app_module.platforms,
            {"chzzk": chzzk, "cime": cime, "soop": soop, "popkon": popkon},
            clear=True,
        ):
            response = self.client.get("/api/search?q=%EA%B2%8C%EC%9E%84")

        self.assertEqual(response.status_code, 200)
        results = response.get_json()["results"]
        self.assertEqual(len(results), 3)
        # 시청자 수 내림차순 정렬
        self.assertEqual([item["platform"] for item in results], ["cime", "soop", "chzzk"])
        chzzk.search_lives.assert_called_once()
        self.assertFalse(hasattr(popkon, "search_lives"))  # 미구현 플랫폼은 검색 대상 아님

    def test_search_swallows_platform_failure(self):
        chzzk = Mock(spec=app_module.Chzzk)
        chzzk.search_lives.side_effect = RuntimeError("api down")
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True):
            response = self.client.get("/api/search?q=game")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"], [])

    def test_search_dedupes_soop_and_afreeca_alias(self):
        # SOOP는 soop 과 afreeca 두 이름으로 등록돼 있어 같은 방송이 두 번 온다
        entry = {"platform": "soop", "streamer_id": "abc", "viewers": 10}
        soop = Mock(spec=app_module.Soop)
        soop.search_lives.return_value = [entry]
        afreeca = Mock(spec=app_module.Soop)
        afreeca.search_lives.return_value = [entry]
        with patch.dict(
            app_module.platforms, {"soop": soop, "afreeca": afreeca}, clear=True
        ):
            response = self.client.get("/api/search?q=%EB%A1%9C")

        results = response.get_json()["results"]
        self.assertEqual([item["streamer_id"] for item in results], ["abc"])


class StatusApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_returns_live_status_per_entry(self):
        chzzk = Mock(spec=app_module.Chzzk)
        chzzk.check_status.return_value = {"is_live": True, "viewers": 4282, "title": "방송"}
        soop = Mock(spec=app_module.Soop)  # check_status 미구현
        with patch.dict(app_module.platforms, {"chzzk": chzzk, "soop": soop}, clear=True):
            response = self.client.post("/api/status", json={
                "entries": [
                    {"platform": "chzzk", "streamer_id": "abc"},
                    {"platform": "chzzk", "streamer_id": "abc"},  # 중복은 한 번만 조회
                    {"platform": "soop", "streamer_id": "xyz"},
                ]
            })

        self.assertEqual(response.status_code, 200)
        statuses = response.get_json()["statuses"]
        self.assertEqual(len(statuses), 2)
        by_id = {s["streamer_id"]: s for s in statuses}
        self.assertTrue(by_id["abc"]["is_live"])
        self.assertEqual(by_id["abc"]["viewers"], 4282)
        self.assertIsNone(by_id["xyz"]["is_live"])
        chzzk.check_status.assert_called_once_with("abc")

    def test_empty_entries_returns_empty(self):
        response = self.client.post("/api/status", json={"entries": []})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["statuses"], [])


class StreamProxyTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_missing_url_returns_400(self):
        self.assertEqual(self.client.get("/api/stream").status_code, 400)

    def test_rejects_host_outside_allowlist(self):
        # 허용 목록 밖 호스트를 프록시하면 오픈 프록시가 된다
        response = self.client.get("/api/stream?u=https://example.com/master.m3u8")
        self.assertEqual(response.status_code, 403)

    def test_rejects_non_http_scheme(self):
        response = self.client.get("/api/stream?u=file:///etc/passwd")
        self.assertEqual(response.status_code, 403)

    def test_allows_chzzk_navercdn_cdn(self):
        # 치지직은 같은 방송도 CDN을 갈아타며 경로를 돌려준다. 이 호스트가
        # 빠져 있으면 재생이 "Host is not allowed"로 실패한다.
        playlist = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2.0,\nseg0.ts\n"

        with patch.object(app_module, "open_stream") as open_stream:
            open_stream.return_value = _fake_upstream(playlist)
            response = self.client.get(
                "/api/stream?u=https://ex-nlive-streaming.navercdn.com/chzzk/lip2_kr/"
                "cflexnmss2u0006/abc/xyz_playlist.m3u8?hdnts=st=1~exp=2"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/stream?u=", response.get_data(as_text=True))

    def test_allows_cime_ivs_segment_host(self):
        # ci.me는 AWS IVS로 스트림을 내보내며 세그먼트는 마스터와 다른
        # cloudfront.hls.live-video.net 호스트로 나간다. 이게 빠져 있으면
        # 재생이 "Host is not allowed"로 실패한다.
        playlist = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2.0,\nseg0.ts\n"

        with patch.object(app_module, "open_stream") as open_stream:
            open_stream.return_value = _fake_upstream(playlist)
            response = self.client.get(
                "/api/stream?u=https://13e6217ef783.001540a9585c.j.cloudfront.hls."
                "live-video.net/v1/segment/CuMFHIk%2Fv1%2Fsegment%2Fabc.mp4"
            )

        self.assertEqual(response.status_code, 200)

    def test_sends_pandalive_referer_to_ivs_cdn(self):
        # AWS IVS는 방송이 서 있는 사이트 Referer가 없으면 403으로 막는다
        headers = stream_proxy._headers_for("https://abc.us-west-2.playback.live-video.net/api/video/v1/x.m3u8")
        self.assertEqual(headers["Referer"], "https://www.pandalive.co.kr/")
        self.assertEqual(headers["Origin"], "https://www.pandalive.co.kr")

    def test_sends_soop_referer_to_soop_cdn(self):
        headers = stream_proxy._headers_for("https://play.sooplive.com/abc/master.m3u8")
        self.assertEqual(headers["Referer"], "https://play.sooplive.co.kr/")

    def test_sends_no_referer_to_unknown_host(self):
        headers = stream_proxy._headers_for("https://www.pandalive.co.kr/live")
        self.assertNotIn("Referer", headers)

    def test_rewrites_playlist_segments_to_proxy(self):
        playlist = (
            "#EXTM3U\n"
            "#EXT-X-TARGETDURATION:2\n"
            "#EXT-X-MAP:URI=\"init.m4s\"\n"
            "#EXTINF:2.0,\n"
            "seg0.ts\n"
        )

        with patch.object(app_module, "open_stream") as open_stream:
            open_stream.return_value = _fake_upstream(playlist)
            response = self.client.get(
                "/api/stream?u=https://mobile-web.stream.sooplive.com/live/x/auth_playlist.m3u8"
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("/api/stream?u=", body)
        # 상대경로 세그먼트가 프록시 경로로 바뀌어야 hls.js가 우리 origin을 탄다
        self.assertNotIn("\nseg0.ts", body)
        self.assertIn("init.m4s", body)

    def test_passes_segment_through_without_rewriting(self):
        # SOOP은 세그먼트(.TS)에도 m3u8 Content-Type을 주므로 재작성 대상이 아니다
        upstream = _fake_upstream("binary", content_type="application/vnd.apple.mpegurl")

        with patch.object(app_module, "open_stream") as open_stream:
            open_stream.return_value = upstream
            response = self.client.get(
                "/api/stream?u=https://mobile-web.stream.sooplive.com/live/x/seg0.ts"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "video/mp2t")
        self.assertEqual(response.get_data(), b"binary")

    def test_grab_returns_playback_url_for_proxy(self):
        with patch.dict(app_module.platforms, {"chzzk": fake_platform()}):
            response = self.client.get(f"/api/grab?url={CHZZK_URL}&quality=auto")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        # 복사 대상은 원본, 재생 대상은 프록시 주소여야 한다
        self.assertEqual(body["m3u8_url"], FAKE_INFO["m3u8_url"])
        self.assertTrue(body["playback_url"].startswith("/api/stream?u="))

    def test_grab_disables_cache(self):
        # m3u8 URL에는 만료 토큰이 있어, 캐시되면 재시도가 늘 옛 URL을 돌려준다
        with patch.dict(app_module.platforms, {"chzzk": fake_platform()}):
            response = self.client.get(f"/api/grab?url={CHZZK_URL}&quality=auto")

        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.get_json()["m3u8_url"], FAKE_INFO["m3u8_url"])

    def test_upstream_rejection_becomes_bad_gateway(self):
        # 치지직 동시시청 초과는 마스터 요청을 403으로 거절한다.
        # 그대로 흘리면 hls.js가 치명적이지 않은 오류로 삼켜 재시도 UI가 안 뜬다.
        upstream = _fake_upstream("FORBIDDEN", content_type="text/plain")
        upstream.status_code = 403

        with patch.object(app_module, "open_stream") as open_stream:
            open_stream.return_value = upstream
            response = self.client.get(
                "/api/stream?u=https://prod-quote.chzzk.com/live/x/master.m3u8"
            )

        self.assertEqual(response.status_code, 502)


def _fake_upstream(body, content_type="application/vnd.apple.mpegurl"):
    response = Mock()
    response.headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
    response.status_code = 200
    response.raw = Mock()
    response.raw.read.return_value = body.encode("utf-8")
    response.iter_content.return_value = iter([body.encode("utf-8")])
    return response


class StreamShareTokenTests(unittest.TestCase):
    """프록시 링크를 세션 없는 곳(플레이어·다른 브라우저)에서 열 수 있게 하는
    서명 토큰 게이트를 확인한다. 토큰은 그 주소 하나에만 묶인다."""

    UPSTREAM = (
        "https://ex-nlive-streaming.navercdn.com/chzzk/lip2_kr/"
        "cflexnmss2u0006/abc/xyz_playlist.m3u8?hdnts=st=1~exp=2"
    )
    PLAYLIST = "#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2.0,\nseg0.ts\n"

    def setUp(self):
        self.client = app_module.app.test_client()
        # 잠금 켠 상태에서 링크 복사 시나리오를 본다
        state_dir = tempfile.mkdtemp()
        self._env = patch.dict(os.environ, {
            auth_guard.AUTH_ENV: "on",
            auth_guard.SECRET_ENV: "test-secret",
            auth_guard.STATE_ENV: os.path.join(state_dir, "auth.json"),
        })
        self._env.start()
        self.addCleanup(self._env.stop)

    def _proxy_url(self, upstream=None, with_token=True):
        upstream = upstream or self.UPSTREAM
        url = f"/api/stream?u={quote(upstream, safe='')}"
        if with_token:
            url += f"&k={stream_proxy.share_token(upstream)}"
        return url

    def test_share_token_allows_the_signed_url_without_login(self):
        with patch.object(app_module, "open_stream") as open_stream:
            open_stream.return_value = _fake_upstream(self.PLAYLIST)
            response = self.client.get(self._proxy_url())

        self.assertEqual(response.status_code, 200)
        self.assertIn("/api/stream?u=", response.get_data(as_text=True))

    def test_missing_token_still_requires_login(self):
        self.assertEqual(self.client.get(self._proxy_url(with_token=False)).status_code, 401)

    def test_wrong_token_still_requires_login(self):
        url = f"/api/stream?u={quote(self.UPSTREAM, safe='')}&k={'0' * 32}"
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_token_is_bound_to_the_exact_url(self):
        # 주소가 조금만 달라져도 서명이 유효하지 않다. 다른 주소에 원본의 토큰을 붙이면 게이트가 막는다
        other = self.UPSTREAM.replace("abc/", "def/")
        url = f"/api/stream?u={quote(other, safe='')}&k={stream_proxy.share_token(self.UPSTREAM)}"
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_grab_result_url_carries_the_token(self):
        proxy = stream_proxy.build_proxy_url(self.UPSTREAM)
        self.assertIn(f"k={stream_proxy.share_token(self.UPSTREAM)}", proxy)
        self.assertTrue(proxy.startswith("/api/stream?u="))

    def test_token_survives_urls_that_already_contain_encoded_slashes(self):
        # Akamai 토큰이 들어간 실제 주소는 %2F 등 인코딩된 문자가 그대로 들어 있다.
        # args 를 이중 디코드하면 주소가 변조돼 서명이 깨진다(실측).
        upstream = (
            "https://nvelop-livecloud.pstatic.net/chzzk/lip2_kr/abc/xyz/"
            "hdntl=exp=1~acl=*%2Fabc%2F*~hmac=aa/720p/xyz_playlist.m3u8?vp=x"
        )
        with patch.object(app_module, "open_stream") as open_stream:
            open_stream.return_value = _fake_upstream(self.PLAYLIST)
            response = self.client.get(self._proxy_url(upstream=upstream))

        self.assertEqual(response.status_code, 200)


class PlatformHealthApiTests(unittest.TestCase):
    """플랫폼 생존 확인이 '지금 스트림을 받을 수 있는가'를 그대로 답하는지 확인한다"""

    def setUp(self):
        self.client = app_module.app.test_client()
        # 실제 기계의 상태 파일을 건드리지 않도록 임시 파일에 격리한다
        handle, self.state_file = tempfile.mkstemp(prefix="ls-health-test-")
        os.close(handle)
        os.unlink(self.state_file)
        self.env = patch.dict(os.environ, {platform_health.STATE_ENV: self.state_file})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        if os.path.exists(self.state_file):
            os.unlink(self.state_file)

    def test_reports_ok_when_stream_is_fetchable(self):
        chzzk = fake_platform(m3u8_url="https://livecloud.pstatic.net/ab/master.m3u8")
        playlist = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\n720p.m3u8\n"
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True), \
                patch.object(platform_health, "_sample_streamers", return_value=["abc"]), \
                patch.object(platform_health, "open_stream", return_value=_fake_upstream(playlist)):
            response = self.client.get("/api/platforms/health?force=1")

        self.assertEqual(response.status_code, 200)
        entry = response.get_json()["platforms"][0]
        self.assertEqual(entry["platform"], "chzzk")
        self.assertTrue(entry["ok"])
        self.assertEqual(entry["reason"], "")

    def test_marks_blocked_host_as_unavailable(self):
        # 허용 목록에 없는 호스트면 브라우저에서 CORS로 막히므로 사용 불가로 본다
        chzzk = fake_platform(m3u8_url="https://unknown-cdn.example.com/master.m3u8")
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True), \
                patch.object(platform_health, "_sample_streamers", return_value=["abc"]):
            response = self.client.get("/api/platforms/health?force=1")

        entry = response.get_json()["platforms"][0]
        self.assertFalse(entry["ok"])
        self.assertIn("차단", entry["reason"])

    def test_marks_offline_when_no_stream_url(self):
        chzzk = fake_platform(m3u8_url="")
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True), \
                patch.object(platform_health, "_sample_streamers", return_value=["abc"]):
            response = self.client.get("/api/platforms/health?force=1")

        entry = response.get_json()["platforms"][0]
        self.assertFalse(entry["ok"])

    def test_accepts_master_playlist_without_extinf(self):
        # master에는 #EXTINF 대신 #EXT-X-STREAM-INF가 있다. 이걸 걸러내면 안 된다
        chzzk = fake_platform(m3u8_url="https://livecloud.pstatic.net/ab/master.m3u8")
        playlist = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1280x720\n720p.m3u8\n"
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True), \
                patch.object(platform_health, "_sample_streamers", return_value=["abc"]), \
                patch.object(platform_health, "open_stream", return_value=_fake_upstream(playlist)):
            response = self.client.get("/api/platforms/health?force=1")

        self.assertTrue(response.get_json()["platforms"][0]["ok"])

    def test_one_working_candidate_is_enough(self):
        # 후보 중 하나만 성공해도 그 플랫폼은 사용 가능한 것으로 본다
        chzzk = fake_platform(m3u8_url="https://livecloud.pstatic.net/ab/master.m3u8")
        playlist = "#EXTM3U\n#EXTINF:2.0,\nseg0.ts\n"

        def get_live(streamer_id, quality="auto"):
            if streamer_id == "off":
                return {"m3u8_url": ""}
            return {"m3u8_url": "https://livecloud.pstatic.net/ab/master.m3u8"}

        chzzk.get_live.side_effect = get_live
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True), \
                patch.object(platform_health, "_sample_streamers", return_value=["off", "on"]), \
                patch.object(platform_health, "open_stream", return_value=_fake_upstream(playlist)):
            response = self.client.get("/api/platforms/health?force=1")

        self.assertTrue(response.get_json()["platforms"][0]["ok"])

    def test_omits_afreeca_alias(self):
        # soop 과 afreeca 는 같은 플랫폼이라 두 번 보고하면 안 된다
        with patch.dict(app_module.platforms, {"soop": fake_platform(), "afreeca": fake_platform()}, clear=True), \
                patch.object(platform_health, "_sample_streamers", return_value=["abc"]), \
                patch.object(
                    platform_health,
                    "open_stream",
                    return_value=_fake_upstream("#EXTM3U\n#EXTINF:2.0,\nseg0.ts\n"),
                ):
            response = self.client.get("/api/platforms/health?force=1")

        names = [item["platform"] for item in response.get_json()["platforms"]]
        self.assertEqual(names, ["soop"])

    def test_does_not_leak_signed_url_in_reason(self):
        # 실패 사유에 서명된 URL이 그대로 실리면 응답이 통째로 새어나간다
        chzzk = fake_platform(m3u8_url="https://livecloud.pstatic.net/ab/master.m3u8?token=SECRET")
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True), \
                patch.object(platform_health, "_sample_streamers", return_value=["abc"]), \
                patch.object(
                    platform_health, "open_stream",
                    side_effect=platform_health.ProxyError("403 for url=https://cdn.example.com/m.m3u8?token=SECRET"),
                ):
            response = self.client.get("/api/platforms/health?force=1")

        entry = response.get_json()["platforms"][0]
        self.assertFalse(entry["ok"])
        self.assertNotIn("SECRET", entry["reason"])


class PlatformHealthProbeTests(unittest.TestCase):
    """health 조회가 살아 있는 방송 후보를 플랫폼마다 올바르게 고르는지 확인한다"""

    def test_popkon_skips_adult_and_private_broadcasts(self):
        class _Fake:
            @staticmethod
            def post(url, headers=None, json=None, timeout=None):
                return Mock(
                    raise_for_status=Mock(),
                    json=Mock(return_value={"data": {"list": [
                        {"signId": "adult", "partnerCode": "P-00001", "isAdult": 1, "isPrivate": 0},
                        {"signId": "secret", "partnerCode": "P-00001", "isAdult": 0, "isPrivate": 1},
                        {"signId": "ok", "partnerCode": "P-00117", "isAdult": 0, "isPrivate": 0},
                    ]}}),
                )

        with patch.object(platform_health.requests, "post", _Fake.post):
            keys = platform_health._sample_popkon()

        # partnerCode 는 방송마다 다르므로 목록에서 그대로 가져와야 한다
        self.assertEqual(keys, ["ok|P-00117"])

    def test_search_platform_uses_search_results(self):
        chzzk = Mock()
        chzzk.search_lives.return_value = [
            {"streamer_id": "aaa"}, {"streamer_id": "bbb"}, {"streamer_id": ""}
        ]
        ids = platform_health._sample_by_search(chzzk)

        # streamer_id 가 비어 있는 항목은 제외된다
        self.assertEqual(sorted(ids), ["aaa", "bbb"])


class PlatformHealthScheduleTests(unittest.TestCase):
    """새벽 06시 하루 1회 점검과 실패 플랫폼 1시간 재시도를 확인한다.

    시각은 전부 고정값으로 조작하고, 실제 프로브는 _probe_names 패치로 대체한다.
    """

    TZ = ZoneInfo("Asia/Seoul")
    TODAY = "2026-11-08"
    YESTERDAY = "2026-11-07"

    def setUp(self):
        handle, self.state_file = tempfile.mkstemp(prefix="ls-health-sched-")
        os.close(handle)
        os.unlink(self.state_file)
        # 테스트 중에 실제 텔레그램 발송이 나가지 않도록 비워 둔다
        self.env = patch.dict(os.environ, {
            platform_health.STATE_ENV: self.state_file,
            platform_health.TELEGRAM_TOKEN_ENV: "",
            platform_health.TELEGRAM_CHAT_ENV: "",
        })
        self.env.start()
        self.platforms = {"chzzk": Mock(), "soop": Mock()}

    def tearDown(self):
        self.env.stop()
        if os.path.exists(self.state_file):
            os.unlink(self.state_file)

    def _at(self, hour, minute=0, day_offset=0):
        base = datetime(2026, 11, 8, hour, minute, tzinfo=self.TZ)
        return base + timedelta(days=day_offset)

    def _save(self, date, results, retried_at):
        platform_health._save_state({
            "date": date,
            "retried_at": retried_at,
            "results": results,
        })

    @staticmethod
    def _probe_ok(names, platforms):
        return {name: {"ok": True, "reason": ""} for name in names}

    def test_fresh_today_result_is_served_without_probing(self):
        now = self._at(10)
        self._save(self.TODAY, {"chzzk": {"ok": True, "reason": ""}}, now.timestamp())

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names") as probe:
            results = platform_health.get_health(self.platforms)

        probe.assert_not_called()
        self.assertTrue(results["chzzk"]["ok"])

    def test_full_check_runs_after_dawn_when_only_yesterdays_result_exists(self):
        now = self._at(6, minute=30)
        self._save(self.YESTERDAY, {"chzzk": {"ok": True, "reason": ""}},
                   self._at(6, day_offset=-1).timestamp())

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names",
                             side_effect=self._probe_ok) as probe:
            platform_health.get_health(self.platforms)

        self.assertEqual(sorted(probe.call_args.args[0]), ["chzzk", "soop"])
        self.assertEqual(platform_health._load_state()["date"], self.TODAY)

    def test_before_dawn_serves_yesterdays_result_without_probing(self):
        now = self._at(2)
        self._save(self.YESTERDAY, {"soop": {"ok": False, "reason": "지금 방송 중인 방송이 없습니다"}},
                   self._at(6, day_offset=-1).timestamp())

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names") as probe:
            results = platform_health.get_health(self.platforms)

        # 자정~06시는 전일 결과를 그대로 보여주고 점검·재시도 모두 없다
        probe.assert_not_called()
        self.assertFalse(results["soop"]["ok"])

    def test_failed_platform_retries_hourly_and_ok_results_are_kept(self):
        now = self._at(9)
        self._save(self.TODAY, {
            "chzzk": {"ok": True, "reason": ""},
            "soop": {"ok": False, "reason": "지금 방송 중인 방송이 없습니다"},
        }, self._at(7).timestamp())

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names",
                             side_effect=self._probe_ok) as probe:
            results = platform_health.get_health(self.platforms)

        # 성공한 플랫폼은 건드리지 않고 실패한 것만 다시 점검한다
        self.assertEqual(probe.call_args.args[0], ["soop"])
        self.assertTrue(results["soop"]["ok"])
        self.assertTrue(results["chzzk"]["ok"])
        state = platform_health._load_state()
        self.assertTrue(state["results"]["soop"]["ok"])
        self.assertEqual(state["date"], self.TODAY)

    def test_retry_waits_a_full_hour(self):
        now = self._at(9)
        self._save(self.TODAY, {"soop": {"ok": False, "reason": "x"}},
                   self._at(8, minute=30).timestamp())  # 30분 전 — 아직 이르다

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names") as probe:
            platform_health.get_health(self.platforms)

        probe.assert_not_called()

    def test_force_probes_everything_even_when_fresh(self):
        now = self._at(10)
        self._save(self.TODAY, {"chzzk": {"ok": True, "reason": ""}}, now.timestamp())

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names",
                             side_effect=self._probe_ok) as probe:
            platform_health.get_health(self.platforms, force=True)

        probe.assert_called_once()
        self.assertEqual(sorted(probe.call_args.args[0]), ["chzzk", "soop"])

    def test_daily_check_result_is_sent_to_telegram(self):
        now = self._at(6, minute=30)
        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names",
                             side_effect=self._probe_ok), \
                patch.object(platform_health, "_send_telegram") as send:
            platform_health.get_health(self.platforms)

        send.assert_called_once()
        text = send.call_args.args[0]
        self.assertIn("플랫폼 점검", text)
        self.assertIn("치지직", text)  # chzzk 의 화면 이름
        self.assertIn("SOOP", text)
        self.assertIn("2/2", text)

    def test_force_check_does_not_send_telegram(self):
        now = self._at(10)
        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names",
                             side_effect=self._probe_ok), \
                patch.object(platform_health, "_send_telegram") as send:
            platform_health.get_health(self.platforms, force=True)

        # force=1 은 운영자가 직접 거는 확인이라 자동 발송하지 않는다
        send.assert_not_called()

    def test_recovery_of_failed_platform_sends_alert(self):
        now = self._at(9)
        self._save(self.TODAY, {"soop": {"ok": False, "reason": "지금 방송 중인 방송이 없습니다"}},
                   self._at(7).timestamp())

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names",
                             side_effect=self._probe_ok), \
                patch.object(platform_health, "_send_telegram") as send:
            platform_health.get_health(self.platforms)

        send.assert_called_once()
        text = send.call_args.args[0]
        self.assertIn("복구", text)
        self.assertIn("SOOP", text)

    def test_still_failing_retry_sends_nothing(self):
        now = self._at(9)
        self._save(self.TODAY, {"soop": {"ok": False, "reason": "x"}},
                   self._at(7).timestamp())

        def fail(names, platforms):
            return {name: {"ok": False, "reason": "x"} for name in names}

        with patch.object(platform_health, "_now", return_value=now), \
                patch.object(platform_health, "_probe_names", side_effect=fail), \
                patch.object(platform_health, "_send_telegram") as send:
            platform_health.get_health(self.platforms)

        # 여전히 실패라면 복구 알림도 없다
        send.assert_not_called()

    def test_telegram_sender_skips_when_not_configured(self):
        with patch.dict(os.environ, {
            platform_health.TELEGRAM_TOKEN_ENV: "",
            platform_health.TELEGRAM_CHAT_ENV: "",
        }), patch.object(platform_health.requests, "post") as post:
            sent = platform_health._send_telegram("hi")

        self.assertFalse(sent)
        post.assert_not_called()

    def test_telegram_sender_posts_html(self):
        with patch.dict(os.environ, {
            platform_health.TELEGRAM_TOKEN_ENV: "tok",
            platform_health.TELEGRAM_CHAT_ENV: "1",
        }), patch.object(platform_health, "TELEGRAM_RETRY_DELAY_SECONDS", 0), \
                patch.object(platform_health.requests, "post") as post:
            post.return_value = Mock(ok=True, status_code=200)
            sent = platform_health._send_telegram("<b>hi</b>")

        self.assertTrue(sent)
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_id"], "1")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertEqual(payload["text"], "<b>hi</b>")


class AuthGuardTests(unittest.TestCase):
    """인증번호 잠금은 APP_AUTH 로 켜지고 꺼진다.

    인증번호는 APP_PASSWORD 가 아니라 상태 파일의 날짜별 키로 관리된다.
    오늘자·전일자 두 인증번호를 모두 허용한다.
    """

    # 오늘자로 심어 두는 고정 인증번호. 오답과 구분되도록 6자리로 잡는다.
    TODAY_PIN = "111111"
    YESTERDAY_PIN = "222222"
    WRONG_PIN = "999999"

    def setUp(self):
        handle, self.state_file = tempfile.mkstemp(prefix="ls-auth-test-")
        os.close(handle)
        os.unlink(self.state_file)  # 빈 상태 파일로 시작
        self.env = patch.dict(
            os.environ,
            {"APP_AUTH": "on", "APP_STATE_FILE": self.state_file},
        )
        self.env.start()
        self.client = app_module.app.test_client()
        self._seed_password(self.TODAY_PIN)

    def tearDown(self):
        self.env.stop()
        if os.path.exists(self.state_file):
            os.unlink(self.state_file)

    def _seed_password(self, pin, date=None):
        """상태 파일에 특정 날짜의 인증번호를 심는다.

        백그라운드 갱신 스레드와 겹치지 않도록 같은 파일 락 안에서 쓴다.
        """
        date = date or auth_guard._date_str()
        with auth_guard._locked_state() as state:
            state["passwords"][date] = pin
        return date

    def _passwords(self):
        with auth_guard._locked_state() as state:
            return dict(state["passwords"])

    def _nonce(self):
        response = self.client.get("/api/auth/challenge")
        self.assertEqual(response.status_code, 200)
        return response.json["nonce"]

    def _login(self, password=None, nonce=None):
        password = self.TODAY_PIN if password is None else password
        nonce = self._nonce() if nonce is None else nonce
        proof = hashlib.sha256(f"{password}:{nonce}".encode()).hexdigest()
        return self.client.post(
            "/api/auth/login", json={"nonce": nonce, "proof": proof}
        )

    def test_session_reports_locked_before_login(self):
        response = self.client.get("/api/auth/session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"authed": False, "enabled": True})

    def test_api_is_blocked_until_login(self):
        with patch.object(app_module, "get_health", return_value={}):
            for method, url in [
                ("get", "/api/platforms/health"),
                ("get", "/api/search?q=테스트"),
                ("get", "/api/stream?u=https://example.com/a.m3u8"),
                ("post", "/api/status"),
            ]:
                response = getattr(self.client, method)(url)
                self.assertEqual(response.status_code, 401, url)
                self.assertTrue(response.json.get("auth_required"))

    def test_wrong_password_is_rejected(self):
        response = self._login(password=self.WRONG_PIN)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json["error"], "invalid_password")

    def test_correct_password_unlocks_and_persists_in_session(self):
        self.assertEqual(self._login().status_code, 200)
        self.assertTrue(self.client.get("/api/auth/session").json["authed"])

    def test_api_works_after_login(self):
        with patch.object(app_module, "get_health", return_value={}):
            self._login()
            response = self.client.get("/api/platforms/health?force=1")
        self.assertEqual(response.status_code, 200)

    def test_nonce_cannot_be_replayed(self):
        # 같은 증명으로 두 번 시도하면 안 된다. 도청한 값을 되쏘아도 뚫리면 안 된다.
        nonce = self._nonce()
        first = self._login(nonce=nonce)
        self.assertEqual(first.status_code, 200)
        second = self._login(nonce=nonce)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(second.json["error"], "stale_nonce")

    def test_nonce_is_consumed_even_on_failure(self):
        nonce = self._nonce()
        self.assertEqual(self._login(password=self.WRONG_PIN, nonce=nonce).status_code, 401)
        # 틀린 시도가 nonce 를 태워 버린다
        self.assertEqual(self._login(nonce=nonce).status_code, 400)

    def test_expired_nonce_is_rejected(self):
        nonce = self._nonce()
        with patch.object(auth_guard.time, "time", return_value=time.time() + 61):
            response = self._login(nonce=nonce)
        self.assertEqual(response.status_code, 400)

    def test_missing_proof_is_rejected(self):
        nonce = self._nonce()
        response = self.client.post("/api/auth/login", json={"nonce": nonce})
        self.assertEqual(response.status_code, 401)

    def test_five_failures_lock_out_for_ten_minutes(self):
        for attempt in range(auth_guard.MAX_ATTEMPTS):
            response = self._login(password=self.WRONG_PIN)
            self.assertEqual(response.status_code, 401, f"attempt {attempt}")
            self.assertEqual(response.json["attempts_left"], auth_guard.MAX_ATTEMPTS - attempt - 1)

        locked = self._login()
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json["lockout_minutes"], 10)
        self.assertGreater(locked.json["retry_after"], 9 * 60)
        # 잠금 중에도 맞는 비밀번호는 통과시키지 않는다
        self.assertEqual(self._login().status_code, 429)

    def _run_lockout_at(self, elapsed):
        """elapsed 초 시점에서 실패를 채워 잠금을 걸고, 걸린 시간을 돌려준다."""
        with patch.object(auth_guard.time, "time", return_value=time.time() + elapsed):
            for _ in range(auth_guard.MAX_ATTEMPTS):
                self._login(password=self.WRONG_PIN)
            blocked = self._login()
        self.assertEqual(blocked.status_code, 429)
        return blocked.json["lockout_minutes"]

    def test_lockout_grows_with_repeated_failures(self):
        minutes = []
        elapsed = 0.0
        for _ in range(4):
            minutes.append(self._run_lockout_at(elapsed))
            # 잠금이 끝난 뒤로 시간을 넘겨 다음 단계를 본다
            elapsed += minutes[-1] * 61
        self.assertEqual(minutes, [10, 20, 40, 80])

    def test_lockout_is_capped(self):
        minutes = []
        elapsed = 0.0
        for _ in range(10):
            minutes.append(self._run_lockout_at(elapsed))
            elapsed += minutes[-1] * 61
        self.assertEqual(minutes[-1], auth_guard.MAX_LOCKOUT_MINUTES)
        # 중간에 잘리지 않고 계속 증가한다
        self.assertEqual(minutes[:-1], sorted(minutes[:-1]))

    def test_success_resets_the_failure_counter(self):
        for _ in range(auth_guard.MAX_ATTEMPTS - 1):
            self._login(password=self.WRONG_PIN)
        self.assertEqual(self._login().status_code, 200)

        # 누적은 초기화됐으므로 다시 4번까지만 틀려도 잠기지 않는다
        for _ in range(auth_guard.MAX_ATTEMPTS - 1):
            response = self._login(password=self.WRONG_PIN)
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self._login().status_code, 200)

    def test_success_after_lockout_clears_the_record(self):
        for _ in range(auth_guard.MAX_ATTEMPTS):
            self._login(password=self.WRONG_PIN)
        self.assertEqual(self._login().status_code, 429)

        with patch.object(auth_guard.time, "time", return_value=time.time() + 11 * 60):
            self.assertEqual(self._login().status_code, 200)
        # 누적 횟수가 0으로 돌아갔는지 다음 실패가 4회째까지 잠기지 않는지로 본다
        self.assertEqual(self._login(password=self.WRONG_PIN).json["attempts_left"], 4)

    def test_logout_locks_again(self):
        self._login()
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertFalse(self.client.get("/api/auth/session").json["authed"])

    def test_guard_can_be_disabled(self):
        # APP_AUTH=off 면 잠금을 걸지 않는다. 개발 중 설정을 잊어도 앱은 돌아간다.
        with patch.dict(os.environ, {"APP_AUTH": "off"}):
            self.assertFalse(auth_guard.is_enabled())
            with patch.object(app_module, "get_health", return_value={}):
                self.assertEqual(self.client.get("/api/platforms/health?force=1").status_code, 200)

    def test_yesterday_password_is_accepted(self):
        # 방송이 새벽까지 이어지므로 어제 인증번호도 하루 더 통과한다.
        yesterday = auth_guard._date_str(auth_guard._now() - timedelta(days=1))
        self._seed_password(self.YESTERDAY_PIN, date=yesterday)
        self.assertEqual(self._login(self.YESTERDAY_PIN).status_code, 200)

    def test_password_older_than_yesterday_is_rejected_and_pruned(self):
        day_before = auth_guard._date_str(auth_guard._now() - timedelta(days=2))
        self._seed_password("333333", date=day_before)

        response = self._login("333333")
        self.assertEqual(response.status_code, 401)
        # 그제 인증번호는 갱신 과정에서 상태 파일에서도 지워진다
        self.assertNotIn(day_before, self._passwords())

    def test_rotation_generates_six_digit_password_and_prunes(self):
        # 오늘 키가 없는 상태(자정 직후·상태 파일 초기화)에서 갱신이 일어난다.
        yesterday = auth_guard._date_str(auth_guard._now() - timedelta(days=1))
        self._seed_password(self.YESTERDAY_PIN, date=yesterday)

        # 갱신 함수는 잠금 스위치를 보지 않으므로, 백그라운드 스레드가 끼어들지
        # 않도록 APP_AUTH=off 에서 직접 부른다.
        with patch.dict(os.environ, {"APP_AUTH": "off"}):
            with auth_guard._locked_state() as state:
                state["passwords"].pop(auth_guard._date_str(), None)
            rotated, today_pin, yesterday_pin = auth_guard.ensure_today_password()

        self.assertTrue(rotated)
        self.assertEqual(len(today_pin), auth_guard.PIN_LENGTH)
        self.assertTrue(today_pin.isdigit())
        self.assertEqual(yesterday_pin, self.YESTERDAY_PIN)
        # 오늘과 어제 두 개만 남는다
        self.assertEqual(
            sorted(self._passwords()),
            sorted([auth_guard._date_str(), yesterday]),
        )

    def test_rotation_is_idempotent(self):
        with patch.dict(os.environ, {"APP_AUTH": "off"}):
            with auth_guard._locked_state() as state:
                state["passwords"].pop(auth_guard._date_str(), None)
            first = auth_guard.ensure_today_password()
            second = auth_guard.ensure_today_password()

        self.assertTrue(first[0])
        self.assertFalse(second[0])
        self.assertEqual(first[1], second[1])

    def test_notify_sends_new_password_to_telegram(self):
        with patch.dict(os.environ, {
            auth_guard.TELEGRAM_TOKEN_ENV: "test-token",
            auth_guard.TELEGRAM_CHAT_ENV: "12345",
        }), patch.object(auth_guard.requests, "post") as post:
            post.return_value = Mock(ok=True, status_code=200)
            sent = auth_guard._notify_sync("2026-11-05", "111111", "222222")

        self.assertTrue(sent)
        post.assert_called_once()
        self.assertIn("bottest-token/sendMessage", post.call_args.args[0])
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_id"], "12345")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("<code>111111</code>", payload["text"])
        self.assertIn("<code>222222</code>", payload["text"])

    def test_notify_failure_keeps_password_usable(self):
        # 발송이 실패해도 갱신은 끝나고, 새 인증번호는 상태 파일에 남는다.
        with patch.dict(os.environ, {
            auth_guard.TELEGRAM_TOKEN_ENV: "test-token",
            auth_guard.TELEGRAM_CHAT_ENV: "12345",
        }), patch.object(auth_guard, "TELEGRAM_RETRY_DELAY_SECONDS", 0), \
             patch.object(auth_guard.requests, "post",
                          side_effect=auth_guard.requests.RequestException("boom")):
            sent = auth_guard._notify_sync("2026-11-05", "111111", None)

        self.assertFalse(sent)
        self.assertEqual(self._passwords().get(auth_guard._date_str()), self.TODAY_PIN)

    def test_notify_without_telegram_config_skips_api(self):
        with patch.dict(os.environ, {
            auth_guard.TELEGRAM_TOKEN_ENV: "",
            auth_guard.TELEGRAM_CHAT_ENV: "",
        }), patch.object(auth_guard.requests, "post") as post:
            sent = auth_guard._notify_sync("2026-11-05", "111111", None)

        self.assertFalse(sent)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
