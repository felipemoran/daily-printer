# Bluetooth Investigation

## What was tested

The printer advertises Classic Bluetooth (Bluetooth 4.0, paired as "MPT-II").
macOS creates `/dev/cu.MPT-II` and `/dev/tty.MPT-II` virtual serial ports when paired.

Tested:
- `pyserial` via `/dev/cu.MPT-II` at all standard baud rates (9600–115200)
- Raw ESC/POS bytes via `pyserial` (bypassing python-escpos)
- Plain ASCII without any ESC commands
- Various flow control settings (`dsrdtr`, `rtscts`)
- BLE scan via `bleak` (crashed — see below)

## Root cause: RFCOMM link never established

Opening `/dev/cu.MPT-II` with `pyserial` succeeds and `write()` returns the
correct byte count, but no data reaches the printer. Confirmed by checking
`system_profiler SPBluetoothDataType` while the port is held open — the printer
does **not** appear in the "Connected" section.

macOS creates the `/dev/cu` device for any paired Bluetooth device that
advertises an RFCOMM service, but does **not** auto-establish the RFCOMM link
when a script opens the serial port. Data is accepted into a local OS buffer
and silently dropped.

The printer showed as "Connected" (with services `0x802000 <Braille ACL>`)
during initial pairing/reconnect, but this was a macOS-initiated transient
connection — not triggered by opening the port.

## BLE scan

`bleak` (v3.0.1) crashed immediately with `SIGABRT` (exit 134). This is a macOS
privacy gate — Terminal must be granted Bluetooth access in:

> System Settings → Privacy & Security → Bluetooth

Until that permission is granted, it's unknown whether the printer also
advertises BLE GATT services.

## What would be needed to make BT work

1. **Grant Bluetooth permission** to Terminal (or the Python binary) in Privacy settings.
2. **Re-run `src/bt_scan.py`** to check if the printer has BLE GATT characteristics.
3. If BLE GATT: implement printing via `bleak` writing to the writable characteristic.
4. If Classic BT only: investigate why macOS doesn't auto-connect the RFCOMM link
   (may require using `IOBluetooth` via PyObjC to explicitly open the RFCOMM channel).

## Decision

**USB is the primary transport for this project.**

USB works reliably, requires no pairing state, and the printer is desk-bound.
Bluetooth may be revisited if wireless operation is needed.

## Printer BT details

| Field | Value |
|---|---|
| Device name | MPT-II |
| BT address | DC:0D:51:68:2A:6E |
| macOS serial port | `/dev/cu.MPT-II` |
| Advertised service | `0x802000` (Braille ACL per macOS) |
| Minor device type | Printer |
