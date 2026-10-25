"""
Contains YOLO-specific model loading, inference and prediction processing.
"""
import time
from pathlib import Path

import numpy as np
from ultralytics import YOLO
import cv2

from inspection.base import BaseInspector
from inspection.result import InspectionResult

# ---------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------

# Project root: canTech_tin_inspection/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Model location 
MODEL_PATH = PROJECT_ROOT / "models" / "model_no2.pt"

# Initial inference threshold.
CONFIDENCE_THRESHOLD = 0.40

# model class mapping
DEFECT_CLASS_ID = 0
NORMAL_CLASS_ID = 1


def correct_color(frame):
    # OpenCV channel order is BGR
    b, g, r = cv2.split(frame)

    b = cv2.convertScaleAbs(b, alpha=0.50)  # Reduce blue
    g = cv2.convertScaleAbs(g, alpha=0.70)  # Slightly reduce green
    r = cv2.convertScaleAbs(r, alpha=0.80)  # Boost red

    return cv2.merge([b, g, r])

class YOLOOBBInspector(BaseInspector):
    """
    YOLO OBB inspector for can-bottom defect detection.
    """

    def __init__(
        self,
        model_path: str | Path = MODEL_PATH,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        device: str | None = None,
    ):
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.device = device 

        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"YOLO model not found: {self.model_path}"
            )

        # Load the model once during startup 
        self.model = YOLO(str(self.model_path))

        # Validate the expected class mapping
        names = self.model.names

        if isinstance(names, dict):
            defect_name = names.get(DEFECT_CLASS_ID)
            normal_name = names.get(NORMAL_CLASS_ID)
        else:
            defect_name = (
                names[DEFECT_CLASS_ID]
                if len(names) > DEFECT_CLASS_ID else None
            )
            normal_name = (
                names[NORMAL_CLASS_ID]
                if len(names) > NORMAL_CLASS_ID else None
            )

        if (
            str(defect_name).strip().lower() != "defect"
            or str(normal_name).strip().lower() != "normal"
        ):
            raise ValueError(
                "Unexpected model class mapping. Expected"
                "{0: 'defect', 1: 'normal'}, but model.name is"
                f"{names!r}"
            )

        print(f"YOLO OBB model loaded: {self.model_path}")
        print(f"Model classes: {names}")
        print(f"Confidence threshold: {self.confidence_threshold}")
        print(f"Inference devices: {self.device or 'Ultraytics default'}")


    def inspect(
        self,
        image: np.ndarray,
        frame_id: int,
        timestamp_ns: int,

    ) -> InspectionResult:
        """
        Inspect one image and return a standardized result.
        """
        start_time = time.perf_counter()

        try:
            if image is None or image.size == 0:
                raise ValueError("Input image is empty")

            image = correct_color(image)

            # Run oriented bounding box interface.
            prediction = self.model.predict(
                source=image,
                conf=self.confidence_threshold,
                device=self.device,
                verbose=False
            )[0]

            obb = prediction.obb

            print("\n========== YOLO DEBUG ==========")
            print("Image shape:", image.shape)
            print("Class names:", prediction.names)
            print("OBB object:", obb)

            if obb is None:
                print("OBB is None")
            elif len(obb) == 0:
                print("No detections even at confidence 0.001")
            else:
                print("Number of detections:", len(obb))
                print("Classes:", obb.cls.cpu().numpy())
                print("Confidences:", obb.conf.cpu().numpy())
                print("OBB coordinates:", obb.xyxyxyxy.cpu().numpy())

            print("================================\n")

            detections = []
            defect_confidences = []
            normal_confidences = []

            obb = prediction.obb

            if obb is not None and len(obb) > 0:
                polygons = obb.xyxyxyxy.cpu().numpy()
                confidences = obb.conf.cpu().numpy()
                class_ids = obb.cls.int().cpu().numpy()

                for polygon, confidence, class_id in zip(
                    polygons, confidences, class_ids
                ):
                    class_id = int(class_id)
                    confidence = float(confidence)

                    class_name = prediction.names.get(
                        class_id, str(class_id)
                    )

                    if class_id == DEFECT_CLASS_ID:
                        defect_confidences.append(confidence)

                    elif class_id == NORMAL_CLASS_ID:
                        normal_confidences.append(confidence)

                    else:
                        # Unexpected classes should not silently determine the inspection decision 
                        continue 

                    detections.append({
                        "class_id": class_id,
                        "class_name": class_name,
                        "confidence": confidence,
                        "polygon": polygon.tolist(),
                    })

            # A defect detection takes priority if both classes are present in the same image 
            if defect_confidences:
                is_defective = True
                decision_confidence = max(defect_confidences)

            elif normal_confidences:
                is_defective = False
                decision_confidence = max(normal_confidences)

            else:
                # No qulifying detection is not proof that the can is normal. Return an explicit inspection failure.
                raise RuntimeError(
                    "No defect or normal OBB detection found above"
                    f"the confidence threshold"
                    f"({self.confidence_threshold:.2f})"
                )

            elapsed_ms = (
                time.perf_counter() - start_time

            ) * 1000.0

            return InspectionResult(
                frame_id=frame_id,
                timestamp_ns=timestamp_ns,
                is_defective=is_defective,
                confidence=decision_confidence,
                detections=detections,
                processing_time_ms=elapsed_ms,
                image=image,
            )

        except Exception as exc:
            elapsed_ms = (
                time.perf_counter() - start_time
            )*1000.0

            return InspectionResult(
                frame_id=frame_id,
                timestamp_ns=timestamp_ns,
                is_defective=False,
                confidence=0.0,
                detections=[],
                processing_time_ms=elapsed_ms,
                error=str(exc),
                image=image,
            )


    def close(self) -> None:
        """
        Release resources if required by the model backend.
        Normally ultralytics manages model resources internally. 
        """
        pass


        

        
