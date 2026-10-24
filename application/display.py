
import cv2
import numpy as np

from inspection.result import InspectionResult


# Display colors use OpenCV's BGR ordering.
COLOR_DEFECT = (0, 0, 255)       # Red
COLOR_NORMAL = (0, 180, 0)       # Green
COLOR_ERROR = (0, 165, 255)      # Orange
COLOR_TEXT = (255, 255, 255)
COLOR_BACKGROUND = (35, 35, 35)


def render_result(result: InspectionResult) -> np.ndarray | None:
    """Draw inspection results on the associated image."""

    if result.image is None:
        return None

    # Copy the image so that the original frame is not modified.
    image = result.image.copy()

    # Draw the status banner at the top.
    if result.error:
        status = "INSPECTION ERROR"
        banner_color = COLOR_ERROR
    elif result.is_defective:
        status = "DEFECTIVE"
        banner_color = COLOR_DEFECT
    else:
        status = "NORMAL"
        banner_color = COLOR_NORMAL

    height, width = image.shape[:2]
    banner_height = min(75, max(50, height // 8))

    cv2.rectangle(
        image,
        (0, 0),
        (width, banner_height),
        banner_color,
        thickness=-1,
    )

    cv2.putText(
        image,
        status,
        (15, min(35, banner_height - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        COLOR_TEXT,
        2,
        cv2.LINE_AA,
    )

    details = (
        f"Frame: {result.frame_id} | "
        f"Confidence: {result.confidence:.2f} | "
        f"Time: {result.processing_time_ms:.1f} ms"
    )

    cv2.putText(
        image,
        details,
        (15, banner_height - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        COLOR_TEXT,
        1,
        cv2.LINE_AA,
    )

    # Draw OBB polygons and their labels.
    for detection in result.detections:
        polygon = np.asarray(
            detection["polygon"],
            dtype=np.float32,
        ).reshape(-1, 2).astype(np.int32)

        class_name = detection["class_name"]
        confidence = detection["confidence"]

        if detection["class_id"] == 0:
            color = COLOR_DEFECT
        elif detection["class_id"] == 1:
            color = COLOR_NORMAL
        else:
            color = (255, 200, 0)

        cv2.polylines(
            image,
            [polygon],
            isClosed=True,
            color=color,
            thickness=2,
            lineType=cv2.LINE_AA,
        )

        # Position the label near the top of the polygon.
        x = max(0, int(polygon[:, 0].min()))
        y = max(banner_height, int(polygon[:, 1].min()) - 8)

        label = f"{class_name}: {confidence:.2f}"

        cv2.putText(
            image,
            label,
            (x, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    return image
