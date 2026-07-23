# Local Media Workspace

Each **film topic** (World War II, Swiss, ...) gets its own self-contained
folder here — pick any name, the engine auto-discovers it:

```text
local-media/
  <Topic Name>/
    assets/
      a-roll/
      b-roll/
      x-roll/
    artifacts/        <- rendered films land here
```

Drop real video/audio files into the right `assets/<roll-type>/` subfolder —
the engine auto-detects them on the next generate (auto-inferred title,
duration, dominant color, pacing). Deleting a file retires its entry the
same way. No manual JSON editing, no restart needed.

A brand-new topic folder just needs the `assets/` and `artifacts/`
subfolders to exist (even empty) — the engine creates a matching
metadata index automatically at
`metadata/collections/<topic>_collection_index.json` the first time it's
seen.

The files in these folders are ignored by Git so large media does not get
pushed to GitHub.

To run the command-line validation against a topic's footage:

```bash
python3 scripts/run_first_film.py --assets-path "local-media/Validation/assets" --films-path "local-media/Validation/artifacts"
```
