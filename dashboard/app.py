
"""
Main Flask application for the CAN inspection dashboard.
"""
import json
import time 

from flask import Flask, jsonify, Response, stream_with_context, render_template

from dashboard.data_manager import DashboardDataManager
from dashboard.mqtt_client import DashboardMQTTClient


# ---------------------------------------------------------
# INITIALIZE APPLICATION
# ---------------------------------------------------------

app = Flask(__name__)

# Central dashboard data manager.
data_manager = DashboardDataManager()

# MQTT subscriber.
mqtt_subscriber = DashboardMQTTClient(
    data_manager=data_manager,
    host="127.0.0.1",
    port=1883,
)


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )

@app.route("/api/health")
def health():

    data = data_manager.get_dashboard_data()

    return jsonify({

        "flask": "RUNNING",

        "mqtt": (
            "CONNECTED"
            if data["mqtt_connected"]
            else "DISCONNECTED"
        ),

    })


@app.route("/api/data")
def get_dashboard_data():

    return jsonify(
        data_manager.get_dashboard_data()
    )

@app.route("/events")
def events():
    @stream_with_context
    def event_stream():
        print("[SSE] Browser connected.")

        try:
            while True:
                # Retrieve latest dashboard data
                data = data_manager.get_dashboard_data()

                # Convert data into JSON
                payload = json.dumps(data)

                # Send a SSE event
                yield f"data: {payload}\n\n"

                # Update interval
                time.sleep(1.0)

        except GeneratorExit:
            print("[SSE] Browser disconnected.")

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )




# =========================================================
# APPLICATION ENTRY POINT
# =========================================================

def main():

    print("=" * 55)
    print("CAN INSPECTION DASHBOARD")
    print("=" * 55)

    # Start MQTT subscriber.
    mqtt_subscriber.start()

    try:

        # Start Flask web server.
        #
        # 0.0.0.0 allows other devices on the same LAN
        # to access the dashboard using this PC's IP.

        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            threaded=True,
            use_reloader=False,
        )

    except KeyboardInterrupt:

        print("\nDashboard shutdown requested.")

    finally:

        mqtt_subscriber.stop()

        print("Dashboard stopped.")


if __name__ == "__main__":
    main()
