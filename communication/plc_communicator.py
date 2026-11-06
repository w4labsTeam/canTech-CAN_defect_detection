
import time
import threading

from pymodbus.client import ModbusSerialClient


class PLCCommunicator:
    """
    Handles Modbus RTU communication with the Xinje XC3-24T-E PLC
    through a USB-to-RS485 adapter.
    """

    def __init__(
        self,
        port="COM3",
        baudrate=115200,
        slave_id=1,
        timeout=1.0,
    ):
        self.port = port
        self.baudrate = baudrate
        self.slave_id = slave_id
        self.timeout = timeout

        self.client = ModbusSerialClient(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="E",
            stopbits=1,
            timeout=self.timeout,
        )

        # Prevent simultaneous serial transactions.
        self.lock = threading.Lock()

    # -------------------------------------------------
    # Connection management
    # -------------------------------------------------

    def connect(self):
        """Connect to the PLC."""

        print(f"[PLC] Connecting to {self.port}...")

        connected = self.client.connect()

        if connected:
            print("[PLC] Connected successfully.")
        else:
            print("[PLC ERROR] Connection failed.")

        return connected

    def disconnect(self):
        """Close the PLC connection."""

        if self.client:
            self.client.close()

        print("[PLC] Connection closed.")

    def is_connected(self):
        """Check connection state."""

        return self.client.connected

    # -------------------------------------------------
    # Register operations
    # -------------------------------------------------

    def write_register(self, address, value):
        """
        Write a single holding register.

        Returns True if successful, otherwise False.
        """

        with self.lock:

            if not self.is_connected():
                print("[PLC ERROR] Not connected.")
                return False

            try:
                response = self.client.write_register(
                    address=address,
                    value=value,
                    device_id=self.slave_id,
                )

                if response.isError():
                    print(
                        f"[PLC ERROR] Write failed: "
                        f"D{address} = {value}"
                    )
                    return False

                return True

            except Exception as exc:
                print(f"[PLC ERROR] Write exception: {exc}")
                return False

    def read_register(self, address):
        """
        Read a single holding register.

        Returns the register value, or None if unsuccessful.
        """

        with self.lock:

            if not self.is_connected():
                print("[PLC ERROR] Not connected.")
                return None

            try:
                response = self.client.read_holding_registers(
                    address=address,
                    count=1,
                    device_id=self.slave_id,
                )

                if response.isError():
                    print(
                        f"[PLC ERROR] Read failed: D{address}"
                    )
                    return None

                return response.registers[0]

            except Exception as exc:
                print(f"[PLC ERROR] Read exception: {exc}")
                return None
