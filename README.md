
## Files
- `pyproject.toml` - Python package metadata and dependencies
- `src/mp3_player_waveterm/__init__.py` - package version
- `src/mp3_player_waveterm/__main__.py` - module entrypoint
- `src/mp3_player_waveterm/library.py` - MP3 discovery and metadata extraction
- `src/mp3_player_waveterm/player.py` - VLC-backed playback with a safe fallback
- `src/mp3_player_waveterm/app.py` - Textual terminal UI

## Intent
- compact file-based MP3 browser/player for WaveTerm
- sticky now-playing header
- short metadata display in the form `band · album · song`
- Windows-first playback, but Linux-friendly
- configurable root via `--root`, `MP3_ROOT`, or OS defaults

## Defaults
- Windows: `K:\media vault\music`
- Linux: `~/Music`

## Controls
- Enter: play selected
- Space: pause/resume
- n / p: next / previous
- s: stop
- r: rescan
- q: quit

## Run
From this folder:

```bash
python -m pip install -e .
python -m mp3_player_waveterm --root "/path/to/music"
```

Helpful commands:

```bash
waveterm-mp3-doctor
python -m mp3_player_waveterm --full-scan --root "K:\media vault\music"
```

In-app playback uses VLC via `python-vlc`.
Install the Python binding with:

```bash
python -m pip install python-vlc
```

You also need the VLC application installed on Windows so the Python binding can load `libvlc`.

## Performance notes
- Default startup uses a fast scan: file names only, no tag reads.
- Use `--full-scan` when you want richer metadata and don't mind the slower first load.
- The playlist is the file tree, not M3U files.
- Metadata falls back cleanly when tags are missing.
- If VLC is unavailable, the app still boots and shows a safe no-op player.
- Keep the layout narrow; WaveTerm panels are often tight.
