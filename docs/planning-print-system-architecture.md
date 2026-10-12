# Planning: print system architecture

Decided 2026-10-12. Built 2026-10-12.

## Goals

- Print any content on receipt printers at home and at the office.
- Robust and simple: set and forget. This is a side project with little maintenance time.
- Easy to add new ticket types.
- Automations and other people (friends, colleagues) can send prints.
- Fast prints are a direction, not a hard budget. Optimise later.

## Shape

```
web form senders
        |  HTTPS
        v
sender hostname (Cloudflare Access login)
        |
        v
Cloudflare Tunnel (no open router ports)
        |
        v
server: Intel Mac at home    <- CLI, cron and Telegram bot, on the same Mac
  intake -> queue -> render (one Chromium per job for now) -> dither -> ESC/POS bytes
        ^
        |  Cloudflare Tunnel, device hostname
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
| Public access | Cloudflare Tunnel gives the server two public hostnames: one for senders, one for devices. |
| Tailscale | Only for your own admin access. Devices do not need it: the work computer is on the work tailnet. |
| What a device receives | ESC/POS bytes. The server holds each printer's settings. |
| Who opens the connection | The device opens a WebSocket to the server and keeps it open. |
| Operating system | The server and devices run on macOS or Linux. Services: launchd on macOS, systemd on Linux. The server needs a 64-bit system, because Playwright has no 32-bit ARM build. A device also runs on 32-bit ARM. |
| Simulation | The full system runs on one machine: server plus devices with fake printers (`src/fake_printer.py`). |

## Device protocol

These rules go into device firmware, so they are expensive to change later.

- Each device has its own token. Every job is addressed to one printer id.
- The server sends a job as a series of small binary frames, about 4 KB each. The device writes each frame to USB as it arrives. An ESP32 never holds a whole job in memory.
- The device confirms a job after the last frame is written to the printer.
- The server sends `ping` every 20 s, and the device answers `pong`. The device reconnects with a growing delay when the connection drops.

## Job lifecycle

- The writer of a job sets its expiry; the default is 1 hour. A job not confirmed before its expiry is dropped.
- The server sends an unconfirmed job again when the device reconnects. It stops after 3 attempts in total and marks the job failed. A duplicate print is possible when a device dies between printing and confirming.
- Manual controls, in the CLI and in the admin web page at `/admin`: list queued jobs, cancel one job, clear a printer's queue.
- The queue survives a server restart.

## Devices

- Macs and the Pi run one Python client that reuses `src/printer.py`, under launchd or systemd. It runs with `uv run --script`, with only its own dependencies, so a Pi 2 or 32-bit Raspberry Pi OS works.
- An ESP32 must be an S2 or S3. The original ESP32 has no USB host port. Bluetooth is not an option: it garbles images on this printer (`docs/setup-bluetooth-investigation.md`).
- Last resort for the office: extend the home Wi-Fi with a directional antenna.

## Senders

- Telegram: the bot asks Telegram for new messages (long polling), so it needs no public endpoint.
- Web form: behind Cloudflare Access. A sender logs in with a one-time PIN sent by email. Allowed: a list of email addresses, and the office email domain. The server reads the sender's email from the Access token.
- Devices use the second hostname, without Access, and log in with their own tokens.
- WhatsApp: not planned. It needs a public webhook and a Meta business account setup.
- Public intake needs at least a size limit and a rate limit.
- Several users, each with a printer, sending to each other: possible later. A friend's printer is one more device with a token. Drop this if it starts to cost complexity.

## Interfaces

The contract between server, device client, CLI and web form. Change it here first.

### Modules

| Module | Role |
|---|---|
| `src/job_queue.py` | SQLite store: jobs, job events, printer state, stats queries |
| `src/render_job.py` | Job content to a 1-bit bitmap, PNG and ESC/POS bytes |
| `src/server_config.py` | Reads the server TOML config |
| `src/access_auth.py` | Verifies a Cloudflare Access token and returns the email |
| `src/device_hub.py` | Device WebSocket sessions and job delivery |
| `src/http_api.py` | HTTP routes: intake, admin API, sender web form |
| `src/print_device.py` | Device client: WebSocket loop and printer sinks (USB, fake) |
| `src/scripts/print_server.py`, `src/scripts/print_device.py`, `src/scripts/printctl.py` | Entry points |

### Server config (TOML)

```toml
[server]
host = "127.0.0.1"
port = 8787
database = "data/print-server.db"
admin_token = "..."

[access]                 # optional; without it, web senders are refused
team_domain = "<team>.cloudflareaccess.com"
audience = "<application audience tag>"
web_rate_limit = 10      # jobs per sender email per 10 minutes
admin_emails = ["you@example.com"]  # may use the admin web interface

[printers.home]
name = "Home"
place = "Home office"
token = "..."
public = true            # offered in the sender web form

