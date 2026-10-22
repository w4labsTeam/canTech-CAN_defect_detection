import cv2 
import numpy as np
import platform
import traceback
import threading 
import time

from dataclasses import dataclass
from queue import Queue, Full, Empty
from typing import Optional

from SDK import mvsdk
from camera.config import (
    EXPOSURE_TIME_US,
    TRIGGER_MODE,
    DISPLAY_WINDOW_NAME,
    TRIGGER_EDGE
)

# --------------------------------------------------------------------
# Frame Packet
# --------------------------------------------------------------------
@dataclass
class FramePackets:
    """An acquired image and its acquisition metadata"""

    frame_id: int
    timestamp_ns: int
    image: np.ndarray


# --------------------------------------------------------------------
# Shared acquisition state  
# --------------------------------------------------------------------
FRAME_QUEUE_SIZE = 10

frame_queue: Queue[FramePackets] = Queue(maxsize=FRAME_QUEUE_SIZE)

stop_event = threading.Event()
acquisition_fault_event = threading.Event()

# Information about acquisition faults 
fault_lock = threading.Lock()
last_fault: Optional[str] = None
queue_overflow_count = 0
callback_error_count = 0

# Frame IDs are assigned in callback-arrival order 
frame_id_lock = threading.Lock()
next_frame_id = 0

# SDK image-processing buffer pointer
pFrameBuffer = 0

def _set_acquisition_fault(message: str) -> None:
    """Set the acquisition fault state and record the fault message"""
    global last_fault
    with fault_lock:
        last_fault = message

    acquisition_fault_event.set()
    print(f"Acquisition fault: {message}")

def get_acquisition_status() -> dict:
    """Return the current acquisition status, including fault information"""
    with fault_lock:
        fault_message = last_fault
        overflow_count = queue_overflow_count
        error_count = callback_error_count

    return {
        "fault_message": fault_message,
        "queue_overflow_count": overflow_count,
        "callback_error_count": error_count
    }
    

# --------------------------------------------------------------------
# Camera callback 
# --------------------------------------------------------------------

@mvsdk.CAMERA_SNAP_PROC
def grab_callback(hCamera, pRawData, pFrameHead, pContext):

    global pFrameBuffer
    global next_frame_id
    global queue_overflow_count
    global callback_error_count

    # Timestamp callback arrival. This is not necessarily the exact sensor exposure timestamp.
    timestamp_ns = time.monotonic_ns()

    # Assign an ID to every callback invocation, including frames that cannot be queued.
    with frame_id_lock:
        frame_id = next_frame_id
        next_frame_id += 1

    try: 
        # ----------------------------------------------------------------
        # Get frame Information 
        # ----------------------------------------------------------------

        frame_head = pFrameHead[0]

        # ----------------------------------------------------------------
        # Convert the raw camera image into the format specified 
        # by CameraSetIspFormat()
        # ----------------------------------------------------------------

        mvsdk.CameraImageProcess(
            hCamera,
            pRawData,
            pFrameBuffer,
            frame_head
        )

        # Correct image orientation on windows, as in the original code.
        if platform.system() == "Windows":
            mvsdk.CameraFlipFrameBuffer(
                pFrameBuffer,
                frame_head,
                1.
            )

        height = frame_head.iHeight
        width = frame_head.iWidth

        # convert the SDK buffer into a NumPy view.
        buffer_type = mvsdk.c_ubyte * frame_head.uBytes
        frame_data = buffer_type.from_address(pFrameBuffer)

        frame = np.frombuffer(frame_data, dtype=np.uint8)

        # Preserve the correct shape for monochrome images.
        if frame_head.uiMediaType == mvsdk.CAMERA_MEDIA_TYPE_MONO8:
            frame = frame.reshape((height, width))
        else:
            frame = frame.reshape((height, width, 3))

        # Essential: detach the image from the reusable SDK buffer
        frame = frame.copy()

        packet = FramePackets(
            frame_id = frame_id,
            timestamp_ns = timestamp_ns,
            image = frame,
        )

        # Never silenty discard an older queued frame. A full queue raises an explicit acqusition fault.
        try:
            frame_queue.put_nowait(packet)

        except Full:
            with fault_lock:
                queue_overflow_count += 1
                overflow_count = queue_overflow_count

            _set_acquisition_fault(
                f"Frame queue full. Frame {frame_id} dropped."
                f"Total queue overflow: {overflow_count}"
            )

    except Exception as exc:
        with fault_lock:
            callback_error_count += 1

        _set_acquisition_fault(
            f"Error processing frame {frame_id}: {exc}."
        )

    finally:
        # Always return the raw SDK buffer, including on processing or queue errors.
        try:
            mvsdk.CameraReleaseImageBuffer(
                hCamera,
                pRawData,
            )

        except Exception as exc:
            _set_acquisition_fault(
                f"Failed to release SDK image buffer: {exc}"
            )


