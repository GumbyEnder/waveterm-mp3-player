
This file is the short working plan for the repo.

## Done already

- Basic WaveTerm MP3 player scaffold
- Fast library scan by default
- `--full-scan` metadata mode
- `--visuals` basic terminal visualizer
- VLC probing / backend detection
- Windows-safe, Mac/Linux, and visuals-on-start widget snippets
- `WIDGETS.md` and `widgets.example.json`
- Auto-advance to the next track when a song ends
- Human-readable README

## Next pass: visual polish

Goal: make the player feel more alive without making startup heavy.

Best first modes:

- pulse: a small breathing bar while playing
- bars: a simple block-meter animation
- wave: a scrolling ribbon style
- minimal: almost no motion, just a status blink

Nice follow-ups:

- auto mode that chooses a visual style based on track length or play state
- a progress ribbon that doubles as a track-position indicator
- a track-aware mode that changes style when paused or when a new song starts

## Next pass: platform polish

Goal: keep the app feeling at home on Windows, macOS, and Linux.

Things to tighten:

- VLC path probing on each platform
- shell commands in widget examples
- default music root handling
- install notes for each OS

## Next pass: speed and startup

Goal: make large libraries feel instant.

Ideas:

- smarter cache invalidation
- incremental refresh / rescan logic
- background metadata loading only when requested
- cache track lists by folder signature and mtime

## Next pass: widget polish

Goal: make the repo easier to drop into WaveTerm.

Ideas:

- more exact widget examples for common config paths
- a separate visualizer-only widget
- a command variant that launches with `--visuals` by default

## Later / maybe

- real audio-reactive visualization if the backend exposes samples cleanly
- search/filter in the player UI
- album-art-aware color themes
- more compact/mobile-friendly layouts for tiny panes

## Suggested order

1. Visual modes
2. Platform polish
3. Speed and startup
4. Widget polish
5. Bigger optional features
