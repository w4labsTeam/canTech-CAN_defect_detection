
import time

from communication.plc_communicator import PLCCommunicator


PLC_REGISTER = 100

plc = PLCCommunicator(
    port="COM3",
    baudrate=115200,
    slave_id=1,
)

try:
    # Connect
    if not plc.connect():
        raise ConnectionError("PLC connection failed!")

    # Test writing
    print("\nTesting register writing...")

    for value in [1, 0, 1, 0]:

        success = plc.write_register(
            PLC_REGISTER,
            value
        )

        if success:
            print(f"D100 = {value}")
        else:
            print("Write failed!")

        time.sleep(0.5)

    # Test reading
    print("\nTesting register reading...")

    value = plc.read_register(PLC_REGISTER)

    if value is not None:
        print(f"Read D100 = {value}")
    else:
        print("Read failed!")

except KeyboardInterrupt:
    print("\nTest stopped.")

except Exception as exc:
    print(f"[TEST ERROR] {exc}")

finally:
    plc.disconnect()