# -------------------------------------------------------------------
# Main acquisition function 
# -------------------------------------------------------------------

def capture_main(preview: bool = False) -> None:
    """
    Initialize the camera and acquire hardware-triggered frames.

    preview=False:
        the application consumes frame_queue from another thread.

    preview=True:
        Display queued frames for standalone camera testing. This mode is not suitable for production use, 
        as it may drop frames if the display cannot keep up with the camera frame rate.
    """

    global pFrameBuffer
    global next_frame_id
    global last_fault
    global queue_overflow_count
    global callback_error_count

    hCamera = 0
    camera_initialized = False
    camera_started = False

    stop_event.clear()
    acquisition_fault_event.clear()

    with fault_lock:
        last_fault = None
        queue_overflow_count = 0
        callback_error_count = 0    

    with frame_id_lock:
        next_frame_id = 0

    try:
        # ---------------------------------------------------------
        # 1. Enumerate Camera
        # ---------------------------------------------------------
        dev_list = mvsdk.CameraEnumerateDevice()
        if len(dev_list) == 0:
            raise RuntimeError("No MindVision camera was found")

        print(f"Found {len(dev_list)} camera(s)")


        # ---------------------------------------------------------
        # 2. Select camera
        # ---------------------------------------------------------
        if len(dev_list) == 1:
            dev_info = dev_list[0]

        else:
            raise RuntimeError("Multiple MindVision cameras detected. Please specify which camera to use.")


        # ---------------------------------------------------------
        # 3. Initialize Camera
        # ---------------------------------------------------------
        print("Initialize camera..")
        try:
            hCamera = mvsdk.CameraInit(dev_info, -1, -1)
            camera_initialized = True
            print("Camera Initialized..")

        except mvsdk.CameraException as e:
            print("CameraInit Failed({}): {}".format(e.error_code, e.message) )
            raise RuntimeError("Failed to initialize camera")


        # ---------------------------------------------------------
        # 4. Get camera capability
        # ---------------------------------------------------------
        cap = mvsdk.CameraGetCapability(
            hCamera
        )

        mono_camera = cap.sIspCapacity.bMonoSensor != 0
        max_width = cap.sResolutionRange.iWidthMax
        max_height = cap.sResolutionRange.iHeightMax

        print(
            f"maximum resolution: "
            f"{max_width} x"
            f"{max_height}"
        )


        # ---------------------------------------------------------
        # 5. Configure image output format
        # ---------------------------------------------------------

        if mono_camera:
            print("Camera type: Monochrome")
            mvsdk.CameraSetIspOutFormat(hCamera, mvsdk.CAMERA_MEDIA_TYPE_MONO8)

        else:
            print("Camera type: Color")
            mvsdk.CameraSetIspOutFormat(hCamera, mvsdk.CAMERA_MEDIA_TYPE_BGR8)

        channels = 1 if mono_camera else 3


        # ---------------------------------------------------------
        # 6. Configure Exposure
        # ---------------------------------------------------------
        status = mvsdk.CameraSetAeState(hCamera, 0)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            raise RuntimeError("Failed to disable auto exposure")

        print(f"Exposure time: {EXPOSURE_TIME_US} us")

        status = mvsdk.CameraSetExposureTime(hCamera, EXPOSURE_TIME_US)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            print("Failed to set exposure time.")


        # ---------------------------------------------------------
        # 7. Configure Trigger 
        # ---------------------------------------------------------
        print(
            f"Setting trigger mode: "
            f"{TRIGGER_MODE}"
        )

        status = mvsdk.CameraSetTriggerMode(hCamera, TRIGGER_MODE)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            raise RuntimeError("Failed to set trigger mode")

        if TRIGGER_MODE == 2:
            status = mvsdk.CameraSetExtTrigSignalType(hCamera, TRIGGER_EDGE)

            if status != mvsdk.CAMERA_STATUS_SUCCESS:
                raise RuntimeError("Failed to set trigger edge type")

            print("Hardware trigger configured")


        # ---------------------------------------------------------
        # 8. Allocate image processing buffer 
        # ---------------------------------------------------------
        buffer_size = max_width * max_height * channels

        pFrameBuffer = mvsdk.CameraAlignMalloc(buffer_size, 16)

        if not pFrameBuffer:
            raise RuntimeError("Failed to allocate image processing buffer")


        # ---------------------------------------------------------
        # 9. Regster callback 
        # ---------------------------------------------------------  
        print("Registering callback...")

        status = mvsdk.CameraSetCallbackFunction(
            hCamera, 
            grab_callback, 
            0
        )

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            raise RuntimeError("Failed to register callback")

        print("Callback registered..")


        # ---------------------------------------------------------
        # 10. Start camera
        # ---------------------------------------------------------
        print("Starting Camera..")

        status = mvsdk.CameraPlay(hCamera)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            raise RuntimeError("Failed to start the camera.")

        camera_started = True

        print("Camera Started..")
        print("\nWaiting for hardware trigger...")

        if preview:
            cv2.namedWindow(
                DISPLAY_WINDOW_NAME,
                cv2.WINDOW_NORMAL,
            )


        # ---------------------------------------------------------
        # 11. Other configurations
        # ---------------------------------------------------------
        gain_range = mvsdk.CameraGetAnalogGainXRange(hCamera)
        print("Analog gain range: ", gain_range)

        current_gain = mvsdk.CameraGetGain(hCamera)
        print("Current RGB gain range: ", current_gain)


        # ---------------------------------------------------------
        # 12. Keep acquisition alive until user requests exit
        # ---------------------------------------------------------
        while not stop_event.is_set():
            if acquisition_fault_event.is_set():
                print("Acquisition fault detected. Stopping acquisition.")
                break

            if preview:
                try:
                    packet = frame_queue.get(timeout=0.02)

                    cv2.imshow(DISPLAY_WINDOW_NAME, packet.image)

                    key = cv2.waitKey(1) & 0xFF

                    if key == ord('q'):
                        stop_event.set()

                except Empty:
                    cv2.waitKey(1)

            else:
                # The application/Inspection thread cosumes the queue
                stop_event.wait(0.02)

    except mvsdk.CameraException as exc:
        _set_acquisition_fault(f"Camera SDK error: {exc}")
        traceback.print_exc()

    except Exception as exc:
        _set_acquisition_fault(f"Unexpected error: {exc}")
        traceback.print_exc()

    finally:
        # ---------------------------------------------------------
        # 13. Stop camera
        # ---------------------------------------------------------
        if camera_started:
            try:
                mvsdk.CameraStop(hCamera)

            except Exception:
                traceback.print_exc()


        # ---------------------------------------------------------
        # 14. Uninitialize Camera
        # ---------------------------------------------------------
        if camera_initialized:
            try:
                mvsdk.CameraUnInit(hCamera)

            except Exception:
                traceback.print_exc()


        # ---------------------------------------------------------
        # 15. Free image Buffer
        # ---------------------------------------------------------
        if pFrameBuffer:
            try:
                mvsdk.CameraAlignFree(pFrameBuffer)
            except Exception:
                traceback.print_exc()
            finally:
                pFrameBuffer = 0


        # ---------------------------------------------------------
        # 16. Close openCV windows
        # ---------------------------------------------------------
        if preview:
            cv2.destroyAllWindows()
        print("\nCamera system stopped")


def stop_capture() -> None:
    """Request the capture thread to stop"""
    stop_event.set()


# ---------------------------------------------------------
# Standalone test mode
# ---------------------------------------------------------
if __name__ =="__main__":
    capture_main(preview=True)
        