# Bluetooth Investigation — RESOLVED

**Outcome:** BLE (GATT/MLDP) works. Classic BT SPP via `/dev/cu` does not.
Use `open_printer()` from `src/printer.py` — it auto-selects USB or BLE.

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

## Key lesson: BLE requires a single session

Two sequential `asyncio.run()` calls (scan then send = two BLE connections) causes
the printer to miss the second connection. Scan, connect, send, and disconnect must
all happen within one `async` function and one `asyncio.run()` call.

## BLE quirks

- **Connection beep**: the printer beeps on every BLE connect. USB is silent.
  This is why USB is the preferred transport.
- **macOS BLE UUID is randomised**: the hardware MAC (`DC:0D:51:68:2A:6E`) is not
  usable for BLE on macOS. Discover the printer by name `"MPT-II"` at scan time.
- **All three writable GATT characteristics accept ESC/POS data.** MLDP is used
  as the canonical one.

## Transport API

`open_printer()` in `src/printer.py` is the single entry point.
It detects USB availability via `usb.core.find()` (fast, no timeout) and falls
back to BLE only when USB is absent.

```python
with open_printer() as p:   # USB if plugged in, BLE otherwise
    p.text("Hello\n")
    p.ln(3)
```

- **USB**: live `Usb` escpos object — commands sent immediately
- **BLE**: `Dummy` buffer — commands accumulated, sent in bulk on context exit

## Printer BT details

| Field | Value |
|---|---|
| Device name | MPT-II |
| Hardware BT address | DC:0D:51:68:2A:6E |
| macOS BLE UUID | `AF022728-500A-77C3-1C2F-642EBCFF81C6` (randomised, may change) |
| macOS SPP port | `/dev/cu.MPT-II` (Classic BT — does not work from scripts) |
| Manufacturer | YAEN |
| Firmware | 1.0 |
| BLE data service | Microchip MLDP (`49535343-fe7d-4ae5-8fa9-9fafd205e455`) |
| BLE TX characteristic | `49535343-8841-43f4-a8d4-ecbe34729bb3` (write-without-response) |
| BLE RX characteristic | `49535343-1e4d-4bd9-ba61-23c647249616` (notify) |
| MTU chunk size | 20 bytes (safe floor) |

## GATT services summary

| Service UUID | Description |
|---|---|
| `49535343-fe7d-4ae5-8fa9-9fafd205e455` | **Microchip MLDP** — used for ESC/POS data |
| `e7810a71-73ae-499d-8c15-faa9aef0c3f2` | Unknown — also accepts ESC/POS data |
| `000018f0-0000-1000-8000-00805f9b34fb` | Vendor specific — also accepts ESC/POS data |
| `0000180a-0000-1000-8000-00805f9b34fb` | Device Information (read-only) |
