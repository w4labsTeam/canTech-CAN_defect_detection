
"""
MQTT statistics publisher for the CAN inspection system.

Responsibilities:
    - Maintain thread-safe inspection counters.
    - Track session and lifetime statistics.
    - Calculate the recent inspection rate.
    - Publish statistics periodically using MQTT.
    - Publish system status when it changes.

The inspection application never performs network operations
when calling record_result().
"""

import json
import threading
import time

from collections import deque
from datetime import datetime, timezone

import paho.mqtt.client as mqtt


# ---------------------------------------------------------
# MQTT configuration
# ---------------------------------------------------------

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883

STATISTICS_TOPIC = "can_inspection/statistics"
STATUS_TOPIC = "can_inspection/status"

PUBLISH_INTERVAL = 1.0
IDLE_RESET_SECONDS = 60.0
RATE_WINDOW_SECONDS = 5.0


class CANInspectionMQTT:

    def __init__(
        self,
        host=MQTT_HOST,
        port=MQTT_PORT,
        publish_interval=PUBLISH_INTERVAL,
        idle_reset_seconds=IDLE_RESET_SECONDS,
        rate_window_seconds=RATE_WINDOW_SECONDS,
    ):

        self.host = host
        self.port = port

        self.publish_interval = publish_interval
        self.idle_reset_seconds = idle_reset_seconds
        self.rate_window_seconds = rate_window_seconds

        # -------------------------------------------------
        # Thread synchronization
        # -------------------------------------------------

        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        self.publisher_thread = None

        # -------------------------------------------------
        # Session counters
        # -------------------------------------------------

        self.total_count = 0
        self.passed_count = 0
        self.defective_count = 0
        self.error_count = 0

        # -------------------------------------------------
        # Lifetime counters
        # -------------------------------------------------

        self.lifetime_total = 0
        self.lifetime_passed = 0
        self.lifetime_defective = 0
        self.lifetime_errors = 0

        # -------------------------------------------------
        # Session timing
        # -------------------------------------------------

        self.session_started_at = datetime.now(timezone.utc)
        self.last_detection_time = None

        # Store timestamps of successfully classified CANs.
        self.rate_events = deque()

        # -------------------------------------------------
        # System status
        # -------------------------------------------------

        self.status = {
            "camera": "STARTING",
            "ai_model": "STARTING",
            "inspection_service": "STARTING",
            "mqtt": "DISCONNECTED",
        }

        # -------------------------------------------------
        # MQTT client (Paho MQTT 2.x)
        # -------------------------------------------------

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="can_inspection_pc",
            protocol=mqtt.MQTTv311,
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        # Last Will and Testament.
        # Broker publishes this if the client disconnects
        # unexpectedly.

        will_message = {
            "camera": "UNKNOWN",
            "ai_model": "UNKNOWN",
            "inspection_service": "OFFLINE",
            "mqtt": "OFFLINE",
        }

        self.client.will_set(
            STATUS_TOPIC,
            json.dumps(will_message),
            qos=1,
            retain=True,
        )

    # =====================================================
    # INSPECTION RESULT MANAGEMENT
    # =====================================================

    def record_result(self, result):
        """
        Record one completed inspection.

        This method is intentionally lightweight.

        It does NOT publish MQTT messages.
        It does NOT wait for network communication.
        """

        now = time.monotonic()

        with self.lock:

            # Inspection error: do not count it as PASS.
            if result.error is not None:

                self.error_count += 1
                self.lifetime_errors += 1

                return

            # Reset session counters after an idle period.
            if (
                self.last_detection_time is not None
                and now - self.last_detection_time
                >= self.idle_reset_seconds
            ):
                self._reset_session_locked()

            # Update session and lifetime totals.
            self.total_count += 1
            self.lifetime_total += 1

            if result.is_defective:

                self.defective_count += 1
                self.lifetime_defective += 1

            else:

                self.passed_count += 1
                self.lifetime_passed += 1

            self.last_detection_time = now

            # Store event timestamp for rate calculation.
            self.rate_events.append(now)

    # =====================================================
    # SESSION MANAGEMENT
    # =====================================================

    def _reset_session_locked(self):
        """
        Reset only session counters.

        Caller must already hold self.lock.
        """

        self.total_count = 0
        self.passed_count = 0
        self.defective_count = 0
        self.error_count = 0

        self.last_detection_time = None

        self.rate_events.clear()

        self.session_started_at = datetime.now(timezone.utc)

    # =====================================================
    # STATISTICS
    # =====================================================

    def get_statistics(self):
        """
        Return a consistent snapshot of all statistics.
        """

        now = time.monotonic()

        with self.lock:

            # Handle inactivity even if no new result arrives.
            if (
                self.last_detection_time is not None
                and now - self.last_detection_time
                >= self.idle_reset_seconds
            ):
                self._reset_session_locked()

            # Remove events outside the rolling time window.
            while (
                self.rate_events
                and now - self.rate_events[0]
                > self.rate_window_seconds
            ):
                self.rate_events.popleft()

            # Calculate CANs per minute.
            inspection_rate = 0.0

            if len(self.rate_events) >= 2:

                elapsed = (
                    self.rate_events[-1]
                    - self.rate_events[0]
                )

                if elapsed > 0:

                    inspection_rate = (
                        (len(self.rate_events) - 1)
                        / elapsed
                    ) * 60.0

            # Calculate defect percentage.
            defect_percentage = 0.0

            if self.total_count > 0:

                defect_percentage = (
                    self.defective_count
                    / self.total_count
                ) * 100.0

            return {

                # Session statistics
                "total": self.total_count,
                "passed": self.passed_count,
                "defective": self.defective_count,
                "errors": self.error_count,

                "defect_percentage": round(
                    defect_percentage, 2
                ),

                "inspection_rate": round(
                    inspection_rate, 2
                ),

                # Lifetime statistics
                "lifetime_total": self.lifetime_total,
                "lifetime_passed": self.lifetime_passed,
                "lifetime_defective": self.lifetime_defective,
                "lifetime_errors": self.lifetime_errors,

                "timestamp": datetime.now(
                    timezone.utc
                ).isoformat(),

            }

    # =====================================================
    # SYSTEM STATUS
    # =====================================================

    def set_status(self, **kwargs):
        """
        Update one or more system status fields.

        Example:
            set_status(camera="RUNNING")
        """

        allowed_fields = {
            "camera",
            "ai_model",
            "inspection_service",
        }

        updates = {
            key: str(value).upper()
            for key, value in kwargs.items()
            if key in allowed_fields
        }

        if not updates:
            return

        with self.lock:
            self.status.update(updates)

        self._publish_status()

    def _publish_status(self):

        if not self.client.is_connected():
            return

        with self.lock:
            payload = dict(self.status)

        try:
            self.client.publish(
                STATUS_TOPIC,
                json.dumps(payload),
                qos=1,
                retain=True,
            )

        except Exception as exc:
            print(f"[MQTT STATUS ERROR] {exc}")

    # =====================================================
    # MQTT CALLBACKS
    # =====================================================

    def _on_connect(
        self,
        client,
        userdata,
        flags,
        reason_code,
        properties,
    ):

        if reason_code == 0:

            print("[MQTT] Connected to Mosquitto.")

            with self.lock:
                self.status["mqtt"] = "CONNECTED"

            self._publish_status()

        else:

            print(
                f"[MQTT] Connection failed: {reason_code}"
            )

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):

        with self.lock:
            self.status["mqtt"] = "DISCONNECTED"

        print("[MQTT] Disconnected from Mosquitto.")

    # =====================================================
    # STATISTICS PUBLISHER
    # =====================================================

    def _publish_loop(self):
        """
        Dedicated thread for periodic MQTT statistics.

        Inspection processing never waits for this thread.
        """

        while not self.stop_event.wait(
            self.publish_interval
        ):

            if not self.client.is_connected():
                continue

            statistics = self.get_statistics()

            try:

                payload = json.dumps(statistics)

                result = self.client.publish(
                    STATISTICS_TOPIC,
                    payload,
                    qos=0,
                    retain=True,
                )

                if result.rc != mqtt.MQTT_ERR_SUCCESS:

                    print(
                        "[MQTT] Statistics publish "
                        f"not queued. Return code: {result.rc}"
                    )

            except Exception as exc:

                print(
                    f"[MQTT PUBLISH ERROR] {exc}"
                )

    # =====================================================
    # START / STOP
    # =====================================================

    def start(self):
        """
        Start MQTT networking and statistics publishing.
        """

        print("[MQTT] Starting publisher...")

        # connect_async avoids blocking application startup
        # while waiting for the broker.
        self.client.connect_async(
            self.host,
            self.port,
            keepalive=30,
        )

        # Paho handles network communication in its own thread.
        self.client.loop_start()

        self.publisher_thread = threading.Thread(
            target=self._publish_loop,
            name="MQTTStatisticsPublisher",
            daemon=True,
        )

        self.publisher_thread.start()

    def stop(self):
        """
        Stop publishing and close MQTT communication.
        """

        print("[MQTT] Stopping publisher...")

        self.stop_event.set()

        if self.publisher_thread is not None:

            self.publisher_thread.join(timeout=3.0)

        self.set_status(
            inspection_service="STOPPED",
            camera="STOPPED",
        )

        # Publish final MQTT status before disconnecting.
        if self.client.is_connected():

            with self.lock:
                self.status["mqtt"] = "OFFLINE"

            self._publish_status()

        self.client.disconnect()
        self.client.loop_stop()

        print("[MQTT] Publisher stopped.")
