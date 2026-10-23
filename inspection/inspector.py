"""
Runs the inspection worker, consumes frames and publishes results 
"""

import threading
import traceback

from queue import Queue, Empty, Full

from acquisition.capture import (
    FramePackets,
    frame_queue,
)

from inspection.base import BaseInspector
from inspection.result import InspectionResult
from inspection.ml.yolo_obb_inspector import YOLOOBBInspector

# Maximum number of completed resullts waiting for the application 
RESULT_QUEUE_SIZE = 100


class InspectionWorker:
    """
    Consumes acquiredd frames and publishes inspection results 
    """

    def __init__(
        self,
        inspector: BaseInspector | None=None,
        input_queue: Queue | None=None,
        output_queue: Queue | None=None,
    ):
        self.input_queue = (
            input_queue if input_queue is not None else frame_queue
        )

        self.result_queue = (
            output_queue
            if output_queue is not None
            else Queue(maxsize=RESULT_QUEUE_SIZE)
        )

        self.inspector = (
            inspector if inspector is not None
            else YOLOOBBInspector()
        )

        self.stop_event = threading.Event()
        self.fault_event = threading.Event()
        self.last_fault = None

        self.thread = threading.Thread(
            target=self.run,
            name="InspectionWorker",
            daemon=False,
        )


    def start(self):
        """
        Start the inspection worker thread
        """
        self.thread.start()


    def _run(self):
        try:
            while not self.stop_event.is_set():

                try:
                    packet: FramePacket = self.input_queue.get(
                        timeout=0.1
                    )

                except Empty:
                    continue

                try:
                    result = self.inspector.inspect(
                        image=packet.image,
                        frame_id=packet.frame_id,
                        timestamp_ns=packet.timestamp_ns,
                    )

                    # Never silently discard an inspection result.
                    try:
                        self.result_queue.put_nowait(result)

                    except Full:
                        self.last_fault = (
                            "Result queue full."
                            f"Result for frame {result.frame_id}"
                            "Could not be stored"
                        )
                        self.fault_event.set()
                        self.stop_event.set()
                        break

                finally:
                    """
                    Mark this input frame as consumed, including when inspection raises an 
                    exception.
                    """
                    self.input_queue.task_done()

        except Exception as exc:
            self.last_fault = (
                f"Inspection worker failed: {exc}"
            )    

            self.fault_event.set()
            traceback.print_exc()

        finally:
            try:
                self.inspector.close()
            except Exception:
                traceback.print_exc()


    def get_result(
        self,
        timeout: float | None=None,
    ):
        """
        Retrieve the next result from the application-facing queue
        """
        return self.result_queue.get(timeout=timeout)


    def stop(
        self,
        timeout: float | None=5.0,
    ):
        """
        Request shutdown and wait for the worker to finish
        """
        self.stop_event.set()
        if self.thread.ident is not None:
            self.thread.join(timeout=timeout)

        if self.thread.is_alive():
            raise TimeoutError(
                "Inspection worker did not stop within the timeout"
            )
        

            
