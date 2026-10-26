# Setup: deploy the print server and the printer devices

`deploy/wizard.sh` installs everything. It walks you through each step, checks it where a check is possible, and is safe to re-run: it keeps the tokens and the answers you gave.

## What runs where

| Machine | Runs | Service |
|---|---|---|
| Server (the Intel Mac at home, macOS or Linux) | print server, `cloudflared` | macOS: LaunchDaemons, start at boot. Linux: systemd units. |
| Each printer machine (Mac or Raspberry Pi) | device client | macOS: LaunchAgent, runs while you are logged in, no admin rights. Linux: systemd unit. |

Two public hostnames go through one Cloudflare Tunnel to the server's local port (`127.0.0.1:8787`):

| Hostname | Who | Protection | Paths |
|---|---|---|---|
| sender, e.g. `print.example.com` | web form senders | Cloudflare Access, one-time PIN by email | all |
| device, e.g. `print-device.example.com` | devices | the printer token | `/device` only; every other path is 404 |

Devices reach the server through the device hostname. They need no Tailscale and no VPN.

## Run it

On the server:

```sh
git clone https://github.com/felipemoran/daily-printer.git ~/daily-printer
~/daily-printer/deploy/wizard.sh server
```

It installs uv, builds the receipt renderer, writes the config, installs the server service, creates the tunnel and its DNS records, installs `cloudflared` as a service, and walks you through the Access application in the Cloudflare dashboard. At the end it can show each printer's token. It asks for your password (sudo) to install the services.

You need: Node.js (`npm`) for the receipt renderer, and a Cloudflare account with a domain (zone). The server needs a 64-bit system: Playwright has no 32-bit ARM build, so `wizard.sh server` stops on an ARM machine whose `getconf LONG_BIT` is 32.

On each printer machine, with the printer plugged in over USB:

```sh
git clone https://github.com/felipemoran/daily-printer.git ~/daily-printer
~/daily-printer/deploy/wizard.sh device
```

A device should run on a Raspberry Pi 2 or later, with 32-bit or 64-bit Raspberry Pi OS. No Pi has run it yet (see Limits). It installs only the device's own Python dependencies, from the inline metadata in `src/scripts/print_device.py` at the versions in `src/scripts/print_device.py.lock` (`uv sync --script`), and the service starts it with `uv run --script`. Playwright and the other server dependencies stay off the device. On 32-bit ARM, PyPI has no wheel for Pillow, so the wizard installs `build-essential python3-dev libjpeg-dev zlib1g-dev` and uv builds Pillow from source. The wizard asks for the device hostname and the printer's token. On macOS it also asks for your password (sudo), to set up log rotation. To see a token again, run `deploy/wizard.sh tokens` on the server. A printer plugged into the server needs the device wizard too.

## Files

| Path | What |
|---|---|
| `~/print-server/config.toml` | server config, mode 0600; the wizard rewrites it and drops comments |
| `~/print-server/admin-token` | admin token for `printctl --token-file`, mode 0600 |
| `~/print-server/data/print-server.db` | job queue, with its `-wal` and `-shm` files beside it |
| `~/print-server/wizard.env`, `~/print-device/wizard.env` | your wizard answers (hostnames, tunnel); no tokens |
| `~/print-device/token` | printer token, mode 0600 |
| `/etc/cloudflared/config.yml` | tunnel config, from `deploy/cloudflared/config.example.yml` |
| `/Library/LaunchDaemons/com.daily-printer.server.plist` | macOS server service, from `deploy/launchd/` |
| `~/Library/LaunchAgents/com.daily-printer.device.plist` | macOS device service, from `deploy/launchd/` |
| `/etc/newsyslog.d/daily-printer.conf` | macOS log rotation: one line per service log |
| `/etc/systemd/system/print-server.service`, `print-device.service` | Linux services, from `deploy/systemd/` |
| `/etc/udev/rules.d/60-daily-printer.rules` | Linux: lets the device user open the USB printer |

Placeholders: `render` in `deploy/wizard.sh`.

## Operate

| Task | macOS | Linux |
|---|---|---|
| Server log | `~/print-server/logs/server.log` | `journalctl -u print-server` |
| Device log | `~/print-device/logs/device.log` | `journalctl -u print-device` |
| Restart the server | `sudo launchctl kickstart -k system/com.daily-printer.server` | `sudo systemctl restart print-server` |
| Restart the device | `launchctl kickstart -k gui/$(id -u)/com.daily-printer.device` | `sudo systemctl restart print-device` |
| Restart the tunnel | `sudo launchctl kickstart -k system/com.cloudflare.cloudflared` | `sudo systemctl restart cloudflared` |
| Stop the server for good | `sudo launchctl bootout system/com.daily-printer.server` | `sudo systemctl disable --now print-server` |

After a `git pull` on the server, restart the server. When `web/` changed, run `cd web && npm run build` first.

## Docker Compose

The print server can also run in Docker, in place of the server service above. `compose.yaml` and `Dockerfile` are at the repo root. You need Docker with Compose v2 (Docker Desktop on a Mac).

