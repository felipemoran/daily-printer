# Feature: print system

A print server takes jobs over HTTP, renders each one to a 1-bit image, and sends it to a printer device over a WebSocket. Each device prints on its USB receipt printer, or saves a PNG when it runs with a fake printer. Design and HTTP contract: `docs/planning-print-system-architecture.md`. Deployment: `docs/setup-deploy.md`.

## Run it locally

Receipt, template and text jobs render in Chromium from the built web app. On a fresh clone, run `make setup` and `make web-build` first.

| Command | Does |
|---|---|
| `make demo` | Builds `web/dist` when it is missing, then runs `make simulate`. |
| `make simulate` | Starts the server and two fake printers (`home`, `work`), prints one job per sample, then keeps running until Ctrl-C. |
| `make demo-<name>` | Sends one sample to the running demo, on `home`. `make help` lists the names. |
| `make server CONFIG=<file>` | Starts the server with your config. Format: `samples/print-server.example.toml`. The file must have mode 0600. |
| `make device-fake TOKEN_FILE=<file> [SERVER=<url>] [OUT=<dir>]` | Starts one device with a fake printer. `SERVER` defaults to `ws://127.0.0.1:8787/device`, `OUT` to `data/fake-printer`. |

### Samples

The simulation sends these jobs, in turn to `home` and `work`. Each `make demo-<name>` target sends the same file:

| Name | Kind | File |
|---|---|---|
| one per template, e.g. `ticket` | `template` | `samples/templates/<name>.json` |
| `text` | `text` | `samples/templates/build.json` |
| `image` | `image` | `samples/test-pattern.png` |
| `receipt` | `receipt` | `samples/receipt-sample.json` |

A new `.json` file in `samples/templates/` becomes a sample and a make target with no code change.

### Output

`make simulate` writes its config, printer tokens and logs to a new temporary folder, `print-sim-<random>`. It prints:

1. a line for each start step;
2. one line for each job when the server accepts it;
3. one line for each printed job: printer, kind, name, status, size in dots, paper length in cm, and the output file;
4. the admin page URL, the admin token, the folder, the `make demo-<name>` command, and ready `printctl` commands. `printctl` is the admin CLI, `uv run src/scripts/printctl.py`.

