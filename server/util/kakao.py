import json
import re
from typing import Any, Optional
from urllib.parse import urlparse
import httpx

# ── 카카오 오픈빌더 통합 스킬 ──

def kakao_response(text: str, quick_replies: list = None):
    """오픈빌더 응답 규격 JSON 생성"""
    body = {
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}]
        }
    }
    if quick_replies:
        body["template"]["quickReplies"] = quick_replies
    return body


IMAGE_PARAM_KEYS = {
    "secureimage",
    "secure_image",
    "secureImage",
    "image",
    "imageUrl",
    "image_url",
    "cdnUrl",
    "cdn_url",
    "url",
}

VIDEO_PARAM_KEYS = {
    "securevideo",
    "secure_video",
    "secureVideo",
    "video",
    "videoUrl",
    "video_url",
    "media",
    "mediaUrl",
    "media_url",
}

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".m4v",
    ".avi",
    ".webm",
    ".mkv",
}

URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")


def _looks_like_image(content: bytes) -> bool:
    image_signatures = (
        b"\xff\xd8\xff",
        b"\x89PNG\r\n\x1a\n",
        b"GIF87a",
        b"GIF89a",
        b"RIFF",
        b"BM",
        b"II*\x00",
        b"MM\x00*",
    )
    return bool(content) and content.startswith(image_signatures)


def _looks_like_video(content: bytes) -> bool:
    if not content:
        return False

    return (
        content[4:8] == b"ftyp"
        or content.startswith(b"\x1aE\xdf\xa3")
        or (content.startswith(b"RIFF") and b"AVI " in content[:16])
    )


def _url_has_video_extension(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return any(path.endswith(extension) for extension in VIDEO_EXTENSIONS)


def _extract_url_from_string(value: str) -> Optional[str]:
    text = value.strip()
    if not text:
        return None

    if text.startswith("{") or text.startswith("["):
        try:
            return find_image_url(json.loads(text))
        except json.JSONDecodeError:
            pass

    match = URL_PATTERN.search(text)
    if match:
        return match.group(0)

    return None


def _extract_video_url_from_string(value: str, *, allow_any_url: bool = False) -> Optional[str]:
    text = value.strip()
    if not text:
        return None

    if text.startswith("{") or text.startswith("["):
        try:
            return find_video_url(json.loads(text), allow_any_url=allow_any_url)
        except json.JSONDecodeError:
            pass

    matches = URL_PATTERN.findall(text)
    for url in matches:
        if _url_has_video_extension(url):
            return url

    if allow_any_url and matches:
        return matches[0]

    return None


def find_image_url(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        for key in IMAGE_PARAM_KEYS:
            if key in value:
                found = find_image_url(value[key])
                if found:
                    return found

        for nested_value in value.values():
            found = find_image_url(nested_value)
            if found:
                return found

    if isinstance(value, list):
        for item in value:
            found = find_image_url(item)
            if found:
                return found

    if isinstance(value, str):
        return _extract_url_from_string(value)

    return None


def find_video_url(value: Any, *, allow_any_url: bool = False) -> Optional[str]:
    if isinstance(value, dict):
        for key in VIDEO_PARAM_KEYS:
            if key in value:
                found = find_video_url(value[key], allow_any_url=True)
                if found:
                    return found

        for nested_value in value.values():
            found = find_video_url(nested_value, allow_any_url=allow_any_url)
            if found:
                return found

    if isinstance(value, list):
        for item in value:
            found = find_video_url(item, allow_any_url=allow_any_url)
            if found:
                return found

    if isinstance(value, str):
        return _extract_video_url_from_string(value, allow_any_url=allow_any_url)

    return None


async def download_image_bytes(image_url: str) -> bytes:
    parsed = urlparse(image_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https image URLs are supported.")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(
            image_url,
            timeout=15,
            headers={"User-Agent": "ai-detection-server/1.0"},
        )

    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    content = response.content
    if not content_type.startswith("image/") and not _looks_like_image(content):
        raise ValueError(f"URL did not return image content: {content_type}")

    return content


async def download_video_bytes(video_url: str, max_size: int = 50 * 1024 * 1024) -> bytes:
    parsed = urlparse(video_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http and https video URLs are supported.")

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(
            video_url,
            timeout=30,
            headers={"User-Agent": "ai-detection-server/1.0"},
        )

    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    content = response.content
    if len(content) > max_size:
        raise ValueError("Video is too large.")

    if (
        not content_type.startswith("video/")
        and not _looks_like_video(content)
        and not _url_has_video_extension(video_url)
    ):
        raise ValueError(f"URL did not return video content: {content_type}")

    return content


QUICK_REPLY_RESTART = [
    {
        "messageText": "텍스트 분석",
        "action": "message",
        "label": "📝 텍스트 분석"
    },
    {
        "messageText": "이미지 분석",
        "action": "message",
        "label": "🖼️ 이미지 분석"
    }
]
