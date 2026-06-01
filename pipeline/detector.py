"""
YOLOv8 person detector wrapper.

Wraps ultralytics YOLOv8 to provide a consistent detection interface
returning normalized bounding boxes and confidence scores per frame.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

# Default model — yolov8s balances speed and accuracy at 1080p / 15 FPS
_DEFAULT_MODEL = "yolov8s.pt"
_PERSON_CLASS_ID = 0  # COCO class 0 = person


@dataclass
class Detection:
    """Single person detection from a video frame."""

    # Bounding box in pixel coordinates [x1, y1, x2, y2]
    bbox: np.ndarray          # shape (4,), dtype float32
    confidence: float
    class_id: int = _PERSON_CLASS_ID
    # Optional feature crop passed to Re-ID later
    crop: np.ndarray | None = field(default=None, repr=False)


class PersonDetector:
    """
    YOLOv8-based person detector.

    Usage
    -----
    detector = PersonDetector(model_path="yolov8s.pt", conf_threshold=0.40)
    detections = detector.detect(frame)  # frame: np.ndarray H×W×C BGR
    """

    def __init__(
        self,
        model_path: str = _DEFAULT_MODEL,
        conf_threshold: float = 0.40,
        iou_threshold: float = 0.45,
        device: str = "cpu",
    ) -> None:
        """
        Parameters
        ----------
        model_path:      Path to YOLOv8 .pt weights (auto-downloaded if absent).
        conf_threshold:  Minimum detection confidence (0–1).
        iou_threshold:   NMS IoU threshold.
        device:          'cpu' or 'cuda' / 'mps'.
        """
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "ultralytics is required for the detector. "
                "Run: pip install ultralytics"
            ) from exc

        logger.info("Loading YOLOv8 model: %s on device=%s", model_path, device)
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self._warmup()

    def _warmup(self) -> None:
        """Run a single dummy inference to pre-load the model into memory."""
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        self.model.predict(
            dummy,
            classes=[_PERSON_CLASS_ID],
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False,
        )
        logger.info("YOLOv8 warmup complete.")

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Run person detection on a single BGR frame.

        Parameters
        ----------
        frame : np.ndarray
            H × W × 3 BGR image (as returned by cv2.VideoCapture.read).

        Returns
        -------
        List[Detection]
            One Detection per detected person, sorted by descending confidence.
        """
        results = self.model.predict(
            frame,
            classes=[_PERSON_CLASS_ID],
            conf=self.conf_threshold,
            iou=self.iou_threshold,
            device=self.device,
            verbose=False,
        )

        detections: List[Detection] = []
        if not results:
            return detections

        result = results[0]
        if result.boxes is None:
            return detections

        boxes_xyxy = result.boxes.xyxy.cpu().numpy()   # (N, 4)
        confs = result.boxes.conf.cpu().numpy()         # (N,)

        for bbox, conf in zip(boxes_xyxy, confs):
            # Extract person crop for Re-ID embedding
            x1, y1, x2, y2 = map(int, bbox)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(frame.shape[1], x2)
            y2 = min(frame.shape[0], y2)
            crop = frame[y1:y2, x1:x2] if (x2 > x1 and y2 > y1) else None

            detections.append(
                Detection(
                    bbox=bbox.astype(np.float32),
                    confidence=float(conf),
                    crop=crop,
                )
            )

        # Sort by descending confidence
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections
