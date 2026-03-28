
from pathlib import Path
from threading import Thread
import sys

try:
    from textual.app import App, ComposeResult
except Exception:  # pragma: no cover - lets import fail loudly later if needed
    App = object  # type: ignore[assignment]
    ComposeResult = object  # type: ignore[assignment]

from textual.widgets import Footer, Header, ListItem, ListView, Static

from .library import Track, resolve_root, scan_library
from .player import Player, create_player


class WaveTermMP3App(App):
    TITLE = "WaveTerm MP3 Player"
    SUB_TITLE = "compact file-based browser/player"
    CSS = """
    Screen {
        layout: vertical;
    }

    #status {
        height: 3;
        padding: 0 1;
        border: heavy $accent;
    }

    #visualizer {
        height: 1;
        padding: 0 1;
        color: $primary;
    }

    #tracks {
        height: 1fr;
        border: heavy $primary;
    }

    #details {
        height: 6;
        padding: 0 1;
        border: heavy $accent;
    }
    """

    BINDINGS = [
        ("enter", "play_selected", "Play"),
        ("space", "pause_resume", "Play/Pause"),
        ("n", "next_track", "Next"),
        ("p", "previous_track", "Previous"),
        ("s", "stop", "Stop"),
        ("r", "rescan", "Rescan"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, root: str | None = None, read_tags: bool = False, visuals: bool = False, visual_mode: str = "pulse", use_cache: bool = True) -> None:
        super().__init__()
        self._explicit_root = root
        self._read_tags = read_tags
        self._visuals = visuals
        self._visual_mode = visual_mode
        self._use_cache = use_cache
        self.root_path: Path = resolve_root(root)
        self.tracks: list[Track] = []
        self.player: Player = create_player()
        self.current_index: int = 0
        self.now_playing: Track | None = None
        self._loading = True
        self._scan_generation = 0
        self._visual_frame = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="status")
        if self._visuals:
            yield Static(id="visualizer")
        yield ListView(id="tracks")
        yield Static(id="details")
        yield Footer()

    def on_mount(self) -> None:
        self._schedule_scan()
        if self._visuals:
            self.set_interval(0.18, self._tick_visualizer)
        self.set_interval(0.5, self._poll_track_end)
        backend = getattr(self.player, "name", self.player.__class__.__name__)
        reason = getattr(self.player, "reason", "")
        scan_mode = "full" if self._read_tags else "fast"
        cache_mode = "on" if self._use_cache else "off"
        mode_text = f"{self._visual_mode}{' + visuals' if self._visuals else ''}"
        self.notify(f"audio backend: {backend} {reason}".strip())
        self.notify(f"scan mode: {scan_mode} | cache: {cache_mode} | visuals: {mode_text}")

    def _schedule_scan(self) -> None:
        self._scan_generation += 1
        generation = self._scan_generation
        self._loading = True
        self._render_status()
        self._render_details(None)
        self._render_visualizer()
        Thread(target=self._load_library_thread, args=(generation,), daemon=True).start()

    def _load_library_thread(self, generation: int) -> None:
        tracks = scan_library(self.root_path, read_tags=self._read_tags, use_cache=self._use_cache)
        self.call_from_thread(self._apply_scan_result, generation, tracks)

    def _apply_scan_result(self, generation: int, tracks: list[Track]) -> None:
        if generation != self._scan_generation:
            return

        self.tracks = tracks
        tracks_view = self.query_one("#tracks", ListView)
        tracks_view.clear()
        for track in self.tracks:
            item = ListItem(Static(track.display))
            item.track = track  # type: ignore[attr-defined]
            tracks_view.append(item)

        self.current_index = 0
        self._loading = False
        self._render_status()
        self._render_details(self.tracks[0] if self.tracks else None)
        self._render_visualizer()

    def _render_status(self) -> None:
        now = self.now_playing.display if self.now_playing else "idle"
        position = self.player.position_text()
        backend = getattr(self.player, "name", self.player.__class__.__name__)
        scan_mode = "full" if self._read_tags else "fast"
        load_state = "loading" if self._loading else "ready"
        visuals_state = self._visual_mode if self._visuals else "off"
        status = (
            f"Root: {self.root_path}\n"
            f"Tracks: {len(self.tracks)} | Scan: {scan_mode} | Load: {load_state} | "
            f"Now: {now} | State: {'playing' if self.player.is_playing() else 'stopped'} | {position} | {backend} | Visuals: {visuals_state}"
        )
        self.query_one("#status", Static).update(status)

    def _render_visualizer(self) -> None:
        if not self._visuals:
            return
        visual = self.query_one("#visualizer", Static)
        if self._loading:
            visual.update("Loading music library…")
            return
        if not self.now_playing:
            visual.update("Idle")
            return

        if not self.player.is_playing():
            visual.update(self._paused_visual())
            return

        visual.update(self._playing_visual())

    def _paused_visual(self) -> str:
        track = self.now_playing.song if self.now_playing else ""
        if self._visual_mode == "minimal":
            return f"Paused · {track}"
        return f"Paused · {track} · ░░░░░░░░░░░"

    def _playing_visual(self) -> str:
        track = self.now_playing.song if self.now_playing else ""
        mode = self._resolve_visual_mode()
        frame = self._visual_frame

        if mode == "minimal":
            return f"▶ {track}"

        if mode == "bars":
            heights = [1, 3, 5, 7, 4, 6, 2, 5]
            chars = " ▁▂▃▄▅▆▇█"
            bars = [chars[(frame + h + i) % len(chars)] for i, h in enumerate(heights)]
            return f"{track} {''.join(bars)}"

        if mode == "wave":
            waves = "~≈≋≋≈~≈≋~≈≋"
            shift = frame % len(waves)
            ribbon = (waves[shift:] + waves[:shift]) * 2
            return f"{track} {ribbon[:20]}"

        # pulse / auto default
        pulse = "◐◓◑◒"
        left = pulse[frame % len(pulse)]
        right = pulse[(frame + 2) % len(pulse)]
        fill = "█" * (4 + (frame % 6))
        return f"{left} {track} {fill} {right}"

    def _resolve_visual_mode(self) -> str:
        if self._visual_mode != "auto":
            return self._visual_mode
        if not self.now_playing:
            return "minimal"
        if self.now_playing.duration is not None and self.now_playing.duration >= 360:
            return "wave"
        if self.now_playing.duration is not None and self.now_playing.duration >= 180:
            return "bars"
        return "pulse"

    def _tick_visualizer(self) -> None:
        self._visual_frame += 1
        self._render_visualizer()

    def _poll_track_end(self) -> None:
        if self._loading or not self.tracks or self.now_playing is None:
            return
        if self.player.consume_end_event():
            self.action_next_track()

    def _render_details(self, track: Track | None) -> None:
        if track is None:
            detail = "No MP3s found in this root."
        else:
            detail = (
                f"Selected: {track.display}\n"
                f"Band: {track.band}\n"
                f"Album: {track.album}\n"
                f"Song: {track.song}\n"
                f"Dur: {track.duration_text}\n"
                f"File: {track.path}"
            )
        self.query_one("#details", Static).update(detail)

    def _selected_track(self) -> Track | None:
        if not self.tracks:
            return None
        tracks_view = self.query_one("#tracks", ListView)
        highlighted = getattr(tracks_view, "highlighted_child", None)
        if highlighted is not None:
            track = getattr(highlighted, "track", None)
            if track is not None:
                return track
        return self.tracks[min(self.current_index, len(self.tracks) - 1)]

    def _play_track(self, track: Track) -> None:
        backend = getattr(self.player, "name", self.player.__class__.__name__)
        try:
            self.player.play(track.path)
        except Exception as exc:
            self.notify(f"play failed: {exc}", severity="error")
            self._render_status()
            return

        self.now_playing = track
        self.notify(f"playing via {backend}: {track.display}")
        self._render_status()
        self._render_details(track)
        self._render_visualizer()

    def _play_selected_or_start(self) -> None:
        track = self._selected_track()
        if track:
            self._play_track(track)

    def on_list_view_highlighted(self, event) -> None:  # textual event API varies by version
        track = getattr(event.item, "track", None)
        if track is not None:
            try:
                self.current_index = self.tracks.index(track)
            except ValueError:
                self.current_index = 0
            self._render_details(track)
            self._render_status()
            self._render_visualizer()

    def on_list_view_selected(self, event) -> None:
        track = getattr(event.item, "track", None)
        if track is not None:
            try:
                self.current_index = self.tracks.index(track)
            except ValueError:
                self.current_index = 0
            self._play_track(track)

    def action_play_selected(self) -> None:
        self._play_selected_or_start()

    def action_pause_resume(self) -> None:
        if self.player.is_playing():
            self.player.pause()
            self._render_status()
            self._render_visualizer()
            return

        if self.now_playing is None or self.player.position_text() in {"stopped", "player unavailable"} or getattr(self.player, "name", "") == "null":
            self._play_selected_or_start()
            return

        self.player.resume()
        self._render_status()
        self._render_visualizer()

    def action_stop(self) -> None:
        self.player.stop()
        self.now_playing = None
        self._render_status()
        self._render_visualizer()

    def action_rescan(self) -> None:
        self._schedule_scan()

    def action_next_track(self) -> None:
        if not self.tracks:
            return
        self.current_index = min(len(self.tracks) - 1, self.current_index + 1)
        self._play_track(self.tracks[self.current_index])

    def action_previous_track(self) -> None:
        if not self.tracks:
            return
        self.current_index = max(0, self.current_index - 1)
        self._play_track(self.tracks[self.current_index])


def main() -> None:
    root = None
    read_tags = False
    visuals = False
    visual_mode = "pulse"
    use_cache = True
    args = sys.argv[1:]

    if "--full-scan" in args:
        read_tags = True
        args = [arg for arg in args if arg != "--full-scan"]
    if "--visuals" in args:
        visuals = True
        args = [arg for arg in args if arg != "--visuals"]
    if "--visual-mode" in args:
        idx = args.index("--visual-mode")
        if idx + 1 < len(args):
            visual_mode = args[idx + 1]
        args = [arg for i, arg in enumerate(args) if i not in {idx, idx + 1}]
    if "--no-cache" in args:
        use_cache = False
        args = [arg for arg in args if arg != "--no-cache"]

    if "--root" in args:
        idx = args.index("--root")
        if idx + 1 < len(args):
            root = args[idx + 1]
    elif args:
        root = args[0]

    if visual_mode not in {"pulse", "bars", "wave", "minimal", "auto"}:
        visual_mode = "pulse"

    WaveTermMP3App(root=root, read_tags=read_tags, visuals=visuals, visual_mode=visual_mode, use_cache=use_cache).run()