### What runs where

| Service | Profile | Runs |
|---|---|---|
| `server` | none, always | the print server with Chromium inside; restarts with Docker |
| `cloudflared` | `tunnel` | the Cloudflare Tunnel, remotely managed; it reaches `http://server:8787` |
| `printer-home`, `printer-work` | `test` | fake printers for `make compose-test`; never on a real deploy |
| `check` | `check` | the `make compose-test` checker; runs once |

Real printers stay outside Docker: Docker Desktop on macOS cannot pass a USB device into a container. Run the device client on the host with `deploy/wizard.sh device`, as above.

All services except `cloudflared` use one image, `daily-printer:local`. Its containers run as user `printer` (uid 10001), not root.

### Ports and volumes

- The server listens on port 8787 in its container. Compose publishes it on the host as `127.0.0.1:8787` only, never on other interfaces. `PRINT_SERVER_PORT` changes the host port.
- The named volume `daily-printer_data` holds the job database (`print-server.db`, with its `-wal` and `-shm` files) and the `artifacts/` folder. It is a named volume, not a bind mount: SQLite locking and the `-wal` file stay on the Docker VM's own disk, and the image makes the `printer` user its owner.

### Config and secrets

1. Write a server config from `samples/print-server.example.toml`, outside the repo, mode 0600. Two values must differ from the example, `host` and `database`; `port` stays 8787:
   ```toml
   [server]
   host = "0.0.0.0"                    # 127.0.0.1 is unreachable from outside the container
   port = 8787
   database = "/data/print-server.db"  # on the data volume; the config folder is read-only
   ```
2. Point Compose at it in `.env` at the repo root. Every `docker compose` command and every `make compose-*` target reads that file. Compose mounts the config read-only at `/config/server.toml`.
   ```sh
   PRINT_SERVER_CONFIG=/Users/<you>/print-server/config.toml   # required
   PRINT_SERVER_PORT=8787                                      # optional: the host port
   TUNNEL_TOKEN=<the tunnel token>                             # only for the tunnel profile
   ```
   `.env` is gitignored. It holds the tunnel token, so keep it mode 0600. `daily_print.py` reads the same file for its own keys.
3. `make compose-up` builds the image and starts the server. It waits until the healthcheck passes. The healthcheck requests `/admin`, which needs no token, at the container's own hostname: a config that listens on loopback only fails it.

| Task | Command |
|---|---|
| Start or upgrade the server | `make compose-up` |
| Start the tunnel too | `docker compose --profile tunnel up -d` |
| Server log | `docker compose logs -f server` |
| Stop the server and the tunnel | `make compose-down`; the data volume stays |

### The tunnel: two ways

- **In Compose, remotely managed.** Create a tunnel in the Zero Trust dashboard (Networks > Tunnels > Create a tunnel > Cloudflared). Put its token in `.env` as `TUNNEL_TOKEN`. In the tunnel's public hostnames, add the device hostname with path `^/device$`, then the sender hostname with no path, both to `http://server:8787`. These are the rules of `deploy/cloudflared/config.example.yml`. Then check that the device hostname answers 404 on every path but `/device`.
- **On the host, locally managed.** `wizard.sh server` installs `cloudflared` as a host service with `deploy/cloudflared/config.example.yml`. It reaches `http://127.0.0.1:8787`, the server's published port, so it works with the Compose server unchanged. Do not also run the wizard's server service: only one server can own port 8787.

### A host device client

On the server Mac itself, a device client connects to the published port: `--server ws://127.0.0.1:8787/device`. Every other printer machine connects through the tunnel's device hostname, `wss://<device host>/device`, as without Docker. The published port is not reachable from the LAN.

### Backups

The data volume holds the whole job history. Stop the server for a consistent copy, because SQLite keeps recent writes in the `-wal` file:

```sh
docker compose stop server
docker compose cp server:/data ./print-server-backup-$(date +%F)
docker compose start server
```

Restoring a backup into the volume is untested.

### Upgrades

Pull the new code, then run `make compose-up`. It rebuilds the image and recreates the server container. The server migrates the database schema when it starts. An older server refuses a database that a newer one migrated, so take a backup before you upgrade.

### Test it

`make compose-test` builds the image and starts the server with `deploy/compose-test/server.toml`, a test-only config whose tokens are public. It starts the two fake printers and sends the 14 template samples plus a text, an image and a receipt job. Then it checks that each job printed, and that each fake printer's `.bin` file equals the job's `job.escpos` artifact. At the end it removes its containers, network, volumes and image, also on failure. It uses its own Compose project, `daily-printer-test`, its own image tag, `daily-printer:test`, and host port 18787 (`COMPOSE_TEST_PORT`). So it never touches the real server, its image or its data.

### Untested

- The `cloudflared` service and the dashboard rules: they need a real tunnel token.
- The image on amd64 (the Intel Mac): it builds with `docker buildx build --platform linux/amd64 .`, but no amd64 machine ran it.
- Docker on the Intel Mac itself.

## Limits

