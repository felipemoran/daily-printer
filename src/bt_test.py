"""
bt_test.py — DEAD END: Classic BT SPP investigation script.

DO NOT USE for printing. Kept for reference only.

Classic BT via /dev/cu.MPT-II does not work on macOS — the RFCOMM link
is never established when a script opens the serial port. Data is silently
dropped. See docs/setup-bluetooth-investigation.md for full details.

Printing over Bluetooth works via BLE (GATT/MLDP). Use open_printer()
from printer.py — it auto-selects USB or BLE.
"""
