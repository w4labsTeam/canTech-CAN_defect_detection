
import threading
import time
import traceback
import cv2

from queue import Empty
from pathlib import Path
 
from acquisition.capture import (
    capture_main,
    stop_capture,
    acquisition_fault_event,
    get_acquisition_status,
)

from inspection.inspector import InspectionWorker
from application.display import render_result

from communication.mqtt_publisher import CANInspectionMQTT

# ---------------------------------------------------------------------
# Annotated image storage
# ---------------------------------------------------------------------

ANNOTATED_IMAGE_DIR = (
    Path(__file__).resolve().parent / "annotated_images"
)

ANNOTATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

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
        print("[SYSTEM] AI model loaded successfully.")

        # ----------------------------------------------
        # ---------------
        # 2. Initialize MQTT monitoring 
        # -------------------------------------------------------------
        print ("Initializing MQTT monitoring...")

        mqtt_monitor = CANInspectionMQTT(
            host="127.0.0.1",
            port=1883,
            publish_interval=1.0,
            idle_reset_seconds=60.0,
            rate_window_seconds=5.0,
        )

        mqtt_monitor.set_status(
            ai_model="LOADED",
            camera="STARTING",
            inspection_service="STARTING",
        )
        mqtt_monitor.start()

        # -------------------------------------------------------------
        # 2. Start inspection worker
        # -------------------------------------------------------------

        print("Starting inspection worker...")
        inspection_worker.start()

        mqtt_monitor.set_status(
            inspection_service="RUNNING"
        )

        # -------------------------------------------------------------
        # 3. Start camera acquisition
        # -------------------------------------------------------------

        print("Starting camera acquisition...")
        camera_thread.start()

        mqtt_monitor.set_status(
            camera="RUNNING"
        )

        print("System running. Press Ctrl+C to stop.")

        # -------------------------------------------------------------
        # 4. Monitor results and system faults
        # -------------------------------------------------------------
        window_name = "Can Defect Inspection"

        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        print("System running. Press Q or ESC to stop.")

        while camera_thread.is_alive():

            # Stop if the inspection worker reports a fatal fault.
            if inspection_worker.fault_event.is_set():
                print(
                    "[APPLICATION FAULT] "
                    f"{inspection_worker.last_fault}"
                )

                mqtt_monitor.set_status(
                    inspection_service="ERROR"
                )
                break

            # Stop if acquisition reports a fault.
            if acquisition_fault_event.is_set():
                print(
                    "[APPLICATION FAULT] "
                    f"{get_acquisition_status()}"
                )
                mqtt_monitor.set_status(
                    camera="ERROR"
                )

                break

            try:
                result = inspection_worker.get_result(timeout=0.01)

                mqtt_monitor.record_result(result)
                print_result(result)

                # Render bounding boxes and labels
                display_image = render_result(result)

                if display_image is not None:

                    # Display the annotated image
                    cv2.imshow(window_name, display_image)

                    # Save the final annotated image
                    if result.error is None:

                        filename = f"frame_{result.frame_id:06d}.png"

                        image_path = ANNOTATED_IMAGE_DIR / filename

                        success = cv2.imwrite(
                            str(image_path),
                            display_image
                        )

                        if success:
                            print(
                                f"[ANNOTATED IMAGE SAVED] {filename}"
                            )
                        else:
                            print(
                                f"[IMAGE SAVE ERROR] {filename}"
                            )

            except Empty:
                pass

            # Process GUI events on every iteration, including when
            # no new inspection result is available.
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q") or key == 27:
                print("Shutdown requested from display window.")
                break

            # Stop if the user closes the window.
            try:
                if cv2.getWindowProperty(
                    window_name, cv2.WND_PROP_VISIBLE
                ) < 1:
                    break
            except cv2.error:
                break

    except KeyboardInterrupt:
        print("\nShutdown requested by user.")

    except Exception as exc:
        print(f"[APPLICATION ERROR] {exc}")
        traceback.print_exc()

    finally:
        # -------------------------------------------------------------
        # 5. Stop acquisition first
        # -------------------------------------------------------------
        print("Stopping camera acquisition...")
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

                    if mqtt_monitor is not None:
                        mqtt_monitor.record_result(result)

                    print_result(result)
                except Empty:
                    break

        # -------------------------------------------------------------
        # 7. Stop MQTT monitoring
        # -------------------------------------------------------------
        if mqtt_monitor is not None:
            mqtt_monitor.stop()

        # -------------------------------------------------------------
        # 9. Release GUI resources
        # -------------------------------------------------------------
        cv2.destroyAllWindows()
        print("Application stopped.")


if __name__ == "__main__":
    main()
