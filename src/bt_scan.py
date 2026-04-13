"""
bt_scan.py — Scan for the printer's BLE services.

Checks whether the printer advertises BLE (GATT) services in addition to
or instead of Classic BT SPP. If it shows up here with writable
characteristics, BLE is the real data channel.

Run:
    uv run src/bt_scan.py
"""

import asyncio
from bleak import BleakScanner, BleakClient

# From system_profiler
PRINTER_BT_ADDR = "DC:0D:51:68:2A:6E"


async def scan_all():
    """Quick scan — list all BLE devices nearby."""
    print("Scanning for BLE devices (5s)...\n")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in sorted(devices, key=lambda x: x.rssi or -999, reverse=True):
        print(f"  {d.address}  RSSI={d.rssi:>4}  {d.name or '(no name)'}")
    return [d for d in devices if d.address.upper() == PRINTER_BT_ADDR.upper()]


async def inspect_services(address: str):
    """Connect and list all GATT services and characteristics."""
    print(f"\nConnecting to {address} via BLE ...")
    try:
        async with BleakClient(address, timeout=10.0) as client:
            print(f"Connected: {client.is_connected}\n")
            for svc in client.services:
                print(f"  Service: {svc.uuid}  ({svc.description})")
                for char in svc.characteristics:
                    flags = ", ".join(char.properties)
                    print(f"    Char: {char.uuid}  [{flags}]  ({char.description})")
    except Exception as e:
        print(f"  BLE connect failed: {e}")
        print("  → Printer may be Classic BT only (no BLE GATT server).")


async def main():
    matches = await scan_all()

    if not matches:
        print(f"\nPrinter ({PRINTER_BT_ADDR}) not found in BLE scan.")
        print("It may be Classic BT only — BLE scanning won't see it.")
        print("Proceeding to direct GATT connect attempt anyway...\n")

    await inspect_services(PRINTER_BT_ADDR)


if __name__ == "__main__":
    asyncio.run(main())
