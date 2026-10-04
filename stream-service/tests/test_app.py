import os
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import app as app_module


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


if __name__ == "__main__":
    unittest.main()
