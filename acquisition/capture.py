import cv2 
import numpy as np
import platform
import traceback

from queue import Queue
from SDK import mvsdk
from camera.config import (
    EXPOSURE_TIME_US,
    TRIGGER_MODE,
    DISPLAY_WINDOW_NAME,
    TRIGGER_EDGE
)

# --------------------------------------------------------------------
# Global variables 
# --------------------------------------------------------------------
# Pointer to the SDK image processing buffer 
pFrameBuffer = 0

# Used to stop the main loop
quit_requested = False

# Queue to store the numpy arrays (images) 
frame_queue = Queue(maxsize=2)

# --------------------------------------------------------------------
# Camera callback 
# --------------------------------------------------------------------

@mvsdk.CAMERA_SNAP_PROC
def grab_callback(hCamera, pRawData, pFrameHead, pContext):

    global pFrameBuffer
    global quit_requested

    # ----------------------------------------------------------------
    # Get frame Information 
    # ----------------------------------------------------------------

    FrameHead = pFrameHead[0]

    # ----------------------------------------------------------------
    # Convert the raw camera image into the format specified 
    # by CameraSetIspFormat()
    # ----------------------------------------------------------------

    mvsdk.CameraImageProcess(
        hCamera,
        pRawData,
        pFrameBuffer,
        FrameHead
    )

    # ---------------------------------------------------------------
    # Release the raw image buffer back to the SDK
    # ---------------------------------------------------------------

    mvsdk.CameraReleaseImageBuffer(
        hCamera,
        pRawData
    )

    # ---------------------------------------------------------------
    # Windows-specific image orientation correction
    # ---------------------------------------------------------------
    if platform.system() == "Windows":

        mvsdk.CameraFlipFrameBuffer(
            pFrameBuffer,
            FrameHead,
            1
        )

    # ---------------------------------------------------------------
    # Convert SDK buffer into a Numpy array
    # ---------------------------------------------------------------
    frame_data = (
        mvsdk.c_ubyte * FrameHead.uBytes
    ).from_address(pFrameBuffer)

    frame = np.frombuffer(
        frame_data, dtype=np.uint8
    )

    # ---------------------------------------------------------------
    # Determine number of image channels 
    # ---------------------------------------------------------------
    if FrameHead.uiMediaType == mvsdk.CAMERA_MEDIA_TYPE_MONO8:
        channels = 1
    else:
        channels = 3

    # ---------------------------------------------------------------
    # Convert the 1D Numpy array into an image 
    # ---------------------------------------------------------------
    frame = frame.reshape(
        (
            FrameHead.iHeight, 
            FrameHead.iWidth,
            channels
        )
    )

    # ---------------------------------------------------------------
    # Put the frame inside the Queue so that the inspection algorithm
    # can use the image
    # ---------------------------------------------------------------
    # First copy the image 
    frame = frame.copy()

    # put the frame into Queue
    if not frame_queue.full():
        frame_queue.put_nowait(frame)

    else:
        # Queue is full
        # drop the old frame and keep the enwest one 
        try:
            frame_queue.get_nowait()
        except:
            pass

        frame_queue.put_nowait(frame)


# -------------------------------------------------------------------
# Main acquisition function 
# -------------------------------------------------------------------

