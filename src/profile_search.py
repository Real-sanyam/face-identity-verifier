"""Fetch candidates from user-authorized accounts and public post APIs.

Twitter/X candidates are actual posts retrieved through the official v2 API.
GitHub avatars and manually configured images remain useful comparison aids,
but are deliberately labelled as non-discovery candidates: they cannot by
themselves satisfy the pipeline's live-search requirement.
"""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import requests
import yaml

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/users/{username}"
TWITTER_USER_API = "https://api.twitter.com/2/users/by/username/{username}"
TWITTER_TWEETS_API = (
    "https://api.twitter.com/2/users/{user_id}/tweets"
    "?max_results=100"
    "&expansions=attachments.media_keys"
    "&media.fields=type,url,preview_image_url"
    "&tweet.fields=created_at,text"
)


@dataclass
class Candidate:
    platform: str
    source_url: str
    image_path: str
    discovery_method: str
    is_live_discovery: bool
    title: str | None = None
    post_text: str | None = None
    published_at: str | None = None


def load_profiles(config_path: str) -> dict:
    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def _download(url: str) -> str:
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    suffix = Path(url.split("?")[0]).suffix or ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return tmp_path


def _github_candidates(usernames: list[str]) -> Iterator[Candidate]:
    for username in usernames:
        try:
            resp = requests.get(GITHUB_API.format(username=username), timeout=15)
            resp.raise_for_status()
            data = resp.json()
            avatar_url = data.get("avatar_url")
            if not avatar_url:
                continue
            image_path = _download(avatar_url)
            yield Candidate(
                platform="github_profile",
                source_url=data.get("html_url", f"https://github.com/{username}"),
                image_path=image_path,
                discovery_method="github_profile_api",
                is_live_discovery=False,
            )
        except requests.RequestException as e:
            logger.warning("GitHub lookup failed for %s: %s", username, e)


def _twitter_candidates(usernames: list[str], bearer_token: str | None) -> Iterator[Candidate]:
    if not bearer_token:
        logger.info("Skipping Twitter/X check: no TWITTER_BEARER_TOKEN configured.")
        return
    headers = {"Authorization": f"Bearer {bearer_token}"}
    for username in usernames:
        try:
            resp = requests.get(
                TWITTER_USER_API.format(username=username), headers=headers, timeout=15
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
            user_id = data.get("id")
            if not user_id:
                continue

            tweets_response = requests.get(
                TWITTER_TWEETS_API.format(user_id=user_id), headers=headers, timeout=15
            )
            tweets_response.raise_for_status()
            tweets = tweets_response.json()
            media_by_key = {
                item["media_key"]
                for item in tweets.get("includes", {}).get("media", [])
                if item.get("media_key")
            }
            media_details = {
                item["media_key"]: item
                for item in tweets.get("includes", {}).get("media", [])
                if item.get("media_key")
            }
            for tweet in tweets.get("data", []):
                for media_key in tweet.get("attachments", {}).get("media_keys", []):
                    if media_key not in media_by_key:
                        continue
                    media = media_details[media_key]
                    if media.get("type") != "photo" or not media.get("url"):
                        continue
                    image_path = _download(media["url"])
                    yield Candidate(
                        platform="twitter",
                        source_url=f"https://x.com/{username}/status/{tweet['id']}",
                        image_path=image_path,
                        discovery_method="twitter_v2_user_timeline",
                        is_live_discovery=True,
                        post_text=tweet.get("text"),
                        published_at=tweet.get("created_at"),
                    )
        except requests.RequestException as e:
            logger.warning("Twitter lookup failed for %s: %s", username, e)


def _direct_image_candidates(entries: list[dict]) -> Iterator[Candidate]:
    for entry in entries or []:
        try:
            image_path = _download(entry["url"])
            yield Candidate(
                platform=entry.get("platform", "unknown"),
                source_url=entry.get("source_url", entry["url"]),
                image_path=image_path,
                discovery_method="configured_image",
                is_live_discovery=False,
                title=entry.get("title"),
                post_text=entry.get("post_text"),
                published_at=entry.get("published_at"),
            )
        except (requests.RequestException, KeyError) as e:
            logger.warning("Direct image fetch failed for %s: %s", entry, e)


def find_candidates(config_path: str) -> Iterator[Candidate]:
    """Yield all candidate images from every configured source."""
    profiles = load_profiles(config_path)
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")

    yield from _github_candidates(profiles.get("github", []))
    yield from _twitter_candidates(profiles.get("twitter", []), bearer_token)
    yield from _direct_image_candidates(profiles.get("direct_images", []))
