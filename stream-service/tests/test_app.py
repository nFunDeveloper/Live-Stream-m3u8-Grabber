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
        soop = Mock(spec=app_module.Soop)  # search_lives 미구현 플랫폼
        with patch.dict(app_module.platforms, {"chzzk": chzzk, "cime": cime, "soop": soop}, clear=True):
            response = self.client.get("/api/search?q=%EA%B2%8C%EC%9E%84")

        self.assertEqual(response.status_code, 200)
        results = response.get_json()["results"]
        self.assertEqual(len(results), 2)
        # 시청자 수 내림차순 정렬
        self.assertEqual(results[0]["platform"], "cime")
        chzzk.search_lives.assert_called_once()
        self.assertFalse(hasattr(soop, "search_lives"))  # 미구현 플랫폼은 검색 대상 아님

    def test_search_swallows_platform_failure(self):
        chzzk = Mock(spec=app_module.Chzzk)
        chzzk.search_lives.side_effect = RuntimeError("api down")
        with patch.dict(app_module.platforms, {"chzzk": chzzk}, clear=True):
            response = self.client.get("/api/search?q=game")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["results"], [])


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


if __name__ == "__main__":
    unittest.main()
