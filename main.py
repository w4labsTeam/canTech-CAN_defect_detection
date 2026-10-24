
import threading
import time
import traceback
import cv2

from queue import Empty

from acquisition.capture import (
    capture_main,
    stop_capture,
    acquisition_fault_event,
    get_acquisition_status,
)

from inspection.inspector import InspectionWorker
from application.display import render_result

# ---------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------

def print_result(result):
    """print the result and display the annotated image."""

    if result.error is not None:
        print(
            f"[INSPECTION ERROR] "
            f"Frame={result.frame_id} | "
            f"Error={result.error}"
        )
    
    else:
        status = "DEFECTIVE" if result.is_defective else "NORMAL"

        print(
            f"[RESULT] "
            f"Frame={result.frame_id} | "
            f"Status={status} | "
            f"Confidence={result.confidence:.3f} | "
            f"Inference={result.processing_time_ms:.2f} ms"
        )

    display_image = render_result(result)

    if display_image is not None:
        cv2.imshow("Can Defect Inspection", display_image)
        cv2.waitKey(1)


def main():
    """Coordinate camera acquisition and inspection."""

    inspection_worker = None

    camera_thread = threading.Thread(
        target=capture_main,
        kwargs={"preview": False},
        name="CameraAcquisition",
        daemon=False,
    )

    try:
        # -------------------------------------------------------------
        # 1. Initialize inspection
        # -------------------------------------------------------------

        print("Initializing inspection system...")

        # Loads the YOLO model before camera acquisition begins.
        inspection_worker = InspectionWorker()

        # -------------------------------------------------------------
        # 2. Start inspection worker
        # -------------------------------------------------------------

        print("Starting inspection worker...")
        inspection_worker.start()

        # -------------------------------------------------------------
        # 3. Start camera acquisition
        # -------------------------------------------------------------

        print("Starting camera acquisition...")
        camera_thread.start()

        print("System running. Press Ctrl+C to stop.")

        # -------------------------------------------------------------
        # 4. Monitor results and system faults
        # -------------------------------------------------------------

        while camera_thread.is_alive():

            # Stop if the inspection worker reports a fatal fault.
            if inspection_worker.fault_event.is_set():
                print(
                    "[APPLICATION FAULT] "
                    f"{inspection_worker.last_fault}"
                )
                break

            # Stop if acquisition reports a fault.
            if acquisition_fault_event.is_set():
                print(
                    "[APPLICATION FAULT] "
                    f"{get_acquisition_status()}"
                )
                break

            try:
                result = inspection_worker.get_result(timeout=0.1)
                print_result(result)

            except Empty:
                continue

    except KeyboardInterrupt:
        print("\nShutdown requested by user.")

    except Exception as exc:
        print(f"[APPLICATION ERROR] {exc}")
        traceback.print_exc()

    finally:
        # -------------------------------------------------------------
        # 5. Stop acquisition first
        # -------------------------------------------------------------

        stop_capture()

        if camera_thread.ident is not None:
            camera_thread.join(timeout=5.0)

            if camera_thread.is_alive():
                print(
                    "[WARNING] Camera thread did not stop "
                    "within the timeout."
                )

        # -------------------------------------------------------------
        # 6. Stop inspection worker
        # -------------------------------------------------------------

        if inspection_worker is not None:
            if inspection_worker.thread.ident is not None:
                try:
                    inspection_worker.stop(timeout=5.0)
                except TimeoutError as exc:
                    print(f"[WARNING] {exc}")

            # Consume results that were already queued before shutdown.
            while True:
                try:
                    result = inspection_worker.get_result(timeout=0)
                    print_result(result)
                except Empty:
                    break

        cv2.destroyAllWindows()
        print("Application stopped.")


if __name__ == "__main__":
    main()