def main():

    global pFrameBuffer
    global quit_requested

    hCamera = 0

    try:
        # ---------------------------------------------------------
        # 1. Enumerate Camera
        # ---------------------------------------------------------
        dev_list = mvsdk.CameraEnumerateDevice()
        if len(dev_list) == 0:
            print("No camera was found!")
            return

        print(f"Found {len(dev_list)} camera(s)")

        # ---------------------------------------------------------
        # 2. Select camera
        # ---------------------------------------------------------
        if len(dev_list) == 1:
            dev_info = dev_list[0]

        else:
            print("Multiple Cameras detected.")

        # ---------------------------------------------------------
        # 3. Initialize Camera
        # ---------------------------------------------------------
        print("Initialize camera..")
        try:
            hCamera = mvsdk.CameraInit(dev_info, -1, -1)
            print("Camera Initialized..")

        except mvsdk.CameraException as e:
            print("CameraInit Failed({}): {}".format(e.error_code, e.message) )
            return

        # ---------------------------------------------------------
        # 4. Get camera capability
        # ---------------------------------------------------------
        cap = mvsdk.CameraGetCapability(
            hCamera
        )

        print(
            f"maximum resolution: "
            f"{cap.sResolutionRange.iWidthMax} x"
            f"{cap.sResolutionRange.iHeightMax}"
        )

        # ---------------------------------------------------------
        # 5. Determine whether camera is monochrome or color
        # ---------------------------------------------------------
        monoCamera = (cap.sIspCapacity.bMonoSensor != 0)

        if monoCamera:
            print("Camera type: Monochrome")
            mvsdk.CameraSetIspOutFormat(hCamera, mvsdk.CAMERA_MEDIA_TYPE_MONO8)

        else:
            print("Camera type: Color")
            mvsdk.CameraSetIspOutFormat(hCamera, mvsdk.CAMERA_MEDIA_TYPE_BGR8)

        # ---------------------------------------------------------
        # 6. Configure Trigger Mode 
        # ---------------------------------------------------------
        print(
            f"Setting trigger mode: "
            f"{TRIGGER_MODE}"
        )

        status = mvsdk.CameraSetTriggerMode(hCamera, TRIGGER_MODE)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            print("Failed to set Trigger mode")

        print("Hardware trigger configured")

        # ---------------------------------------------------------
        # 7. Disable auto exposure
        # ---------------------------------------------------------
        status = mvsdk.CameraSetAeState(hCamera, 0)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            print("Failed to disable auto exposure")

        # ---------------------------------------------------------
        # 8. Set exposure time
        # ---------------------------------------------------------
        print(
            f"Exposure time: "
            f"{EXPOSURE_TIME_US} us"
        )

        status = mvsdk.CameraSetExposureTime(hCamera, EXPOSURE_TIME_US)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            print("Failed to set exposure time.")

        # ---------------------------------------------------------
        # 9. Start camera
        # ---------------------------------------------------------
        print("Starting Camera..")

        status = mvsdk.CameraPlay(hCamera)

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            print("Failed to start the camera.")
            return 

        print("Camera Started..")

        # ---------------------------------------------------------
        # 10. Allocate image processing buffer 
        # ---------------------------------------------------------
        FrameBufferSize = (
            cap.sResolutionRange.iWidthMax
            * cap.sResolutionRange.iHeightMax 
            * (1 if monoCamera else 3)
        )

        pFrameBuffer = mvsdk.CameraAlignMalloc(FrameBufferSize, 16)

        if not pFrameBuffer:
            print("failed to allocate frame buffer")
            return

        # ---------------------------------------------------------
        # 11. Register callback
        # ---------------------------------------------------------
        print("Registering callback...")

        status = mvsdk.CameraSetCallbackFunction(
            hCamera, 
            grab_callback, 
            0
        )

        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            print("failed to register callback")
            return

        print("\nWaiting for hardware trigger...")
        print("Press Q in the image window to exit")

        # ---------------------------------------------------------
        # 11-1. Other configurations
        # ---------------------------------------------------------

        status = mvsdk.CameraSetExtTrigSignalType(hCamera, TRIGGER_EDGE)
        if status != mvsdk.CAMERA_STATUS_SUCCESS:
            print("Failed to set trigger mode. ")

        gain_range = mvsdk.CameraGetAnalogGainXRange(hCamera)
        print("Analog gain range: ", gain_range)

        current_gain = mvsdk.CameraGetGain(hCamera)
        print("Current RGB gain range: ", current_gain)

        # ---------------------------------------------------------
        # 12. Main waiting loop
        # ---------------------------------------------------------
        while not quit_requested:
            # We simply keep the application alive here
            cv2.waitKey(10)

    except mvsdk.CameraException as e:
        print(f"\nCamera Rrror: {e}")

    except Exception as e:
        print(f"\nUnexpected Error: {e}")
        traceback.print_exc()

    finally:
        # ---------------------------------------------------------
        # 13. Stop camera
        # ---------------------------------------------------------
        if hCamera:
            try:
                mvsdk.CameraStop(hCamera)

            except Exception:
                pass


            # ---------------------------------------------------------
            # 14. Uninitialize Camera
            # ---------------------------------------------------------
            try:
                mvsdk.CameraUnInit(hCamera)

            except Exception:
                pass

        # ---------------------------------------------------------
        # 15. Free image Buffer
        # ---------------------------------------------------------
        if pFrameBuffer:
            try:
                mvsdk.CameraAlignFree(pFrameBuffer)
            except Exception:
                pass
            pFrameBuffer = 0

        # ---------------------------------------------------------
        # 16. Close openCV windows
        # ---------------------------------------------------------
        cv2.destroyAllWindows()
        print("\nCamera system stopped")


if __name__ =="__main__":
    main()
        