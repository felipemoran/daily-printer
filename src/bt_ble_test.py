"""
bt_ble_test.py — BLE print test using the shared printer module.

Run:
    uv run python src/bt_ble_test.py
"""

from printer import open_printer_ble

with open_printer_ble() as p:
    p.set(align="center", bold=True)
    p.text("BLE OK\n")
    p.set(align="left", bold=False)
    p.text("Transport: BLE MLDP\n")
    p.ln(3)

print("Done.")
