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
    # return_adv=True gives (BLEDevice, AdvertisementData) tuples
    results = await BleakScanner.discover(timeout=5.0, return_adv=True)
    found = []
    for addr, (device, adv) in results.items():
        print(f"  {device.address}  RSSI={adv.rssi:>4}  {device.name or '(no name)'}")
        if device.address.upper() == PRINTER_BT_ADDR.upper():
            found.append(device)
    return found


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
        print(f"\nPrinter ({PRINTER_BT_ADDR}) not found by hardware MAC — trying by name...\n")
        # macOS exposes BLE devices under a randomised UUID, not the hardware MAC.
        # Re-scan and match by device name instead.
        results = await BleakScanner.discover(timeout=5.0, return_adv=True)
        for addr, (device, adv) in results.items():
            if device.name and "MPT" in device.name.upper():
                print(f"Found by name: {device.name}  UUID={device.address}")
                matches.append(device)

    if not matches:
        print("Printer not found in BLE scan at all.")
        return

    for device in matches:
        await inspect_services(device.address)


if __name__ == "__main__":
    asyncio.run(main())
