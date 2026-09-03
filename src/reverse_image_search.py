"""Live visual search of the user's reference photo using SerpApi Google Lens."""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

SERPAPI_SEARCH_ENDPOINT = "https://serpapi.com/search.json"
SERPAPI_IMAGE_ENDPOINT = "https://serpapi.com/image"
SERPAPI_UPLOAD_LIMIT_BYTES = 500_000
MAX_DOWNLOAD_BYTES = 5_000_000


class ImageSearchError(RuntimeError):
    """The live visual-search provider could not complete a search."""


@dataclass
class ImageSearchHit:
    source_url: str
    page_url: str
    image_path: str
    platform: str
    title: str | None = None
    published_at: str | None = None


def _download(url: str) -> str:
    """Download a bounded image result to a temporary file."""
    response = requests.get(
        url, timeout=20, stream=True, headers={"User-Agent": "face-identity-verifier/1.0"}
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if not content_type.startswith("image/"):
        raise ImageSearchError(f"Search result is not an image ({content_type or 'unknown type'})")

    suffix = Path(urlparse(url).path).suffix or ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    total = 0
    try:
        with os.fdopen(fd, "wb") as output:
            for chunk in response.iter_content(chunk_size=8192):
                total += len(chunk)
                if total > MAX_DOWNLOAD_BYTES:
                    raise ImageSearchError("Search result image exceeds the 5 MB safety limit")
                output.write(chunk)
        return tmp_path
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _is_social_post(url: str) -> bool:
    """Accept only URL shapes that identify an individual public post."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    if host in {"x.com", "twitter.com", "mobile.twitter.com"}:
        return "/status/" in path
    if host == "instagram.com":
        return path.startswith("/p/") or path.startswith("/reel/") or path.startswith("/tv/")
    if host == "facebook.com":
        return "/posts/" in path or path.startswith("/permalink.php")
    if host == "tiktok.com":
        return "/video/" in path
    if host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        return path == "/watch" or path.startswith("/shorts/") or host == "youtu.be"
    if host == "linkedin.com":
        return path.startswith("/posts/")
    if host == "reddit.com":
        return "/comments/" in path
    return False


def _upload_local_image(image_path: str, api_key: str) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Reference face image not found: {image_path}")
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ImageSearchError("Google Lens upload accepts only JPG, PNG, or WebP images")
    if path.stat().st_size > SERPAPI_UPLOAD_LIMIT_BYTES:
        raise ImageSearchError(
            "Reference image exceeds SerpApi's 500 KB upload limit; pass --reverse-image-url instead."
        )

    with path.open("rb") as image_file:
        try:
            response = requests.post(
                SERPAPI_IMAGE_ENDPOINT,
                data={"api_key": api_key},
                files={"image": (path.name, image_file)},
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ImageSearchError(f"Could not upload reference image to SerpApi: {exc}") from exc
    if data.get("error") or not data.get("image_id"):
        raise ImageSearchError(data.get("error", "SerpApi did not return an image_id"))
    return data["image_id"]


def reverse_image_search(
    image_path: str, image_url: str | None = None, max_results: int = 10
) -> list[ImageSearchHit]:
    """
    The default path uploads the local reference image to SerpApi and then
    uses the short-lived image ID in a Google Lens visual-match search.  An
    optional public ``image_url`` is supported for images over SerpApi's
    500 KB upload limit. Results are restricted to recognizable social-post
    URL shapes so a profile, article, or product page cannot be mistaken for
    a discovered post.
    """
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        logger.info("Skipping reverse image search: no SERPAPI_KEY configured.")
        return []

    params = {"engine": "google_lens", "type": "all", "api_key": api_key, "safe": "active"}
    if image_url:
        params["url"] = image_url
    else:
        params["image_id"] = _upload_local_image(image_path, api_key)

    try:
        resp = requests.get(SERPAPI_SEARCH_ENDPOINT, params=params, timeout=45)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise ImageSearchError(f"Google Lens search request failed: {exc}") from exc
    if data.get("error"):
        raise ImageSearchError(data["error"])

    hits: list[ImageSearchHit] = []
    results = [*data.get("exact_matches", []), *data.get("visual_matches", [])]
    seen_pages: set[str] = set()
    for result in results:
        if len(hits) >= max_results:
            break
        page = result.get("link")
        image_url = result.get("image") or result.get("thumbnail")
        if not image_url or not page or page in seen_pages or not _is_social_post(page):
            continue
        seen_pages.add(page)
        try:
            candidate_path = _download(image_url)
        except (ImageSearchError, requests.RequestException) as e:
            logger.warning("Could not download search result image %s: %s", image_url, e)
            continue
        hits.append(
            ImageSearchHit(
                source_url=image_url,
                page_url=page,
                image_path=candidate_path,
                platform=urlparse(page).netloc.lower().removeprefix("www."),
                title=result.get("title"),
                published_at=result.get("date"),
            )
        )

    logger.info("Reverse image search returned %d usable candidate(s).", len(hits))
    return hits
