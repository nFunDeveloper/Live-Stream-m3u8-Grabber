#!/usr/bin/env python3
"""플랫폼 × 화질 매트릭스 점검 스크립트. 사용법은 tests/QUALITY_TEST_GUIDE.md.

개발 서버가 돌아가는 상태에서 실행한다:

    python3 tests/quality_matrix_probe.py --pin 123456               # 전체 플랫폼
    python3 tests/quality_matrix_probe.py --pin 123456 --platform chzzk
    # 인증번호(--pin)는 매일 00시에 바뀐다. 백엔드 로그나 관리용 텔레그램에서 확인

외부 의존성이 없다(requests/flask 아님). 인증 로그인, 검색으로 라이브 채널 찾기,
화질별 grab, 받은 플레이리스트가 실제로 열리는지까지 한 번에 본다.

각 조합을 이렇게 판정한다.
  OK       : grab 응답에 m3u8_url 이 있고, playback_url 이 실제로 열리며
             플레이리스트(#EXTM3U)가 내려온다
  404/400  : 백엔드가 주소를 만들지 못했다 — URL 조합 로직 문제
  OK(ABR)  : 받은 게 master 플레이리스트. 이 플랫폼은 특정 화질을 못 주고
             ABR 에 맡긴다는 뜻으로, RESOLUTION 목록을 같이 출력한다
  채널 없음: 지금 라이브 중인 방송이 없어 검증 불가 (문제가 아니라 실험실패)
"""

import argparse
import base64
import hashlib
import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.request
import urllib.parse

# ui/src/lib/qualities.js 의 PLATFORM_QUALITIES 와 같은 값을 유지한다.
PLATFORM_QUALITIES = {
    "chzzk": ["auto", "1080p", "720p", "540p", "480p", "360p", "144p"],
    "cime": ["auto", "720p", "540p", "480p", "360p"],
    "pandalive": ["auto", "720p", "540p", "480p", "360p"],
    "popkon": ["auto", "720p", "540p", "480p", "360p"],
    "soop": ["auto", "540p", "480p", "360p"],
}

# 검색 하나가 0을 돌려주는 경우가 많아 키워드를 순서대로 건져본다.
# 플랫폼마다 시청자 분포가 달라서 넓게 잡는다. 이때 로그인 쿠키가 필요하다.
SEARCH_KEYWORDS = [
    "방송", "게임", "음악", "라이브", "리그", "카지노", "소셜", "일상", "노래", "여행",
]
GRAB_TIMEOUT = 30
FETCH_TIMEOUT = 20


class Client:
    """개발 서버에 로그인해 두고 grab/프록시를 부른다."""

    def __init__(self, base, pin):
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.base = base.rstrip("/")
        self._login(pin)

    def _post_json(self, path, payload):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/json"},
        )
        return self.opener.open(req, timeout=15)

    def get(self, path, timeout=GRAB_TIMEOUT):
        req = urllib.request.Request(self.base + path)
        return self.opener.open(req, timeout=timeout)

    def _login(self, pin):
        """nonce 를 받아 sha256(pin:nonce) 를 제출한다. 프론트 lib/auth.js 와 동일."""
        with self.opener.open(self.base + "/api/auth/challenge", timeout=15) as resp:
            nonce = json.load(resp)["nonce"]
        proof = hashlib.sha256(f"{pin}:{nonce}".encode()).hexdigest()
        with self._post_json("/api/auth/login", {"nonce": nonce, "proof": proof}) as resp:
            body = json.load(resp)
        if not body.get("ok"):
            raise SystemExit(f"로그인 실패: {body}")

    def search_one_live(self, platform):
        """검색 키워드를 몇 개 돌려 그 플랫폼의 살아있는 방송 하나를 얻는다."""
        for keyword in SEARCH_KEYWORDS:
            q = urllib.parse.quote(keyword)
            try:
                with self.get(f"/api/search?q={q}", timeout=30) as resp:
                    results = json.load(resp).get("results", [])
            except Exception as e:
                print(f"    검색 실패 {platform} keyword={keyword}: {e}")
                continue
            for item in results:
                if item.get("platform") == platform and item.get("url"):
                    return item
        return None

    def grab(self, url, quality):
        """m3u8_url 을 뽑아 playback_url 이 진짜 플레이리스트로 열리는지 확인한다."""
        q = urllib.parse.quote(url, safe="")
        try:
            with self.get(f"/api/grab?url={q}&quality={quality}") as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read()[:120].decode("utf-8", "ignore")
            try:
                detail = json.loads(detail).get("error", detail)
            except Exception:
                pass
            return f"{e.code}", None, detail
        except Exception as e:
            return "ERR", None, str(e)[:80]

        m3u8 = body.get("m3u8_url") or ""
        playback = body.get("playback_url") or ""
        if not m3u8:
            return "no-url", None, body.get("error", "빈 m3u8_url")

        kind, extra = self._read_playlist(playback)
        return "OK" if kind else "bad-m3u8", m3u8, extra

    def _read_playlist(self, url):
        """프록시 경로를 열어 master 인지 chunklist 인지, 해상도가 뭔지 본다."""
        if url.startswith("/"):
            url = self.base + url   # playback_url 은 /api/stream?u=... 형태의 상대경로
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with self.opener.open(req, timeout=FETCH_TIMEOUT) as resp:
            text = resp.read(20000).decode("utf-8", "ignore")
        if not text.startswith("#EXTM3U"):
            return "", "플레이리스트 아님"

        resolutions = re.findall(r"RESOLUTION=(\d+x\d+)", text)
        if resolutions:
            return "master", ",".join(resolutions)
        return "chunklist", ""


def run(base, pin, only):
    client = Client(base, pin)
    platforms = [only] if only else list(PLATFORM_QUALITIES)
    print(f"대상: {base}  플랫폼: {', '.join(platforms)}\n")

    rows = []
    for platform in platforms:
        item = client.search_one_live(platform)
        if not item:
            rows.append((platform, "-", "채널 없음", "", ""))
            continue
        label = f"{item.get('platform')}/{item.get('streamer_id', '')[:8]} {item.get('url', '')}"
        print(f"▼ {platform} — {label}")

        for quality in PLATFORM_QUALITIES.get(platform, ["auto"]):
            status, m3u8, extra = client.grab(item["url"], quality)
            note = extra or ""
            # master 가 아니면(= 특정 화질을 직접 줬으면) 주소에 화질이 담겼는지 확인
            if status == "OK" and m3u8 and not note:
                note = f"/{quality}/" if f"/{quality}/" in m3u8 else ""
            rows.append((platform, quality, status, m3u8, note))
            shown = m3u8.rsplit("/", 1)[-1][:44] if m3u8 else ""
            print(f"    {quality:6} {status:9} {note:46} {shown}")
    return rows


def main():
    parser = argparse.ArgumentParser(description="플랫폼별 화질 매트릭스 테스트")
    parser.add_argument("--base", default="http://127.0.0.1:10000")
    parser.add_argument("--pin", required=True,
                        help="현재 인증번호 (백엔드 로그 또는 관리용 텔레그램에서 확인)")
    parser.add_argument("--platform", default=None, help="한 플랫폼만 (chzzk/cime/...)")
    args = parser.parse_args()

    rows = run(args.base, args.pin, args.platform)

    print("\n===== 요약 =====")
    print(f"{'플랫폼':11} {'화질':6} {'결과':9} 비고")
    for platform, quality, status, _m3u8, note in rows:
        print(f"{platform:11} {quality:6} {status:9} {note[:40]}")


if __name__ == "__main__":
    main()