A fake printer saves each job as `<dir>/<job id>.png`, with the raw ESC/POS (the printer's command language) bytes in `<job id>.bin`. A text job has no image, so it has only the `.bin`. In the simulation, `<dir>` is `<temporary folder>/<printer id>`.

`uv run src/scripts/simulate.py --once` stops after every job prints. `--port PORT` uses another port. With `--port PORT`, pass the server to the make targets: `make demo-ticket DEMO_SERVER=http://127.0.0.1:PORT`.

### Admin token

The simulation always uses the admin token `moranlindo`, the `ADMIN_TOKEN` constant in `src/scripts/simulate.py`. Open `http://127.0.0.1:8787/admin` and enter it. The Makefile holds a copy for the `demo-<name>` targets, and `tests/test_make_demo.py` checks that the two agree.

The server accepts a token of any length, so a short token also works on the real server. It refuses an empty token and a token that two entries share. The token never appears in the front-end files in `src/static/`: only the server checks it.

## Send a job

### printctl

`printctl` uses the admin token. It reads the token from `--token-file PATH`, or from `$PRINT_ADMIN_TOKEN`. The server is `--server URL`, `$PRINT_SERVER_URL`, or `http://127.0.0.1:8787`. Put both options before the command.

```sh
export PRINT_ADMIN_TOKEN=...
uv run src/scripts/printctl.py send receipt samples/receipt-sample.json --printer home --expires 2h
uv run src/scripts/printctl.py send template samples/templates/ticket.json --printer home
uv run src/scripts/printctl.py send image photo.jpg --printer home --title "Holiday"
```

`--expires` takes a number with `m`, `h` or `d`, e.g. `30m`, up to 7 days.

### HTTP API

A script or a cron job uses a client token from a `[clients.<id>]` table in the server config. The server records the client id as the job's source.

```sh
jq '{printer: "home", kind: "template", title: "Ticket", payload: .}' samples/templates/ticket.json |
  curl -X POST http://127.0.0.1:8787/api/jobs \
    -H "Authorization: Bearer $CLIENT_TOKEN" \
    -H "Content-Type: application/json" \
    -d @-
```

The reply is 201 with the job record. Every field, route and error code: "HTTP API (JSON)" in `docs/planning-print-system-architecture.md`.

### Web form

The page at `/` lets a person send a message (printed as a receipt) or a photo. It works only behind Cloudflare Access: without an `[access]` table in the config, the server refuses every web sender, also on your own machine. A web sender sees and prints only on printers with `public = true`.

## Job kinds

| `kind` | Content | Body field |
|---|---|---|
| `receipt` | Receipt JSON, as in `samples/receipt-sample.json` | `payload` |
| `image` | A photo or picture, dithered to 384 dots wide | `image`, the file as base64 |
| `template` | `{template, schemaVersion, data}`; templates and their rules: `docs/feature-ticket-templates.md` | `payload` |
| `text` | The `template` envelope, printed as native ESC/POS text; only a template with a text mode (`build`) | `payload` |

## Watch and control

| Command | Does |
|---|---|
| `printctl jobs [--printer P] [--status S] [--limit N]` | Lists jobs, newest first. Default limit: 20. |
| `printctl show <id>` | Shows a job, the path of its artifact folder on the server, and its event timeline. |
| `printctl image <id> -o <file>` | Saves the job's `print.png`. |
| `printctl cancel <id>` | Cancels a queued or sending job. A sending job can still print; it then shows as printed. |
| `printctl clear <printer>` | Cancels every queued and sending job of a printer. |
| `printctl reprint <id> [--printer P]` | Queues a finished job again, on the same or another printer. It sends the same bytes as the first print. |
| `printctl move <from> <to>` | Moves the queued jobs of one printer to another. |
| `printctl printers` | Shows each printer's connection and queue. |
| `printctl stats` | Shows print counts, paper use and hourly activity. |

The admin page at `<server URL>/admin`, e.g. `http://127.0.0.1:8787/admin`, shows the same data in a browser, on desktop or phone. It has three views: the job rail (queue first, then the recent jobs), the job detail, and Connections (the printers, then the clients). From it you can cancel, reprint, clear a printer and move its queue.

- Behind Cloudflare Access, an email in `admin_emails` opens it with no token.
- Locally, the page asks for the admin token. It keeps the token only for that browser tab.

## Job artifacts

The server keeps every job as it was created, in `<directory of the database>/artifacts/<job id>/`. A later template, font or code change does not alter a past job. `printctl show <id>` prints the folder path. Write order, retention and failure handling: "Job storage" in `docs/planning-print-system-architecture.md`.

| File | What it is | Kinds |
|---|---|---|
| `request.json` | The HTTP request body, byte for byte as received: `printer`, `kind`, `title`, `expires_in` and `payload` | receipt, template, text |
| `source.<ext>` | The uploaded file, byte for byte; `<ext>` from its format, e.g. `jpg` | image |
| `page.mhtml` | The rendered page with its style sheets, images and web fonts, as Chromium's MHTML. For `text`, the preview page. Chrome opens it offline. | receipt, template, text |
| `screenshot.png` | Chromium's capture of `#receipt`, before rotation and the 1-bit conversion. A landscape template's capture runs along the paper. | receipt, template, text |
| `print.png` | The 1-bit bitmap. For `text`, the preview. | all |
| `job.escpos` | The exact bytes sent to the printer | all |
| `meta.json` | `kind`, `template`, `created_at`, `width`, `height`, `render_ms`, `web_dist_sha256` (a digest of every file in `web/dist`), and `reprint_of` for a reprint | all |

Chromium's MHTML writer leaves web fonts out. Before the snapshot, the server adds a copy of each fetched `@font-face` rule with the font file as a `data:` URL, so the fonts travel in a style sheet part. The receipt app draws in system fonts (Tahoma, Verdana), which no archive carries: its `page.mhtml` shows in the fonts of the machine that opens it.

Disk use per job, measured 2026-10-12 on the samples in `samples/templates/` and `samples/receipt-sample.json`:

| Job | Disk |
|---|---|
| `template`, one of the 14 samples | 210-280 KB; `page.mhtml` is 150-195 KB of it, mostly the fonts |
| `text` (`build`) | 180 KB |
| `receipt` (the sample) | 110 KB |
| `image` | the upload, plus `print.png` and `job.escpos` |
| reprint | the same as the original: the reprint holds its own copy of every file |

## Run a real device

```sh
uv run --script src/scripts/print_device.py --server wss://<device hostname>/device --token-file ~/print-device/token
```

The metadata block at the top of the script lists the device's dependencies. uv installs only those, at the versions in `src/scripts/print_device.py.lock`, and not the project's. `--script` makes uv read the file as a script. A device never renders, so it needs no Playwright. It should run on 32-bit Raspberry Pi OS, but no Pi has run it yet: see Limits in `docs/setup-deploy.md`. `tests/test_device_dependencies.py` fails when the device imports a package that the block does not list, or when the lock no longer matches the block.

A device service installed before the block existed runs `uv run` without `--script`. After a `git pull`, it still moves to the script environment at its next restart, because uv reads the block of any script it runs. That one start installs the packages, so it needs the network.

| Flag | Effect |
|---|---|
| `--server URL` | The server's device endpoint. Must start with `ws://` or `wss://`. Required. |
| `--token-file PATH` | The file with this printer's token. Without it, the token comes from `$PRINT_DEVICE_TOKEN`. There is no `--token` flag, so the token never shows in `ps`. |
| `--fake DIR` | Save each job as `DIR/<job id>.bin`, plus `DIR/<job id>.png` for a raster job, and do not print. |

Without `--fake`, the device prints on the USB receipt printer. It opens the printer only during a job. When the device cannot open the printer, or a USB write takes no data for 10 s, it reports an error for that job. The usual causes of a write timeout are no paper or an open cover. The device reconnects by itself when the connection drops.

To install the server and the devices as services, follow `docs/setup-deploy.md`.

## Limits

- The maximum expiry is 7 days.
- After a device error, or no reply within 120 s, the server sends nothing to that printer for 60 s. `printctl printers` shows the printer as paused until a given time.
- A job prints at most 50 cm long (4000 dots). The server refuses a longer render with 422. A `template` job with `accept_long: true` may print up to 1 m (8000 dots).
- `printctl` refuses an image file over about 7.5 MB, because base64 makes the request body larger than the file.
- A source image has at most 25 million pixels.
- A web sender may send `web_rate_limit` jobs per 10 minutes (from the `[access]` table; the example config sets 10). One more gets 429.
- A template payload has its own limits: `docs/feature-ticket-templates.md`.

The default expiry, the number of attempts, duplicate prints and the body size limit: "Job lifecycle" and the errors line under "HTTP API (JSON)" in `docs/planning-print-system-architecture.md`.
