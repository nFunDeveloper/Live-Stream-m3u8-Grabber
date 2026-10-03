import json
import logging
import os
import re

import requests

from platform_modules.platform_default import PlatformDefault


logger = logging.getLogger(__name__)


class Popkon(PlatformDefault):
    platform = "PopkonParser"
    version = "1.0.0"

    origin = "https://www.popkontv.com"
    watch_api_url = f"{origin}/api/proxy/broadcast/v1/castwatchonoffguest"
    client_key = os.getenv("POPKON_CLIENT_KEY", "Client FpAhe6mh8Qtz116OENBmRddbYVirNKasktdXQiuHfm88zRaFydTsFy63tzkdZY0u")
    app_version = "4.6.2"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": origin,
        "Referer": f"{origin}/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
    }
    playlist_headers = {
        "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*",
        "User-Agent": headers["User-Agent"],
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

    def get_live(self, stream_key, quality="auto"):
        super().get_live()
        normalized_quality = self.quality_list.get(quality)
        if not normalized_quality:
            logger.warning("[popkon] unsupported quality=%s", quality)
            return ""

        cast_id, partner_code = self.__parse_stream_key(stream_key)
        live_info = self.__request_page_live_info(cast_id, partner_code)
        if not live_info:
            logger.warning("[popkon] live info not found cast_id=%s partner_code=%s", cast_id, partner_code)
            return ""

        if str(live_info.get("isAdult", "0")) == "1":
            raise PermissionError("성인 인증이 필요한 방송입니다.")

        watch_info = self.__request_watch_info(cast_id, partner_code, live_info)
        logger.info(
            "[popkon] watch status=%s message=%s data=%s",
            watch_info.get("statusCd"),
            watch_info.get("statusMsg"),
            watch_info.get("data", {}),
        )

        status_code = watch_info.get("statusCd")
        if status_code != "L0000":
            message = watch_info.get("statusMsg") or "Live stream is not available."
            if status_code in ("L000A", "E4001", "E4100", "E4101", "E4102"):
                raise PermissionError(message)

            return ""

        playlist_url = watch_info.get("data", {}).get("castHlsUrl")
        if not playlist_url:
            logger.warning("[popkon] playlist url not found response=%s", watch_info)
            return ""

        if normalized_quality == "auto":
            return playlist_url

        variant_url = self.get_variant_url_from_master(playlist_url, normalized_quality, self.playlist_headers)
        return variant_url or playlist_url

    def __parse_stream_key(self, stream_key):
        parts = stream_key.split("|", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError("Popkon stream key must include castId and partnerCode.")

        return parts[0], parts[1]

    def __request_page_live_info(self, cast_id, partner_code):
        url = f"{self.origin}/live/view?castId={cast_id}&partnerCode={partner_code}"
        response = self.session.get(url, headers={**self.headers, "Referer": self.origin}, timeout=10)
        response.raise_for_status()

        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            response.text,
            re.DOTALL,
        )
        if not match:
            return {}

        next_data = json.loads(match.group(1))
        page_props = next_data.get("props", {}).get("pageProps", {})
        mc_data = page_props.get("mcData") or {}
        if mc_data.get("statusCd") != "S2000":
            logger.warning("[popkon] mcData unavailable response=%s", mc_data)
            return {}

        data = mc_data.get("data") or {}
        return {
            **data,
            "isAdult": page_props.get("isAdult", data.get("isAdult", "0")),
        }

    def __request_watch_info(self, cast_id, partner_code, live_info):
        cast_start_date = live_info.get("mc_castStartDate")
        cast_partner_code = live_info.get("mc_partnerCode") or partner_code
        cast_type = str(live_info.get("castType", "0"))
        if not cast_start_date:
            logger.warning("[popkon] cast start date missing live_info=%s", live_info)
            return {}

        payload = {
            "androidStore": 0,
            "castCode": f"{cast_id}-{cast_start_date}",
            "castPartnerCode": cast_partner_code,
            "castSignId": cast_id,
            "castType": cast_type,
            "commandType": 0,
            "exePath": 0,
            "partnerCode": partner_code,
            "password": "",
            "version": self.app_version,
        }
        response = self.session.post(
            self.watch_api_url,
            headers={
                **self.headers,
                "ClientKey": self.client_key,
                "Referer": f"{self.origin}/live/view?castId={cast_id}&partnerCode={partner_code}",
            },
            data=json.dumps(payload),
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
