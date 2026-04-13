"""
bt_ble_test.py — BLE print test (run with USB unplugged to force BLE path).

Run:
    uv run python src/bt_ble_test.py
"""

from printer import open_printer

with open_printer() as p:
    p.set(align="center", bold=True)
    p.text("BLE OK\n")
    p.set(align="left", bold=False)
    p.text("Transport: BLE MLDP\n")
    p.ln(3)

print("Done.")
