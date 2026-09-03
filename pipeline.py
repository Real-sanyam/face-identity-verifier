"""End-to-end face scan -> live social-post discovery -> Sepolia verification.

Usage:
    python pipeline.py --face path/to/your_photo.jpg --profiles config/profiles.yaml
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from src import blockchain, face_match, profile_search, records, reverse_image_search

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

load_dotenv()


def _remove_temporary_file(path: str) -> None:
    """Candidate images are downloaded only for comparison and should not linger."""
    Path(path).unlink(missing_ok=True)


def _build_metadata(
    candidate: profile_search.Candidate, match: face_match.MatchResult
) -> dict[str, object]:
    """Create a compact public record without placing post text on-chain."""
    metadata: dict[str, object] = {
        "schema_version": "face-identity-verifier/v1",
        "platform": candidate.platform,
        "post_url": candidate.source_url,
        "discovery_method": candidate.discovery_method,
        "matched_at": datetime.now(timezone.utc).isoformat(),
        "face_distance": round(match.distance, 4),
        "face_threshold": round(match.threshold, 4),
        "matched_image_sha256": face_match.sha256_of_file(candidate.image_path),
    }
    if candidate.title:
        metadata["post_title_sha256"] = records.sha256_text(candidate.title)
    if candidate.post_text:
        metadata["post_text_sha256"] = records.sha256_text(candidate.post_text)
    if candidate.published_at:
        metadata["published_at"] = candidate.published_at
    return metadata


def run(
    face_path: str,
    profiles_path: str | None = None,
    reverse_image_url: str | None = None,
    record_out: str | None = None,
) -> int:
    print(f"[1/3] Encoding face from {face_path} ...")
    face_match.encode_face(face_path)  # validates a face is detectable; raises if not
    print("      done.\n")

    print("[2/3] Searching public posts and checking your listed accounts...")
    match = None
    matched_candidate = None
    temporary_paths: list[str] = []
    try:
        if profiles_path and Path(profiles_path).exists():
            for candidate in profile_search.find_candidates(profiles_path):
                temporary_paths.append(candidate.image_path)
                result = face_match.compare_to_candidate(face_path, candidate.image_path)
                if result is None:
                    continue
                print(
                    f"      {candidate.platform}: {candidate.source_url} "
                    f"-> distance={result.distance:.3f} verified={result.verified}"
                )
                if result.verified and candidate.is_live_discovery:
                    match = result
                    matched_candidate = candidate
                    break
                if result.verified:
                    print("      (comparison only; this is not a live post-search result)")
        elif profiles_path:
            print(f"      Profile configuration not found: {profiles_path}; continuing with live search.")

        if match is None:
            print("      Running Google Lens social-post search...")
            try:
                hits = reverse_image_search.reverse_image_search(face_path, reverse_image_url)
            except reverse_image_search.ImageSearchError as error:
                print(f"      Live search could not run: {error}")
                return 1
            for hit in hits:
                temporary_paths.append(hit.image_path)
                result = face_match.compare_to_candidate(face_path, hit.image_path)
                if result is None:
                    continue
                print(
                    f"      {hit.platform}: {hit.page_url} "
                    f"-> distance={result.distance:.3f} verified={result.verified}"
                )
                if result.verified:
                    match = result
                    matched_candidate = profile_search.Candidate(
                        platform=hit.platform,
                        source_url=hit.page_url,
                        image_path=hit.image_path,
                        discovery_method="serpapi_google_lens",
                        is_live_discovery=True,
                        title=hit.title,
                        published_at=hit.published_at,
                    )
                    break

        if match is None or matched_candidate is None:
            print("\nNo verified live post match found. Stopping before blockchain stage.")
            return 1

        print(f"\n      Live post match confirmed: {matched_candidate.source_url}\n")

        print("[3/3] Registering fingerprint on Sepolia...")
        metadata = _build_metadata(matched_candidate, match)
        metadata_json = records.canonical_json(metadata)
        data_hash = records.metadata_hash(metadata)
        output_path = record_out or str(Path("records") / f"{data_hash[2:]}.json")
        records.save_metadata(metadata, output_path)

        print(f"      metadata: {metadata_json}")
        print(f"      hash:     {data_hash}")
        print(f"      evidence: {output_path}")

        tx_hash = blockchain.register_hash(data_hash, metadata_json)
        print(f"      tx: 0x{tx_hash if not tx_hash.startswith('0x') else tx_hash[2:]}")
        print(f"      Etherscan: https://sepolia.etherscan.io/tx/{tx_hash}")

        print("      Re-reading contract to independently re-verify...")
        record = blockchain.verify_hash(data_hash)
        if not record.exists or record.metadata_uri != metadata_json:
            raise RuntimeError("On-chain record does not match the submitted metadata.")
        print("      On-chain record MATCHES submitted data. \u2705")

        print("\nDone. Re-verify the evidence file anytime with:")
        print(f"  python scripts/verify_onchain.py --metadata {output_path}")
        return 0
    finally:
        for temporary_path in temporary_paths:
            _remove_temporary_file(temporary_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--face", required=True, help="Path to your reference face photo")
    parser.add_argument("--profiles", default=None, help="Optional path to your profiles.yaml")
    parser.add_argument(
        "--reverse-image-url",
        default=None,
        help=(
            "Optional public image URL. Normally the local --face image is uploaded "
            "to SerpApi directly; use this only for files over its 500 KB limit."
        ),
    )
    parser.add_argument(
        "--record-out",
        default=None,
        help="Where to write the canonical evidence JSON (default: records/<hash>.json)",
    )
    args = parser.parse_args()
    return run(args.face, args.profiles, args.reverse_image_url, args.record_out)


if __name__ == "__main__":
    raise SystemExit(main())
