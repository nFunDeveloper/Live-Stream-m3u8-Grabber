import os
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import app as app_module


CHZZK_URL = "https://chzzk.naver.com/live/test_channel"


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

    def test_success_returns_m3u8_url(self):
        fake_platform = Mock()
        fake_platform.get_live.return_value = "https://cdn.example.com/master.m3u8"
        with patch.dict(app_module.platforms, {"chzzk": fake_platform}):
            response = self.client.get(f"/api/grab?url={CHZZK_URL}&quality=720p")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["m3u8_url"], "https://cdn.example.com/master.m3u8")
        self.assertEqual(body["platform"], "chzzk")
        self.assertEqual(body["streamer_id"], "test_channel")
        self.assertEqual(body["quality"], "720p")
        fake_platform.get_live.assert_called_once_with("test_channel", "720p")

    def test_popkon_stream_key_uses_cast_and_partner_code(self):
        fake_platform = Mock()
        fake_platform.get_live.return_value = "https://cdn.example.com/master.m3u8"
        url = "https://www.popkontv.com/live/view?castId=123&partnerCode=ABC"
        with patch.dict(app_module.platforms, {"popkon": fake_platform}):
            response = self.client.get(f"/api/grab?url={quote(url, safe='')}")

        self.assertEqual(response.status_code, 200)
        fake_platform.get_live.assert_called_once_with("123|ABC", "auto")

    def test_permission_error_returns_403(self):
        fake_platform = Mock()
        fake_platform.get_live.side_effect = PermissionError("성인 인증이 필요한 방송입니다.")
        with patch.dict(app_module.platforms, {"chzzk": fake_platform}):
            response = self.client.get(f"/api/grab?url={CHZZK_URL}")

        self.assertEqual(response.status_code, 403)
        self.assertIn("성인 인증", response.get_json()["error"])

    def test_value_error_returns_400_with_message(self):
        fake_platform = Mock()
        fake_platform.get_live.side_effect = ValueError(
            "Popkon stream key must include castId and partnerCode."
        )
        url = "https://www.popkontv.com/live/view?castId=123&partnerCode=ABC"
        with patch.dict(app_module.platforms, {"popkon": fake_platform}):
            response = self.client.get(f"/api/grab?url={quote(url, safe='')}")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"],
            "Popkon stream key must include castId and partnerCode.",
        )


class LegacyRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_success_redirects_to_m3u8(self):
        fake_platform = Mock()
        fake_platform.get_live.return_value = "https://cdn.example.com/master.m3u8"
        with patch.dict(app_module.platforms, {"chzzk": fake_platform}):
            response = self.client.get("/chzzk/test_channel/720p")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://cdn.example.com/master.m3u8")

    def test_empty_m3u8_returns_404(self):
        fake_platform = Mock()
        fake_platform.get_live.return_value = ""
        with patch.dict(app_module.platforms, {"chzzk": fake_platform}):
            response = self.client.get("/chzzk/test_channel/720p")

        self.assertEqual(response.status_code, 404)

    def test_unknown_platform_returns_404(self):
        response = self.client.get("/nosuch/channel/720p")
        self.assertEqual(response.status_code, 404)

    def test_value_error_returns_400(self):
        fake_platform = Mock()
        fake_platform.get_live.side_effect = ValueError(
            "Popkon stream key must include castId and partnerCode."
        )
        with patch.dict(app_module.platforms, {"popkon": fake_platform}):
            response = self.client.get("/popkon/123/720p")

        self.assertEqual(response.status_code, 400)


class DetectRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()

    def test_success_redirects_to_m3u8(self):
        fake_platform = Mock()
        fake_platform.get_live.return_value = "https://cdn.example.com/master.m3u8"
        with patch.dict(app_module.platforms, {"chzzk": fake_platform}):
            response = self.client.get(f"/detect/auto?url={CHZZK_URL}")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "https://cdn.example.com/master.m3u8")

    def test_not_live_returns_404(self):
        fake_platform = Mock()
        fake_platform.get_live.return_value = ""
        with patch.dict(app_module.platforms, {"chzzk": fake_platform}):
            response = self.client.get(f"/detect/auto?url={CHZZK_URL}")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
