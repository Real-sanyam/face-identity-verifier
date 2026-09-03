"""Independently re-verify saved match evidence against HashRegistry.

The preferred form recomputes the hash of a pipeline-generated evidence file
before reading the matching record from chain:

    python scripts/verify_onchain.py --metadata records/<hash>.json

This is read-only and needs only SEPOLIA_RPC_URL and CONTRACT_ADDRESS.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.blockchain import verify_hash  # noqa: E402
from src.face_match import sha256_of_file  # noqa: E402
from src.records import canonical_json, metadata_hash  # noqa: E402

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hash", help="A bytes32 SHA-256 record hash (0x...)")
    parser.add_argument(
        "--metadata",
        help="Canonical evidence JSON emitted by pipeline.py; enables full data-to-chain verification.",
    )
    parser.add_argument(
        "--image",
        help="Optional copy of the matched post image; checks its SHA-256 against --metadata.",
    )
    args = parser.parse_args()

    if not args.hash and not args.metadata:
        parser.error("provide --metadata (preferred) or --hash")

    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"could not read metadata JSON: {exc}")
        if not isinstance(metadata, dict):
            parser.error("metadata must be a JSON object")
        computed_hash = metadata_hash(metadata)
        if args.hash and args.hash.lower() != computed_hash:
            parser.error("--hash does not match the hash recomputed from --metadata")
        data_hash = computed_hash
    else:
        data_hash = args.hash

    if args.image:
        if metadata is None:
            parser.error("--image requires --metadata")
        expected_image_hash = metadata.get("matched_image_sha256")
        if not expected_image_hash:
            parser.error("metadata has no matched_image_sha256 value")
        actual_image_hash = sha256_of_file(args.image)
        if actual_image_hash != expected_image_hash:
            print("Image hash does NOT match the evidence record.")
            return 1
        print("Image hash matches the evidence record.")

    record = verify_hash(data_hash)
    if not record.exists:
        print("No record found on-chain for that hash.")
        return 1

    if metadata is not None and record.metadata_uri != canonical_json(metadata):
        print("On-chain metadata does NOT match the supplied evidence file.")
        return 1

    print("On-chain record verified:")
    print(f"  hash:          {data_hash}")
    print(f"  submitter:     {record.submitter}")
    print(f"  timestamp:     {record.timestamp}")
    print(f"  metadata_uri:  {record.metadata_uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
