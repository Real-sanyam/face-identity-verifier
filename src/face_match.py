"""
Face detection, encoding, and matching.

Uses DeepFace (https://github.com/serengil/deepface), which wraps several
detector/encoder backends behind one API and installs cleanly via pip
(no dlib/cmake build step required).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "ArcFace"
DETECTOR_BACKEND = "retinaface"
DISTANCE_METRIC = "cosine"


@dataclass
class FaceEncoding:
    source_path: str
    model: str
    embedding: list


@dataclass
class MatchResult:
    verified: bool
    distance: float
    threshold: float
    candidate_path: str


def encode_face(image_path: str) -> FaceEncoding:
    """Detect the primary face in `image_path` and return its embedding."""
    from deepface import DeepFace  # imported lazily: heavy dependency

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Reference face image not found: {image_path}")

    reps = DeepFace.represent(
        img_path=str(path),
        model_name=MODEL_NAME,
        detector_backend=DETECTOR_BACKEND,
        enforce_detection=True,
    )
    if not reps:
        raise ValueError(f"No face detected in {image_path}")

    embedding = reps[0]["embedding"]
    logger.info("Encoded face from %s using %s (%d-d)", image_path, MODEL_NAME, len(embedding))
    return FaceEncoding(source_path=str(path), model=MODEL_NAME, embedding=embedding)


def compare_to_candidate(reference_path: str, candidate_path: str) -> Optional[MatchResult]:
    """
    Compare the reference face image against a candidate image found during
    search. Returns None if no face could be detected in the candidate
    (e.g. the post/photo simply doesn't show a usable face).
    """
    from deepface import DeepFace

    try:
        result = DeepFace.verify(
            img1_path=reference_path,
            img2_path=candidate_path,
            model_name=MODEL_NAME,
            detector_backend=DETECTOR_BACKEND,
            distance_metric=DISTANCE_METRIC,
            enforce_detection=True,
        )
    except Exception as error:  # Image decoders expose several backend-specific exception types.
        logger.info("Could not use candidate %s for face comparison: %s", candidate_path, error)
        return None

    return MatchResult(
        verified=bool(result["verified"]),
        distance=float(result["distance"]),
        threshold=float(result["threshold"]),
        candidate_path=candidate_path,
    )


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
