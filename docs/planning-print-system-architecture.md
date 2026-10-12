# Planning: print system architecture

Decided 2026-10-12. Nothing in this document is built yet.

## Goals

- Print any content on receipt printers at home and at the office.
- Robust and simple: set and forget. This is a side project with little maintenance time.
- Easy to add new ticket types.
- Automations and other people (friends, colleagues) can send prints.
- Fast prints are a direction, not a hard budget. Optimise later.

## Shape

```
senders: CLI, cron, web form, Telegram bot
        |  HTTPS
        v
print.<zone> (Cloudflare Tunnel, no open router ports)
        |
        v
server: Intel Mac at home
  intake -> queue -> render (Chromium kept running) -> dither -> ESC/POS bytes
        ^
        |  WebSocket, opened by the device
        |
printer devices: Mac (Apple silicon, Intel), Raspberry Pi 2/3, ESP32-S3
        |  USB
        v
receipt printer
```

| Decision | Choice |
|---|---|
| Server | The dedicated Intel Mac at home runs intake, queue, rendering and device connections, in Python. |
| Public access | Cloudflare Tunnel gives the server a public hostname. Devices, senders and the work computer all use it. |
| Tailscale | Only for your own admin access. Devices do not need it: the work computer is on the work tailnet. |
| What a device receives | ESC/POS bytes. The server holds each printer's settings. |
| Who opens the connection | The device opens a WebSocket to the server and keeps it open. |

## Device protocol

These rules go into device firmware, so they are expensive to change later.

- Each device has its own token. Every job is addressed to one printer id.
- The server sends a job as a series of small binary frames, about 4 KB each. The device writes each frame to USB as it arrives. An ESP32 never holds a whole job in memory.
- The device confirms a job after the last frame is written to the printer.
- The device sends a heartbeat, and reconnects with a growing delay when the connection drops.

## Job lifecycle

- The writer of a job sets its expiry. A job not confirmed before its expiry is dropped.
- The server sends an unconfirmed job again when the device reconnects. It stops after 3 attempts in total and marks the job failed. A duplicate print is possible when a device dies between printing and confirming.
- Manual controls: list queued jobs, cancel one job, clear a printer's queue.
- The queue survives a server restart.

## Devices

- Macs and the Pi run one Python client that reuses `src/printer.py`, under launchd or systemd.
- An ESP32 must be an S2 or S3. The original ESP32 has no USB host port. Bluetooth is not an option: it garbles images on this printer (`docs/setup-bluetooth-investigation.md`).
- Last resort for the office: extend the home Wi-Fi with a directional antenna.

## Senders

- Telegram: the bot asks Telegram for new messages (long polling), so it needs no public endpoint.
- Web form: served through the tunnel.
- WhatsApp: not planned. It needs a public webhook and a Meta business account setup.
- Public intake needs at least a size limit and a rate limit.
- Several users, each with a printer, sending to each other: possible later. A friend's printer is one more device with a token. Drop this if it starts to cost complexity.

## Rejected

- **Cloudflare only (Worker, Durable Objects, Browser Rendering or Containers).** Rendering starts per job (a Container cold start is 2-3 s), the print-quality code must be ported or containerised, and a different Chromium build and font set mean re-tuning print quality.
- **Cloudflare in front of a home renderer.** It keeps intake up while the Mac is down, but nothing prints then either. It costs a second codebase in TypeScript.
- **Devices that render.** Chromium on every device, template versions that drift apart, and no ESP32.
- **Devices on Tailscale.** Not possible on the work computer, and only third-party ports exist for ESP32 (S3 with PSRAM only).

## Known costs

- The Intel Mac is a single point of failure. When it is down, senders get an error.
- macOS 26 (Tahoe) is the last macOS release for Intel Macs.
- Dithering is a per-pixel Python loop: 0.5-0.7 s for a 384 x 2,000 image on Apple silicon. The Intel Mac is slower (not measured).

## Open

- Expiry when the writer sets none.
- The form of the manual controls: CLI, web page, or both.
- How outside senders authenticate.
- The public hostname.
