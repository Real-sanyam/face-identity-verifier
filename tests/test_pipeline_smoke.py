"""
Lightweight tests that don't require DeepFace model downloads, a live
Sepolia RPC, or real API keys — they check the plumbing (hashing,
config parsing, contract ABI shape) in isolation.

Run with: pytest tests/
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import face_match, profile_search, records, reverse_image_search  # noqa: E402


def test_sha256_of_file(tmp_path):
    import hashlib

    f = tmp_path / "sample.txt"
    f.write_bytes(b"hello world")
    digest = face_match.sha256_of_file(str(f))
    assert digest == hashlib.sha256(b"hello world").hexdigest()
    assert len(digest) == 64


def test_load_profiles(tmp_path):
    cfg = tmp_path / "profiles.yaml"
    cfg.write_text(
        """
github:
  - octocat
direct_images:
  - url: "https://example.com/img.jpg"
    platform: "instagram"
    source_url: "https://instagram.com/p/xyz"
"""
    )
    data = profile_search.load_profiles(str(cfg))
    assert data["github"] == ["octocat"]
    assert data["direct_images"][0]["platform"] == "instagram"


def test_contract_artifact_shape():
    artifact_path = Path(__file__).parent.parent / "artifacts" / "HashRegistry.json"
    if not artifact_path.exists():
        return  # compile.py hasn't been run in this environment; skip
    artifact = json.loads(artifact_path.read_text())
    assert "abi" in artifact and "bytecode" in artifact
    fn_names = {item.get("name") for item in artifact["abi"] if item.get("type") == "function"}
    assert {"registerHash", "verifyHash"}.issubset(fn_names)


def test_canonical_evidence_hash_is_deterministic(tmp_path):
    first = {"post_url": "https://x.com/example/status/1", "matched_image_sha256": "abc"}
    second = {"matched_image_sha256": "abc", "post_url": "https://x.com/example/status/1"}
    assert records.canonical_json(first) == records.canonical_json(second)
    assert records.metadata_hash(first) == records.metadata_hash(second)

    output = records.save_metadata(first, tmp_path / "evidence.json")
    assert output.read_text(encoding="utf-8") == records.canonical_json(first) + "\n"


def test_social_post_url_filter():
    assert reverse_image_search._is_social_post("https://x.com/example/status/123")
    assert reverse_image_search._is_social_post("https://www.instagram.com/p/abc123/")
    assert reverse_image_search._is_social_post("https://www.tiktok.com/@example/video/123")
    assert not reverse_image_search._is_social_post("https://github.com/example")
    assert not reverse_image_search._is_social_post("https://www.instagram.com/example/")