- On macOS, newsyslog rotates each log at 10 MB and keeps 5 files. A running service keeps writing to the rotated file (`server.log.0`) until it restarts, because launchd opens the log only when it starts the service.
- `wizard.sh server` refuses a 32-bit ARM userland, also on a 64-bit kernel: Playwright has no build for it. `wizard.sh device` runs there.
- ARMv6 boards (Pi 1, Pi Zero, Pi Zero W) are not supported. The repo's `.python-version` makes uv use Python 3.12 for the device too, Raspberry Pi OS ships 3.11 or 3.13, and python-build-standalone publishes no ARMv6 build.
- No Pi has run a device yet. The 32-bit ARM support comes from the published uv and Python builds and the PyPI wheels, listed under Sources.
- The macOS device service runs only while its user is logged in.
- The wizard refuses a repo path or home folder with spaces: the service files cannot quote them.
- An Access application whose wildcard hostname also covers the device hostname stops every device. Protect the sender hostname only.
- Keep Rocket Loader and automatic Web Analytics injection off for the sender hostname. The web form's CSP allows only its own script hash, so both would be blocked, and Rocket Loader would stop the page script. Rocket Loader: Speed > Settings > Content Optimization, or a [configuration rule](https://developers.cloudflare.com/rules/configuration-rules/) for that hostname. Web Analytics: Manage site > Disable.
- On Apple silicon, Homebrew puts libusb in `/opt/homebrew/lib`. Python's library search on macOS skips that folder, so the device plist sets `DYLD_FALLBACK_LIBRARY_PATH`.

## Sources

Checked on 2026-10-12.

- 32-bit ARM devices: uv's [platform support](https://docs.astral.sh/uv/reference/policies/platforms/) (Linux armv7 is Tier 2, with official `armv7-unknown-linux-gnueabihf` binaries), python-build-standalone's [running guide](https://gregoryszorc.com/docs/python-build-standalone/main/running.html) (`armv7-unknown-linux-gnueabihf`: Raspberry Pi 2 and later) and its [releases](https://github.com/astral-sh/python-build-standalone/releases) (CPython 3.12 to 3.14 for armv7). PyPI publishes `manylinux` armv7l wheels for aiohttp, multidict, yarl and frozenlist, and pure-Python wheels for the other device packages, except Pillow and PyYAML: they publish no armv7l wheel. PyYAML then builds from source, and its `setup.py` falls back to pure Python when the libyaml extension does not compile.
- Cloudflare Tunnel, local management: [create a tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/create-local-tunnel/) (`login`, `create`, `route dns`), [configuration file](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/configuration-file/) (`tunnel`, `credentials-file`, `ingress`, `hostname`, `path` as a regular expression, the catch-all last rule, `tunnel ingress validate`), [terms](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/local-tunnel-terms/) (`cert.pem`, default directories), [useful commands](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/tunnel-useful-commands/), [downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
- `cloudflared` as a service: [macOS](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/as-a-service/macos/) (`sudo cloudflared service install` reads `/etc/cloudflared`, label `com.cloudflare.cloudflared`), [Linux](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/as-a-service/linux/) (pass `--config` because `sudo` sets `$HOME` to `/root`), [Windows](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/as-a-service/windows/) (`--config` before the subcommand).
- Cloudflare Access: [self-hosted application](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-public-app/), [one-time PIN](https://developers.cloudflare.com/cloudflare-one/identity/one-time-pin/), [policies](https://developers.cloudflare.com/cloudflare-one/policies/access/) (Emails, Emails ending in, Include is OR), [validate the JWT](https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/) (AUD tag location, `Cf-Access-Jwt-Assertion`), [team domain](https://developers.cloudflare.com/cloudflare-one/faq/getting-started-faq/).
- launchd: `man 5 launchd.plist` (`Label`, `UserName` for the system domain only, `ProgramArguments`, `WorkingDirectory`, `EnvironmentVariables`, `RunAtLoad`, `KeepAlive`, `StandardOutPath`, `StandardErrorPath`), `man launchctl` (`bootstrap`, `bootout`, `kickstart -k`, `system/` and `gui/<uid>/` targets), and [Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html) (folders, owner, mode 600).
- systemd, from the [man page sources](https://github.com/systemd/systemd/tree/main/man): `systemd.service` (`Restart=`, `RestartSec=`, `ExecStart=` needs an absolute path outside the standard folders), `systemd.exec` (`User=` sets `$HOME`; the default `$PATH`), `systemd.special` (`network-online.target` for units that need the network, `WantedBy=multi-user.target`), `systemd.time` (`--since @<epoch seconds>`), `udev` (`ATTR{}`, `OWNER`) and `udevadm` (`control --reload`, `trigger`).
- Cloudflare zone settings: [Rocket Loader](https://developers.cloudflare.com/speed/optimization/content/rocket-loader/enable/) (on specific hostnames through a configuration rule), [Web Analytics](https://developers.cloudflare.com/web-analytics/get-started/) (automatic setup is on by default for proxied sites; Manage site > Disable).
- uv: [installation](https://docs.astral.sh/uv/getting-started/installation/).
