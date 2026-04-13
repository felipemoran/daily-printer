"""
bt_raw_test.py — Bare pyserial test, no escpos layer.

Tries several baud rates and sends raw ESC/POS bytes to see which one
makes the printer respond. Run and observe which baud triggers output.

Run:
    uv run src/bt_raw_test.py
"""

import time
import serial
from printer import BT_PORT

# ESC @ = initialize printer
ESC_INIT = b"\x1b@"
# Print "HELLO\n" + feed 3 lines
TEST_TEXT = b"HELLO BT RAW\n\n\n"

BAUD_RATES = [9600, 19200, 38400, 57600, 115200]


def try_baud(baud: int) -> None:
    print(f"  Trying {baud} baud ... ", end="", flush=True)
    try:
        port = serial.Serial(
            port=BT_PORT,
            baudrate=baud,
            timeout=2,
            dsrdtr=False,
            rtscts=False,
            xonxoff=False,
        )
    except serial.SerialException as e:
        print(f"OPEN FAILED: {e}")
        return

    written = port.write(ESC_INIT + TEST_TEXT)
    port.flush()
    time.sleep(0.5)
    port.close()
    print(f"sent {written} bytes — check printer")
    time.sleep(2)  # pause between attempts so you can observe the printout


if __name__ == "__main__":
    print(f"Port: {BT_PORT}\n")
    print("Each attempt sends ESC @ + 'HELLO BT RAW' + 3 line feeds.")
    print("Watch the printer — the baud that produces output is the correct one.\n")

    for baud in BAUD_RATES:
        try_baud(baud)

    print("\nDone. Set BT_BAUD in printer.py to whichever baud printed.")
