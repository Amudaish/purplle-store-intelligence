"""
OSNet-based Re-Identification module.

Extracts appearance embeddings per tracked person and uses Redis
to maintain a cross-camera embedding store so that the same physical
person always gets the same global visitor_id regardless of which
camera sees them.

Architecture
------------
- OSNet is loaded as an ONNX model for portable, dependency-free inference.
- Embeddings are stored in Redis as JSON-serialized vectors under the key:
    reid:<store_id>:<visitor_id>  →  { "embedding": [...], "updated_at": <ts> }
- New tracks are matched by cosine similarity against all stored embeddings
  for the same store.  If similarity > MATCH_THRESHOLD the existing
  visitor_id is reused; otherwise a new UUID visitor_id is created.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Cosine similarity threshold for considering two embeddings the same person
MATCH_THRESHOLD = 0.72
# Redis TTL for embeddings (seconds) — 2 hours covers re-entry scenarios
EMBEDDING_TTL = 7200
# Input size expected by OSNet ONNX model
_INPUT_SIZE = (256, 128)  # (height, width)
# Default OSNet model path (user must download or use torchreid export)
_DEFAULT_ONNX = Path(__file__).parent / "models" / "osnet_x0_25_msmt17.onnx"


class ReIDModule:
    """
    Cross-camera visitor Re-Identification using OSNet embeddings.

    Falls back to a lightweight color-histogram embedding when the ONNX
    model is unavailable, ensuring the pipeline always produces a visitor_id.

    Usage
    -----
    reid = ReIDModule(redis_client, store_id="store_001")
    visitor_id = reid.get_or_create_visitor_id(track_id=7, crop=frame_crop)
    """

    def __init__(
        self,
        redis_client,
        store_id: str,
        onnx_path: Path = _DEFAULT_ONNX,
        match_threshold: float = MATCH_THRESHOLD,
    ) -> None:
        self.redis = redis_client
        self.store_id = store_id
        self.match_threshold = match_threshold
        self._session: Dict[int, str] = {}   # track_id → visitor_id (in-memory cache)
        self._ort_session = self._load_onnx(onnx_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_visitor_id(
        self,
        track_id: int,
        crop: Optional[np.ndarray],
    ) -> str:
        """
        Return an existing global visitor_id for this track (if Re-ID matches
        a known person) or create and register a new one.

        Parameters
        ----------
        track_id : int
            ByteTrack-assigned track ID for this camera session.
        crop : np.ndarray or None
            BGR image crop of the person bounding box.

        Returns
        -------
        str  — UUID4 string used as visitor_id across the platform.
        """
        # 1. Return cached mapping if this track_id is already known
        if track_id in self._session:
            return self._session[track_id]

        # 2. Extract embedding
        embedding = self._extract_embedding(crop)

        # 3. Query Redis for existing embeddings and find best match
        matched_id = self._find_match(embedding)

        if matched_id is None:
            matched_id = str(uuid.uuid4())
            logger.debug("New visitor_id created: %s (track_id=%d)", matched_id, track_id)
        else:
            logger.debug(
                "Re-ID match: visitor_id=%s for track_id=%d", matched_id, track_id
            )

        # 4. Store / update the embedding in Redis
        self._store_embedding(matched_id, embedding)

        # 5. Cache locally
        self._session[track_id] = matched_id
        return matched_id

    def clear_session(self) -> None:
        """Clear the in-memory track→visitor_id cache (between video files)."""
        self._session.clear()

    # ------------------------------------------------------------------
    # Embedding extraction
    # ------------------------------------------------------------------

    def _extract_embedding(self, crop: Optional[np.ndarray]) -> np.ndarray:
        """Return a unit-norm embedding vector for the given crop."""
        if crop is None or crop.size == 0:
            return self._zero_embedding()

        if self._ort_session is not None:
            return self._onnx_embedding(crop)
        return self._histogram_embedding(crop)

    def _onnx_embedding(self, crop: np.ndarray) -> np.ndarray:
        """Run OSNet ONNX inference."""
        import cv2  # type: ignore

        # Preprocess: resize → normalize → NCHW
        img = cv2.resize(crop, (_INPUT_SIZE[1], _INPUT_SIZE[0]))
        img = img[:, :, ::-1].astype(np.float32) / 255.0  # BGR→RGB, [0,1]
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        img = (img - mean) / std
        img = img.transpose(2, 0, 1)[np.newaxis, :]  # NCHW

        outputs = self._ort_session.run(None, {"input": img})
        embedding = outputs[0][0].astype(np.float32)
        return self._l2_normalize(embedding)

    def _histogram_embedding(self, crop: np.ndarray) -> np.ndarray:
        """
        Lightweight fallback: concatenated HSV histogram as an embedding.
        Dimension: 16 (H) + 8 (S) + 8 (V) = 32 bins.
        """
        import cv2  # type: ignore

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        h_hist = np.histogram(hsv[:, :, 0], bins=16, range=(0, 180))[0]
        s_hist = np.histogram(hsv[:, :, 1], bins=8, range=(0, 256))[0]
        v_hist = np.histogram(hsv[:, :, 2], bins=8, range=(0, 256))[0]
        embedding = np.concatenate([h_hist, s_hist, v_hist]).astype(np.float32)
        return self._l2_normalize(embedding)

    @staticmethod
    def _l2_normalize(v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / (norm + 1e-8)

    @staticmethod
    def _zero_embedding() -> np.ndarray:
        return np.zeros(32, dtype=np.float32)

    # ------------------------------------------------------------------
    # Redis operations
    # ------------------------------------------------------------------

    def _redis_key_pattern(self) -> str:
        return f"reid:{self.store_id}:*"

    def _redis_key(self, visitor_id: str) -> str:
        return f"reid:{self.store_id}:{visitor_id}"

    def _find_match(self, query: np.ndarray) -> Optional[str]:
        """Scan all stored embeddings for this store and return best matching visitor_id."""
        try:
            keys = self.redis.keys(self._redis_key_pattern())
        except Exception as exc:
            logger.warning("Redis scan failed: %s", exc)
            return None

        best_sim = self.match_threshold
        best_id: Optional[str] = None

        for key in keys:
            try:
                raw = self.redis.get(key)
                if raw is None:
                    continue
                data = json.loads(raw)
                stored = np.array(data["embedding"], dtype=np.float32)

                if stored.shape != query.shape:
                    continue

                sim = float(np.dot(query, stored))  # both unit-norm → cosine sim
                if sim > best_sim:
                    best_sim = sim
                    # Key format: reid:<store_id>:<visitor_id>
                    best_id = key.decode() if isinstance(key, bytes) else key
                    best_id = best_id.rsplit(":", 1)[-1]
            except Exception as exc:
                logger.debug("Error reading embedding key %s: %s", key, exc)

        return best_id

    def _store_embedding(self, visitor_id: str, embedding: np.ndarray) -> None:
        """Persist embedding to Redis with TTL."""
        key = self._redis_key(visitor_id)
        try:
            self.redis.setex(
                key,
                EMBEDDING_TTL,
                json.dumps({"embedding": embedding.tolist()}),
            )
        except Exception as exc:
            logger.warning("Failed to store embedding in Redis: %s", exc)

    # ------------------------------------------------------------------
    # ONNX model loader
    # ------------------------------------------------------------------

    @staticmethod
    def _load_onnx(path: Path):
        """Attempt to load ONNX session; return None if unavailable."""
        try:
            import onnxruntime as ort  # type: ignore

            if not path.exists():
                logger.warning(
                    "OSNet ONNX model not found at %s — "
                    "falling back to histogram embedding.",
                    path,
                )
                return None
            sess = ort.InferenceSession(
                str(path),
                providers=["CPUExecutionProvider"],
            )
            logger.info("OSNet ONNX model loaded from %s", path)
            return sess
        except ImportError:
            logger.warning(
                "onnxruntime not installed — using histogram embedding fallback."
            )
            return None
