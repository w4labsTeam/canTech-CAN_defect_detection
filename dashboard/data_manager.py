
"""
Central data manager for the CAN inspection dashboard.

Stores the latest statistics and system status received
from the MQTT subscriber.
"""

import threading
from datetime import datetime, timezone


class DashboardDataManager:

    def __init__(self):

        self.lock = threading.Lock()

        # Latest production statistics
        self.statistics = {
            "total": 0,
            "passed": 0,
            "defective": 0,
            "errors": 0,
            "defect_percentage": 0.0,
            "inspection_rate": 0.0,
            "lifetime_total": 0,
            "lifetime_passed": 0,
            "lifetime_defective": 0,
            "lifetime_errors": 0,
            "timestamp": None,
        }

        # Latest system status
        self.status = {
            "camera": "UNKNOWN",
            "ai_model": "UNKNOWN",
            "inspection_service": "UNKNOWN",
            "mqtt": "DISCONNECTED",
        }

        # MQTT connection information
        self.mqtt_connected = False

        self.last_statistics_received = None
        self.last_status_received = None

    # -----------------------------------------------------
    # UPDATE STATISTICS
    # -----------------------------------------------------

    def update_statistics(self, data):

        with self.lock:

            self.statistics.update(data)

            self.last_statistics_received = (
                datetime.now(timezone.utc).isoformat()
            )

    # -----------------------------------------------------
    # UPDATE SYSTEM STATUS
    # -----------------------------------------------------

    def update_status(self, data):

        with self.lock:

            self.status.update(data)

            self.last_status_received = (
                datetime.now(timezone.utc).isoformat()
            )

    # -----------------------------------------------------
    # MQTT CONNECTION STATUS
    # -----------------------------------------------------

    def set_mqtt_connection(self, connected):

        with self.lock:

            self.mqtt_connected = bool(connected)

            self.status["mqtt"] = (
                "CONNECTED" if connected else "DISCONNECTED"
            )

    # -----------------------------------------------------
    # GET COMPLETE DASHBOARD DATA
    # -----------------------------------------------------

    def get_dashboard_data(self):

        with self.lock:

            return {
                "statistics": self.statistics.copy(),
                "status": self.status.copy(),
                "mqtt_connected": self.mqtt_connected,
                "last_statistics_received":
                    self.last_statistics_received,
                "last_status_received":
                    self.last_status_received,
            }
