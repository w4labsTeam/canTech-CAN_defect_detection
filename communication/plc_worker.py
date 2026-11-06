
"""
PLC worker for buffered CAN inspection results.

- Processes inspection results in FIFO order.
- Uses D100-D149 as a circular buffer.
- Supports graceful shutdown.
- Stops on communication or buffer faults.
- Preserves failed and unprocessed results for diagnosis.
"""

import threading
import traceback

from enum import Enum
from queue import Queue, Empty

from inspection.result import InspectionResult
from communication.plc_communicator import PLCCommunicator


# -------------------------------------------------------------
# PLC buffer configuration
# -------------------------------------------------------------

PLC_BUFFER_START = 100
PLC_BUFFER_SIZE = 50

PLC_RESULT_EMPTY = 0
PLC_RESULT_NORMAL = 1
PLC_RESULT_DEFECTIVE = 2
PLC_RESULT_ERROR = 3


class PLCWorkerState(Enum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    FAULT = "FAULT"


class PLCWorker:

    def __init__(
        self,
        result_queue: Queue,
        plc: PLCCommunicator | None = None,
    ):

        self.result_queue = result_queue

        self.plc = (
            plc if plc is not None
            else PLCCommunicator()
        )

        self.write_index = 0

        self.stop_event = threading.Event()
        self.fault_event = threading.Event()

        self.state = PLCWorkerState.STOPPED
        self.state_lock = threading.Lock()

        self.last_fault = None

        # Result that could not be confirmed as delivered.
        self.failed_result = None

        # Number of results successfully written.
        self.successful_writes = 0

        self.thread = threading.Thread(
            target=self._run,
            name="PLCWorker",
            daemon=False,
        )

    # ---------------------------------------------------------
    # State management
    # ---------------------------------------------------------

    def _set_state(self, state):

        with self.state_lock:
            self.state = state

    def _set_fault(self, message, result=None):

        self.last_fault = message
        self.failed_result = result

        self.fault_event.set()
        self._set_state(PLCWorkerState.FAULT)

        print(f"[PLC FAULT] {message}")

    # ---------------------------------------------------------
    # Start
    # ---------------------------------------------------------

    def start(self):

        if self.state != PLCWorkerState.STOPPED:
            raise RuntimeError(
                "PLC worker has already been started."
            )

        print("[PLC] Connecting...")

        if not self.plc.connect():

            self._set_fault(
                "Could not establish PLC connection."
            )

            raise ConnectionError(self.last_fault)

        self._set_state(PLCWorkerState.RUNNING)

        try:
            self.thread.start()

        except Exception:
            self.plc.disconnect()
            self._set_state(PLCWorkerState.FAULT)
            raise

        print("[PLC] Worker started.")

    # ---------------------------------------------------------
    # Convert inspection result
    # ---------------------------------------------------------

    def _get_plc_value(
        self,
        result: InspectionResult,
    ) -> int:

        if result.error is not None:
            return PLC_RESULT_ERROR

        if result.is_defective:
            return PLC_RESULT_DEFECTIVE

        return PLC_RESULT_NORMAL

    # ---------------------------------------------------------
    # Register addressing
    # ---------------------------------------------------------

    def _get_register_address(self):

        return PLC_BUFFER_START + self.write_index

    def _advance_write_index(self):

        self.write_index = (
            self.write_index + 1
        ) % PLC_BUFFER_SIZE

    # ---------------------------------------------------------
    # Write inspection result
    # ---------------------------------------------------------

    def _write_result(
        self,
        result: InspectionResult,
    ) -> bool:

        address = self._get_register_address()

        # Check whether the slot is empty.
        current_value = self.plc.read_register(address)

        if current_value is None:

            self._set_fault(
                f"Could not read D{address}.",
                result,
            )

            return False

        if current_value != PLC_RESULT_EMPTY:

            self._set_fault(
                f"Buffer slot D{address} is occupied "
                f"(value={current_value}).",
                result,
            )

            return False

        plc_value = self._get_plc_value(result)

        # Write the inspection decision.
        success = self.plc.write_register(
            address=address,
            value=plc_value,
        )

        if not success:

            self._set_fault(
                f"Write to D{address} failed for "
                f"frame {result.frame_id}. "
                "The PLC may or may not have received "
                "the write; manual reconciliation is required.",
                result,
            )

            return False

        print(
            f"[PLC] Frame {result.frame_id} "
            f"-> D{address} = {plc_value}"
        )

        self.successful_writes += 1

        # Advance only after a confirmed successful response.
        self._advance_write_index()

        return True

    # ---------------------------------------------------------
    # Worker thread
    # ---------------------------------------------------------

    def _run(self):

        try:

            while True:

                # Graceful shutdown:
                # Exit only after the queue has been drained.
                if (
                    self.stop_event.is_set()
                    and self.result_queue.empty()
                ):
                    break

                try:
                    result = self.result_queue.get(
                        timeout=0.1
                    )

                except Empty:
                    continue

                try:

                    if not self._write_result(result):
                        break

                finally:
                    self.result_queue.task_done()

        except Exception as exc:

            self._set_fault(
                f"Unexpected PLC worker exception: {exc}"
            )

            traceback.print_exc()

        finally:

            self.plc.disconnect()

            if self.state != PLCWorkerState.FAULT:
                self._set_state(PLCWorkerState.STOPPED)

            print("[PLC] Worker stopped.")

    # ---------------------------------------------------------
    # Stop
    # ---------------------------------------------------------

    def stop(self, timeout: float | None = 10.0):

        if self.state == PLCWorkerState.STOPPED:
            return

        if self.state == PLCWorkerState.FAULT:
            # A faulted worker cannot drain the queue.
            # Keep the pending results available for diagnosis.
            if self.thread.ident is not None:
                self.thread.join(timeout=timeout)

            if self.thread.is_alive():
                raise TimeoutError(
                    "Faulted PLC worker did not stop."
                )

            return

        self._set_state(PLCWorkerState.STOPPING)
        self.stop_event.set()

        if self.thread.ident is not None:
            self.thread.join(timeout=timeout)

        if self.thread.is_alive():
            raise TimeoutError(
                "PLC worker did not finish draining "
                "the queue within the timeout."
            )

    # ---------------------------------------------------------
    # Status
    # ---------------------------------------------------------

    def is_alive(self):
        return self.thread.is_alive()

    def get_status(self):

        with self.state_lock:
            current_state = self.state

        return {
            "state": current_state.value,
            "fault": self.last_fault,
            "successful_writes": self.successful_writes,
            "write_index": self.write_index,
            "failed_frame_id": (
                self.failed_result.frame_id
                if self.failed_result is not None
                else None
            ),
            "pending_queue_size": self.result_queue.qsize(),
        }
