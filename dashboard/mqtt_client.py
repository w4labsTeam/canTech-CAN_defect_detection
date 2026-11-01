
"""
MQTT subscriber for the CAN inspection dashboard.

Receives messages from the independent inspection application
and updates the central dashboard data manager.
"""

import json

import paho.mqtt.client as mqtt

from dashboard.data_manager import DashboardDataManager


# ---------------------------------------------------------
# MQTT CONFIGURATION
# ---------------------------------------------------------

MQTT_HOST = "127.0.0.1"
MQTT_PORT = 1883

STATISTICS_TOPIC = "can_inspection/statistics"
STATUS_TOPIC = "can_inspection/status"

MQTT_CLIENT_ID = "can_inspection_dashboard"


class DashboardMQTTClient:

    def __init__(
        self,
        data_manager: DashboardDataManager,
        host=MQTT_HOST,
        port=MQTT_PORT,
    ):

        self.data_manager = data_manager

        self.host = host
        self.port = port

        # -------------------------------------------------
        # Initialize MQTT client
        # -------------------------------------------------

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311,
        )

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.started = False

    # =====================================================
    # CONNECTION CALLBACKS
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

            print("[DASHBOARD MQTT] Connected to Mosquitto.")

            self.data_manager.set_mqtt_connection(True)

            # Subscribe to inspection statistics.
            client.subscribe(
                STATISTICS_TOPIC,
                qos=0,
            )

            # Subscribe to system status.
            client.subscribe(
                STATUS_TOPIC,
                qos=1,
            )

            print(
                f"[DASHBOARD MQTT] Subscribed to "
                f"{STATISTICS_TOPIC}"
            )

            print(
                f"[DASHBOARD MQTT] Subscribed to "
                f"{STATUS_TOPIC}"
            )

        else:

            self.data_manager.set_mqtt_connection(False)

            print(
                f"[DASHBOARD MQTT] Connection failed: "
                f"{reason_code}"
            )

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):

        self.data_manager.set_mqtt_connection(False)

        print(
            "[DASHBOARD MQTT] Disconnected from broker. "
            f"Reason: {reason_code}"
        )

    # =====================================================
    # MESSAGE CALLBACK
    # =====================================================

    def _on_message(self, client, userdata, msg):

        try:

            payload = msg.payload.decode("utf-8")

            data = json.loads(payload)

            if not isinstance(data, dict):

                raise ValueError(
                    "Expected a JSON object."
                )

            # ---------------------------------------------
            # Statistics message
            # ---------------------------------------------

            if msg.topic == STATISTICS_TOPIC:

                self.data_manager.update_statistics(data)

                print(
                    "[DASHBOARD MQTT] Statistics received: "
                    f"Total={data.get('total')}, "
                    f"Passed={data.get('passed')}, "
                    f"Defective={data.get('defective')}"
                )

            # ---------------------------------------------
            # Status message
            # ---------------------------------------------

            elif msg.topic == STATUS_TOPIC:

                self.data_manager.update_status(data)

                print(
                    "[DASHBOARD MQTT] System status updated."
                )

        except (UnicodeDecodeError, json.JSONDecodeError,
                ValueError, TypeError) as exc:

            print(
                f"[DASHBOARD MQTT] Invalid message on "
                f"{msg.topic}: {exc}"
            )

    # =====================================================
    # START MQTT CLIENT
    # =====================================================

    def start(self):

        if self.started:
            return

        print("[DASHBOARD MQTT] Starting subscriber...")

        self.client.connect_async(
            self.host,
            self.port,
            keepalive=30,
        )

        # Run MQTT network communication in background.
        self.client.loop_start()

        self.started = True

    # =====================================================
    # STOP MQTT CLIENT
    # =====================================================

    def stop(self):

        if not self.started:
            return

        print("[DASHBOARD MQTT] Stopping subscriber...")

        self.client.disconnect()

        self.client.loop_stop()

        self.data_manager.set_mqtt_connection(False)

        self.started = False

        print("[DASHBOARD MQTT] Subscriber stopped.")