[clients.morning-brief]  # a named job producer: cron, script, webhook
token = "..."
```

Tokens are plain text. The config file must have mode 0600.

### Identity

| Caller | Credential | Recorded `source` | `ingress` |
|---|---|---|---|
| Admin (CLI) | `Authorization: Bearer <admin_token>` | `admin` | `cli` |
| Admin (web) | Access token whose email is in `admin_emails` | email | `admin-web` |
| Client | `Authorization: Bearer <client token>` | client name | `api` |
| Web sender | `Cf-Access-Jwt-Assertion` header, verified against the team's public keys and the audience | email | `web` |
| Device | `Authorization: Bearer <printer token>` on the WebSocket | printer id | - |

The tunnel makes every request arrive from localhost, so the server never trusts the source address. Admin routes accept only the admin token or an Access email in `admin_emails`. A web sender may print only on `public` printers.

An Access-authenticated POST needs `Content-Type: application/json` and, when the header is present, `Sec-Fetch-Site` `same-origin` or `none`; otherwise the server answers 403.

### HTTP API (JSON)

| Method and path | Who | Does |
|---|---|---|
| `POST /api/jobs` | admin, client, web | Body: `printer`, `kind` (`receipt`, `image`, `template` or `text`), `title`, `expires_in` (seconds, default 3600), and `payload` or `image` (base64). `payload` is the receipt JSON for `receipt`, and the template envelope `{template, schemaVersion, data}` for `template` and `text`. A `text` job prints native ESC/POS text; only a template with a text mode takes it. Renders, then queues. 201 with the job. |
| `GET /api/jobs?printer=&status=&limit=` | admin | Job summaries, newest first |
| `GET /api/jobs/{id}` | admin | Job with its events |
| `GET /api/jobs/{id}/image` | admin | The rendered 1-bit PNG |
| `POST /api/jobs/{id}/cancel` | admin | Cancel |
| `POST /api/jobs/{id}/reprint` | admin | Body: optional `printer`. Queues a new job from the stored PNG, recorded with the admin as `source`. 409 when the original is still queued or sending. |
| `POST /api/printers/{id}/clear` | admin | Cancel every queued and sending job of the printer |
| `POST /api/printers/{id}/move` | admin | Body: `to`. Moves the queued jobs to another printer. |
| `GET /api/printers` | admin | Printer state (see below) |
| `GET /api/stats` | admin | Aggregates (see below) |
| `GET /api/clients` | admin | `{"clients": [{id, kind, jobs_today, last_job}]}`. Each configured client (`kind` `client`), then each web sender seen (`kind` `web`, `id` the email). `last_job` is `{id, title, kind, printer, created_at}` or null. |
| `GET /api/server` | admin | `{version, started_at, uptime_seconds, renders_in_progress}`. A render waiting for a free slot counts as in progress. |
| `GET /api/me` | web | The sender's email and the public printers |
| `GET /` | web, admin (Access email) | The sender web form |
| `GET /admin` | anyone | The admin web page. It holds no data; its API calls need admin rights. |
| `GET /admin/{name}` | anyone | The admin page's `admin.css` and `admin.js` |
| `GET /device` | device | The device WebSocket (see below) |

Errors are JSON `{"error": "<message>"}`: 400 invalid body, 401 no valid credential, 403 not allowed, 404 unknown printer or job, 409 wrong job state, 413 body over 10 MB, 422 render failed, 429 rate limit, 500 server fault (a generic message; the traceback goes only to the server log).

### Job record

`id`, `printer`, `kind`, `title`, `source`, `ingress`, `status`, `attempts`, `created_at`, `expires_at`, `render_ms`, `width` and `height` (dots), `paper_mm` (height / 8; the printer has 8 dots per mm), `size_bytes` (ESC/POS), `frames`, `sent_at`, `printed_at`.

The rendered PNG stays for 30 days, for preview, download and reprint. The ESC/POS bytes are dropped when the job reaches a final state.

Events (`job_id`, `at`, `event`, `detail`): `received`, `rendered`, `sending`, `sent`, `printed`, `released`, `failed`, `expired`, `cancelled`, `moved`, `reprinted`.

### Printer state

From the config: `id`, `name`, `place`, `public`. Kept by the server: `online`, `connected_since`, `last_seen`, `address`, `route` (`tunnel` when the request carries a `Cf-Ray` header, otherwise `direct`), `latency_ms`, `client_version`, `current_job`, `paused_until` (the epoch time when delivery resumes, 60 s after a device error or a reply timeout, or null), `queued`, `printed_today`.

### Stats

`printed_today`, `queued`, `failed_24h`, `median_job_seconds` (`created_at` to `printed_at`, last 24 h), `paper_today_mm`, and `hourly`: per printer, 24 hourly counts of printed jobs.

### Device WebSocket: `GET /device`

1. The device connects with `Authorization: Bearer <printer token>` and `X-Device-Version: <version>`. The server closes an older connection of the same printer with code 4000.
2. Server to device, one job at a time:
   - text `{"type": "job", "id": "...", "size": <bytes>, "frames": <count>}`;
   - binary frames of at most 4096 bytes;
   - text `{"type": "end", "id": "..."}`.
3. The device writes each frame to the printer as it arrives. After `end`, it replies `{"type": "printed", "id": "..."}`, or `{"type": "error", "id": "...", "message": "..."}` when the printer write fails.
4. With no reply within 120 s, the server releases the job and closes the connection.
5. Every 20 s the server sends `{"type": "ping", "t": <number>}`. The device answers `{"type": "pong", "t": <same number>}`. The server records `latency_ms` and `last_seen`.
6. On a lost connection, the device reconnects after 1 s, doubling up to 60 s, with random jitter.

Confirmation and retries are per job, not per frame. A printer cannot resume an image in the middle.

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

- The public hostnames. `print.<zone>` is the working name for senders.
