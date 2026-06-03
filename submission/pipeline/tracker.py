"""
ByteTrack multi-object tracker wrapper.

Uses the `supervision` library's ByteTrack implementation to assign
persistent track IDs to YOLOv8 detections across video frames.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Track:
    """Active tracked person with a persistent track_id for this camera session."""

    track_id: int
    bbox: np.ndarray          # [x1, y1, x2, y2] float32
    confidence: float
    # Bottom-center foot point in pixel coordinates (used for zone matching)
    foot_point: tuple[float, float] = field(default=(0.0, 0.0))
    # Crop image forwarded from detector (may be None)
    crop: np.ndarray | None = field(default=None, repr=False)
    # How many consecutive frames this track has been active
    age: int = 0

    def __post_init__(self) -> None:
        x1, y1, x2, y2 = self.bbox
        self.foot_point = ((x1 + x2) / 2.0, float(y2))


class PersonTracker:
    """
    ByteTrack wrapper for persistent person tracking across frames.

    ByteTrack uses IoU + Kalman filtering + a low-confidence "second round"
    association, giving it strong performance under partial occlusion —
    critical for a retail environment with crowded aisles.

    Usage
    -----
    tracker = PersonTracker()
    for frame_idx, detections in enumerate(per_frame_detections):
        tracks = tracker.update(detections, frame_idx)
    """

    def __init__(
        self,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,   # frames to keep lost tracks (2 s @ 15 FPS)
        minimum_matching_threshold: float = 0.8,
        frame_rate: int = 15,
    ) -> None:
        try:
            import supervision as sv  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "supervision is required for the tracker. "
                "Run: pip install supervision"
            ) from exc

        self._sv = sv
        self.byte_tracker = sv.ByteTrack(
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
            frame_rate=frame_rate,
        )
        logger.info(
            "ByteTrack initialized (buffer=%d frames, rate=%d FPS)",
            lost_track_buffer,
            frame_rate,
        )

    def update(self, detections: list, frame_idx: int) -> List[Track]:
        """
        Update tracker with latest frame detections.

        Parameters
        ----------
        detections : list[Detection]
            Output from PersonDetector.detect().
        frame_idx : int
            Current frame index (used internally by ByteTrack).

        Returns
        -------
        List[Track]
            Active tracks with assigned track_id.
        """
        if not detections:
            # Advance tracker with empty detections (keeps lost tracks alive)
            sv_detections = self._sv.Detections.empty()
        else:
            boxes = np.array([d.bbox for d in detections], dtype=np.float32)
            confs = np.array([d.confidence for d in detections], dtype=np.float32)
            class_ids = np.zeros(len(detections), dtype=int)
            sv_detections = self._sv.Detections(
                xyxy=boxes,
                confidence=confs,
                class_id=class_ids,
            )

        tracked = self.byte_tracker.update_with_detections(sv_detections)

        tracks: List[Track] = []
        for i in range(len(tracked)):
            track_id = int(tracked.tracker_id[i])
            bbox = tracked.xyxy[i].astype(np.float32)
            conf = float(tracked.confidence[i]) if tracked.confidence is not None else 0.5

            # Retrieve crop from the original detection by matching bounding box
            crop = None
            if detections:
                crop = _match_crop(bbox, detections)

            tracks.append(
                Track(
                    track_id=track_id,
                    bbox=bbox,
                    confidence=conf,
                    crop=crop,
                )
            )

        return tracks

    def reset(self) -> None:
        """Reset tracker state (call between video files)."""
        try:
            import supervision as sv  # type: ignore
            self.byte_tracker = sv.ByteTrack()
        except ImportError:
            pass


def _match_crop(
    tracked_bbox: np.ndarray,
    detections: list,
    iou_threshold: float = 0.5,
) -> "np.ndarray | None":
    """Return the crop from the detection with highest IoU overlap."""
    best_iou = iou_threshold
    best_crop = None
    for det in detections:
        iou = _bbox_iou(tracked_bbox, det.bbox)
        if iou > best_iou:
            best_iou = iou
            best_crop = det.crop
    return best_crop


def _bbox_iou(a: np.ndarray, b: np.ndarray) -> float:
    """Compute IoU between two [x1,y1,x2,y2] boxes."""
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)
