"""
bt_test.py — Phase 1: Bluetooth communication test.

The printer pairs as Classic Bluetooth SPP, exposed by macOS as a
virtual serial port at /dev/cu.MPT-II.

Run:
    uv run src/bt_test.py
"""

from printer import open_printer_bt, BT_PORT, BT_BAUD


def run():
    print(f"Connecting via Bluetooth ({BT_PORT}) ...")
    p = open_printer_bt()
    print("Connected.\n")

    p.set(align="center", bold=True)
    p.text("BT OK\n")
    p.set(align="left", bold=False)
    p.text(f"Port: {BT_PORT}\n")
    p.text(f"Baud: {BT_BAUD}\n")
    p.ln(3)
    p.close()

    print("Done.")


if __name__ == "__main__":
    run()
