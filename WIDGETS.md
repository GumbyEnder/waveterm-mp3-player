
This repo includes a WaveTerm-friendly MP3 player that can be launched as a widget.

## Recommended widget options

### 1) Windows widget
Use this on the Windows machine that has WaveTerm and your NAS music folder mounted.

```json
"waveterm-mp3": {
  "display:order": 10,
  "icon": "music",
  "label": "mp3",
  "color": "#8b5cf6",
  "description": "WaveTerm MP3 player",
  "blockdef": {
    "meta": {
      "view": "term",
      "controller": "cmd",
      "cmd": "python -m mp3_player_waveterm --root \"K:\\media vault\\music\"",
      "cmd:shell": true,
      "cmd:cwd": "K:\\agents\\hermes\\mp3",
      "cmd:runonstart": true,
      "cmd:clearonstart": true,
      "cmd:closeonexit": false,
      "cmd:nowsh": false
    }
  }
}
```

### 2) macOS / Linux widget
Use this if your music lives under `~/Music` and you want the repo to run with `python3`.

```json
"waveterm-mp3": {
  "display:order": 10,
  "icon": "music",
  "label": "mp3",
  "color": "#8b5cf6",
  "description": "WaveTerm MP3 player",
  "blockdef": {
    "meta": {
      "view": "term",
      "controller": "cmd",
      "cmd": "python3 -m mp3_player_waveterm --root \"$HOME/Music\"",
      "cmd:shell": true,
      "cmd:runonstart": true,
      "cmd:clearonstart": true,
      "cmd:closeonexit": false,
      "cmd:nowsh": false
    }
  }
}
```

### 3) Visuals-on-start widget
This starts the player with the simple built-in terminal visualizer enabled.

```json
"waveterm-mp3-visuals": {
  "display:order": 11,
  "icon": "music",
  "label": "mp3+v",
  "color": "#22c55e",
  "description": "WaveTerm MP3 player with visuals",
  "blockdef": {
    "meta": {
      "view": "term",
      "controller": "cmd",
      "cmd": "python -m mp3_player_waveterm --visuals --root \"K:\\media vault\\music\"",
      "cmd:shell": true,
      "cmd:cwd": "K:\\agents\\hermes\\mp3",
      "cmd:runonstart": true,
      "cmd:clearonstart": true,
      "cmd:closeonexit": false,
      "cmd:nowsh": false
    }
  }
}
```

## How to use these snippets

1. Open your WaveTerm `widgets.json`.
2. Keep your existing widget entries intact.
3. Paste one of the snippets above as a new top-level entry inside the same JSON object.
4. Save the file.
5. Restart WaveTerm or reload widgets.

## Notes

- The Windows snippet assumes the repo is at `K:\agents\hermes\mp3`.
- If your repo lives somewhere else, change `cmd:cwd`.
- If your music library lives somewhere else, change the `--root` path.
- If VLC shows up as `null`, run `waveterm-mp3-doctor` in the same shell to see why.
- The visualizer is intentionally lightweight. It is a terminal-friendly animation, not full audio spectrum analysis.

## Example customization ideas

If you want to go further, the widget could eventually be expanded into:
- a plain player widget
- a visuals-only widget
- a battery/clock/status strip
- a bigger “mission control” widget for music and system info together
