"""CORS로 막힌 플랫폼 스트림을 브라우저에서 재생하기 위한 프록시.

SOOP CDN은 자신의 도메인에서만 Access-Control-Allow-Origin을 내려줘서
hls.js의 세그먼트 요청이 실패한다. 이 모듈은 플레이리스트와 세그먼트를
같은 origin(=우리 백엔드)으로 다시 노출해 CORS를 우회한다.
"""
import logging
import re
from urllib.parse import urljoin, urlparse

import requests

logger = logging.getLogger(__name__)

# 이 목록에 없는 호스트로 요청하면 안 된다 — 아무 URL이나 끌어올 수 있는
# 오픈 프록시가 되어 버리기 때문이다(SRF 방지).
ALLOWED_HOST_SUFFIXES = (
    'sooplive.com',
    'sooplive.co.kr',
    'afreeca.tv',
    'naver.com',
    'pstatic.net',
    'navercorp.com',
    'ci.me',
    'pandalive.co.kr',
    'popkontv.com',
)

USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
)

# ORIGIN이 포함된 태그의 URI="..." 속성. 이 안에 있는 상대경로도 재작성해야 한다.
URI_ATTRIBUTE_PATTERN = re.compile(r'URI="([^"]*)"')

# 재귀적으로 플레이리스트가 서로를 가리키면 무한히 깊어질 수 있어 제한한다.
MAX_PLAYLIST_REWRITE_DEPTH = 4

# 세그먼트 하나는 통상 1~10MB. 큰 응답을 메모리에 다 받지 않도록 상한을 둔다.
MAX_PLAYLIST_BYTES = 4 * 1024 * 1024

REQUEST_TIMEOUT = (5, 20)


class ProxyError(Exception):
    """프록시로 처리할 수 없는 요청."""


class ProxyForbidden(ProxyError):
    """허용 목록에 없는 호스트."""


def is_allowed_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        return False

    hostname = (parsed.hostname or '').lower()
    if not hostname:
        return False

    return any(
        hostname == suffix or hostname.endswith('.' + suffix)
        for suffix in ALLOWED_HOST_SUFFIXES
    )


def build_proxy_url(target_url):
    """프론트가 hls.js에 넘길 프록시 URL을 만든다."""
    from urllib.parse import quote

    return '/api/stream?u=' + quote(target_url, safe='')


def _referer_for(url):
    """SOOP CDN은 SOOP 플레이어 Referer가 있어야 응답한다."""
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if host.endswith('sooplive.com') or host.endswith('sooplive.co.kr') or host.endswith('afreeca.tv'):
        return 'https://play.sooplive.co.kr/'
    return None


def _headers_for(url, range_header=None):
    headers = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
    referer = _referer_for(url)
    if referer:
        headers['Referer'] = referer
        headers['Origin'] = 'https://play.sooplive.co.kr'
    if range_header:
        # 바이트 범위 요청은 그대로 전달해야 탐색 없이 이어재생된다
        headers['Range'] = range_header
    return headers


def rewrite_playlist(text, base_url):
    """플레이리스트 안의 상대경로를 모두 프록시 URL로 바꾼다.

    hls.js는 세그먼트를 원본 CDN으로 직접 요청하므로, 상대경로를 그대로 두면
    프록시가 아니라 브라우저가 CORS에 막힌다.
    """
    lines = text.splitlines()
    rewritten = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith('#'):
            # #EXT-X-MAP/KEY/PART/MEDIA 등의 URI="..." 속성도 함께 재작성한다
            def replace_attribute(match):
                target = match.group(1)
                if not target:
                    return match.group(0)
                return 'URI="%s"' % build_proxy_url(urljoin(base_url, target))

            rewritten.append(URI_ATTRIBUTE_PATTERN.sub(replace_attribute, stripped))
            continue

        # URI 라인: master의 variant 경로 또는 media의 세그먼트 경로
        rewritten.append(build_proxy_url(urljoin(base_url, stripped)))

    return '\n'.join(rewritten) + '\n'


def is_probably_playlist(url, content_type, length_header):
    """플레이리스트인지 먼저 판단한다.

    SOOP CDN은 세그먼트(.TS)에도 application/vnd.apple.mpegurl을 내려주므로
    Content-Type만 믿으면 안 된다. 확장자를 먼저 보고, 애매할 때만 본문을
    읽어 #EXTM3U로 확인한다.
    """
    path = urlparse(url).path.lower()
    # 세그먼트가 .m3u8로 끝나지 않는 한 재생목록으로 보지 않는다
    if not path.endswith('.m3u8'):
        return False
    if 'mpegurl' in (content_type or '').lower():
        return True

    # 확장자는 맞지만 Content-Type이 애매한 경우에만 크기로 보조 판단한다
    try:
        declared_size = int(length_header) if length_header else 0
    except (TypeError, ValueError):
        declared_size = 0

    return declared_size <= MAX_PLAYLIST_BYTES


def open_stream(url, range_header=None):
    """업스트림 연결을 연다. 재생 가능한 상태로 유지되므로 호출자가 닫을 책임이 있다."""
    if not is_allowed_url(url):
        logger.warning("[proxy] host not allowed url=%s", url)
        raise ProxyForbidden(url)

    logger.info("[proxy] open url=%s range=%s", url, bool(range_header))
    try:
        response = requests.get(
            url,
            headers=_headers_for(url, range_header),
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        logger.warning("[proxy] upstream request failed url=%s error=%s", url, error)
        raise ProxyError(str(error)) from error

    return response


def read_playlist(response, base_url):
    """연결된 응답을 읽어 재작성된 플레이리스트 텍스트를 돌려준다."""
    body = response.raw.read(MAX_PLAYLIST_BYTES + 1, decode_content=True)
    if len(body) > MAX_PLAYLIST_BYTES:
        raise ProxyError('playlist too large')

    text = body.decode('utf-8', errors='replace')
    if not text.lstrip().startswith('#EXTM3U'):
        raise ProxyError('response is not a playlist')
    return rewrite_playlist(text, base_url)