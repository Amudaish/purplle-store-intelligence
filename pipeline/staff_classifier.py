"""
Staff classifier using HSV dominant-color analysis.

Retail staff wear branded uniforms with a distinctive dominant hue.
This module classifies a person track as staff or customer by comparing
the dominant HSV hue of their clothing region against a configurable
staff-hue range.

Fallback heuristic: tracks that have been continuously visible for more
than STAFF_DWELL_FRAMES frames without ever leaving the store are also
flagged as likely staff (e.g., store managers who never step out).
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ── Colour-based thresholds ────────────────────────────────────────────────────
# Apex Retail staff wear a teal/cyan uniform (hue ≈ 85–105° in OpenCV 0–180 scale)
# Adjust these to match the actual uniform colour in the challenge videos.
STAFF_HUE_LOW = 80       # OpenCV hue units (0–180)
STAFF_HUE_HIGH = 110
STAFF_SAT_MIN = 80       # Require reasonably saturated colour (not grey/white)
STAFF_CONFIDENCE_THRESHOLD = 0.55   # Fraction of clothing pixels in hue range

# ── Dwell-based fallback ───────────────────────────────────────────────────────
# If the model hasn't been seen for >STAFF_DWELL_FRAMES consecutive frames
# we assume it may have left — reset its continuous dwell counter.
STAFF_DWELL_FRAMES = 900   # 60 seconds @ 15 FPS


class StaffClassifier:
    """
    Classifies each track as staff (True) or customer (False).

    Strategy
    --------
    1. Colour histogram on the upper-body crop region (top 60% of bounding box)
       to check if dominant hue falls within the staff uniform range.
    2. Dwell fallback: if a track has been seen for > STAFF_DWELL_FRAMES
       consecutive frames it is flagged as staff regardless of colour.

    Usage
    -----
    classifier = StaffClassifier()
    is_staff = classifier.classify(track_id=3, crop=person_crop, frame_idx=450)
    """

    def __init__(
        self,
        hue_low: int = STAFF_HUE_LOW,
        hue_high: int = STAFF_HUE_HIGH,
        sat_min: int = STAFF_SAT_MIN,
        confidence_threshold: float = STAFF_CONFIDENCE_THRESHOLD,
        dwell_frames: int = STAFF_DWELL_FRAMES,
    ) -> None:
        self.hue_low = hue_low
        self.hue_high = hue_high
        self.sat_min = sat_min
        self.confidence_threshold = confidence_threshold
        self.dwell_frames = dwell_frames

        # track_id → running state
        self._staff_cache: Dict[int, bool] = {}          # confirmed staff tracks
        self._first_seen: Dict[int, int] = {}            # track_id → first frame_idx
        self._last_seen: Dict[int, int] = {}             # track_id → last frame_idx
        self._continuous_dwell: Dict[int, int] = {}      # track_id → consecutive frame count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        track_id: int,
        crop: Optional[np.ndarray],
        frame_idx: int,
    ) -> bool:
        """
        Return True if this track is classified as store staff.

        Parameters
        ----------
        track_id  : ByteTrack track ID.
        crop      : BGR person bounding-box crop (may be None).
        frame_idx : Current frame index in the video.
        """
        # Once classified as staff, always staff for this session
        if self._staff_cache.get(track_id, False):
            self._update_dwell(track_id, frame_idx)
            return True

        # Update continuous dwell counter
        self._update_dwell(track_id, frame_idx)

        # --- Strategy 1: uniform colour ----------------------------------
        if crop is not None and crop.size > 0:
            if self._is_uniform_colour(crop):
                self._staff_cache[track_id] = True
                logger.debug(
                    "track_id=%d classified as STAFF (uniform colour)", track_id
                )
                return True

        # --- Strategy 2: dwell time fallback -----------------------------
        dwell = self._continuous_dwell.get(track_id, 0)
        if dwell >= self.dwell_frames:
            self._staff_cache[track_id] = True
            logger.debug(
                "track_id=%d classified as STAFF (dwell=%d frames)", track_id, dwell
            )
            return True

        return False

    def reset(self) -> None:
        """Clear all state between video files."""
        self._staff_cache.clear()
        self._first_seen.clear()
        self._last_seen.clear()
        self._continuous_dwell.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_uniform_colour(self, crop: np.ndarray) -> bool:
        """
        Check whether the upper-body region of the crop contains a dominant
        hue within the staff uniform range.
        """
        try:
            import cv2  # type: ignore
        except ImportError:
            return False

        # Use top 60% of the bounding box (torso / upper body)
        h, w = crop.shape[:2]
        upper = crop[: int(h * 0.60), :]
        if upper.size == 0:
            return False

        hsv = cv2.cvtColor(upper, cv2.COLOR_BGR2HSV)

        # Mask pixels with sufficient saturation (avoid grey/skin/white)
        sat_mask = hsv[:, :, 1] > self.sat_min

        # Count pixels in staff hue range
        hue = hsv[:, :, 0]
        hue_mask = (hue >= self.hue_low) & (hue <= self.hue_high) & sat_mask

        total_saturated = int(sat_mask.sum())
        if total_saturated == 0:
            return False

        ratio = float(hue_mask.sum()) / total_saturated
        return ratio >= self.confidence_threshold

    def _update_dwell(self, track_id: int, frame_idx: int) -> None:
        """Update continuous dwell counter, resetting on large frame gaps."""
        last = self._last_seen.get(track_id)
        if last is None:
            self._first_seen[track_id] = frame_idx
            self._continuous_dwell[track_id] = 1
        elif frame_idx - last <= 30:  # allow 30-frame gap (2 s) before reset
            self._continuous_dwell[track_id] = (
                self._continuous_dwell.get(track_id, 0) + (frame_idx - last)
            )
        else:
            # Track was lost and reappeared — reset continuous counter
            self._continuous_dwell[track_id] = 1
        self._last_seen[track_id] = frame_idx
