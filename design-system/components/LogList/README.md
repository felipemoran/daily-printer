# LogList

A timeline of `time — event` rows: bold fixed-width times, body text. For incident timelines, agenda summaries and build logs.

- Provide: `rows` as `[time, text]` pairs; `timeWidth` (default 76px) when times are longer (`TUE 14h` wants 120px).
- One line per event. Newest last.
