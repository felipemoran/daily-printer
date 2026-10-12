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

You need: Node.js (`npm`) for the receipt renderer, and a Cloudflare account with a domain (zone).

On each printer machine, with the printer plugged in over USB:

```sh
git clone https://github.com/felipemoran/daily-printer.git ~/daily-printer
~/daily-printer/deploy/wizard.sh device
```

A Raspberry Pi needs the 64-bit Raspberry Pi OS: Playwright has no 32-bit ARM build, so the wizard stops on an ARM machine whose `getconf LONG_BIT` is 32. It asks for the device hostname and the printer's token. On macOS it also asks for your password (sudo), to set up log rotation. To see a token again, run `deploy/wizard.sh tokens` on the server. A printer plugged into the server needs the device wizard too.

## Files

| Path | What |
|---|---|
| `~/print-server/config.toml` | server config, mode 0600; the wizard rewrites it and drops comments |
| `~/print-server/admin-token` | admin token for `printctl --token-file`, mode 0600 |
| `~/print-server/data/print-server.db` | job queue |
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

## Limits

- On macOS, newsyslog rotates each log at 10 MB and keeps 5 files. A running service keeps writing to the rotated file (`server.log.0`) until it restarts, because launchd opens the log only when it starts the service.
- The wizard refuses a 32-bit ARM userland, also on a 64-bit kernel: Playwright has no build for it.
- The macOS device service runs only while its user is logged in.
- The wizard refuses a repo path or home folder with spaces: the service files cannot quote them.
- An Access application whose wildcard hostname also covers the device hostname stops every device. Protect the sender hostname only.
- Keep Rocket Loader and automatic Web Analytics injection off for the sender hostname. The web form's CSP allows only its own script hash, so both would be blocked, and Rocket Loader would stop the page script. Rocket Loader: Speed > Settings > Content Optimization, or a [configuration rule](https://developers.cloudflare.com/rules/configuration-rules/) for that hostname. Web Analytics: Manage site > Disable.
- On Apple silicon, Homebrew puts libusb in `/opt/homebrew/lib`. Python's library search on macOS skips that folder, so the device plist sets `DYLD_FALLBACK_LIBRARY_PATH`.

## Sources

Checked on 2026-10-12.

- Cloudflare Tunnel, local management: [create a tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/create-local-tunnel/) (`login`, `create`, `route dns`), [configuration file](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/configuration-file/) (`tunnel`, `credentials-file`, `ingress`, `hostname`, `path` as a regular expression, the catch-all last rule, `tunnel ingress validate`), [terms](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/local-tunnel-terms/) (`cert.pem`, default directories), [useful commands](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/tunnel-useful-commands/), [downloads](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/).
- `cloudflared` as a service: [macOS](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/as-a-service/macos/) (`sudo cloudflared service install` reads `/etc/cloudflared`, label `com.cloudflare.cloudflared`), [Linux](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/as-a-service/linux/) (pass `--config` because `sudo` sets `$HOME` to `/root`), [Windows](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/as-a-service/windows/) (`--config` before the subcommand).
- Cloudflare Access: [self-hosted application](https://developers.cloudflare.com/cloudflare-one/applications/configure-apps/self-hosted-public-app/), [one-time PIN](https://developers.cloudflare.com/cloudflare-one/identity/one-time-pin/), [policies](https://developers.cloudflare.com/cloudflare-one/policies/access/) (Emails, Emails ending in, Include is OR), [validate the JWT](https://developers.cloudflare.com/cloudflare-one/identity/authorization-cookie/validating-json/) (AUD tag location, `Cf-Access-Jwt-Assertion`), [team domain](https://developers.cloudflare.com/cloudflare-one/faq/getting-started-faq/).
- launchd: `man 5 launchd.plist` (`Label`, `UserName` for the system domain only, `ProgramArguments`, `WorkingDirectory`, `EnvironmentVariables`, `RunAtLoad`, `KeepAlive`, `StandardOutPath`, `StandardErrorPath`), `man launchctl` (`bootstrap`, `bootout`, `kickstart -k`, `system/` and `gui/<uid>/` targets), and [Creating Launch Daemons and Agents](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html) (folders, owner, mode 600).
- systemd, from the [man page sources](https://github.com/systemd/systemd/tree/main/man): `systemd.service` (`Restart=`, `RestartSec=`, `ExecStart=` needs an absolute path outside the standard folders), `systemd.exec` (`User=` sets `$HOME`; the default `$PATH`), `systemd.special` (`network-online.target` for units that need the network, `WantedBy=multi-user.target`), `systemd.time` (`--since @<epoch seconds>`), `udev` (`ATTR{}`, `OWNER`) and `udevadm` (`control --reload`, `trigger`).
- Cloudflare zone settings: [Rocket Loader](https://developers.cloudflare.com/speed/optimization/content/rocket-loader/enable/) (on specific hostnames through a configuration rule), [Web Analytics](https://developers.cloudflare.com/web-analytics/get-started/) (automatic setup is on by default for proxied sites; Manage site > Disable).
- uv: [installation](https://docs.astral.sh/uv/getting-started/installation/).
