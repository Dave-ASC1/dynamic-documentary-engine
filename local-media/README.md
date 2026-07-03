# Local Media Workspace

Use this folder for real video and audio files that live on this computer.

- `raw/` — original downloads or recordings before cleanup.
- `assets/` — engine-ready files referenced by metadata, separated by roll type.
- `films/` — rendered test films generated from local media.

The files in these folders are ignored by Git so large media does not get pushed
to GitHub. Keep filenames in `assets/` matched to the collection metadata, or
update the metadata to match the files you place here.

Example:

```text
assets/a-roll/val_av_003.mp4
assets/b-roll/val_bv_001.mp4
assets/x-roll/val_xa_001.wav
```

When using subfolders, include the subfolder in the metadata filename:

```json
"filename": "a-roll/val_av_003.mp4"
```

To run the command-line validation with this folder:

```bash
python3 scripts/run_first_film.py --assets-path local-media/assets --films-path local-media/films
```
