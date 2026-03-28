
from pathlib import Path
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
        ("space", "pause_resume", "Pause/Resume"),
        ("n", "next_track", "Next"),
        ("p", "previous_track", "Previous"),
        ("s", "stop", "Stop"),
        ("r", "rescan", "Rescan"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, root: str | None = None, read_tags: bool = False) -> None:
        super().__init__()
        self._explicit_root = root
        self._read_tags = read_tags
        self.root_path: Path = resolve_root(root)
        self.tracks: list[Track] = []
        self.player: Player = create_player()
        self.current_index: int = 0
        self.now_playing: Track | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="status")
        yield ListView(id="tracks")
        yield Static(id="details")
        yield Footer()

    def on_mount(self) -> None:
        self.rescan_library()
        backend = getattr(self.player, "name", self.player.__class__.__name__)
        reason = getattr(self.player, "reason", "")
        scan_mode = "full" if self._read_tags else "fast"
        message = f"audio backend: {backend} {reason}".strip()
        self.notify(f"{message} | scan mode: {scan_mode}")

    def rescan_library(self) -> None:
        self.root_path = resolve_root(self._explicit_root)
        self.tracks = scan_library(self.root_path, read_tags=self._read_tags)

        tracks_view = self.query_one("#tracks", ListView)
        tracks_view.clear()
        for track in self.tracks:
            item = ListItem(Static(track.display))
            item.track = track  # type: ignore[attr-defined]
            tracks_view.append(item)

        self.current_index = 0
        self._render_status()
        self._render_details(self.tracks[0] if self.tracks else None)

    def _render_status(self) -> None:
        now = self.now_playing.display if self.now_playing else "idle"
        position = self.player.position_text()
        backend = getattr(self.player, "name", self.player.__class__.__name__)
        scan_mode = "full" if self._read_tags else "fast"
        status = (
            f"Root: {self.root_path}\n"
            f"Tracks: {len(self.tracks)} | Scan: {scan_mode} | Now: {now} | "
            f"State: {'playing' if self.player.is_playing() else 'stopped'} | {position} | {backend}"
        )
        self.query_one("#status", Static).update(status)

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

    def on_list_view_highlighted(self, event) -> None:  # textual event API varies by version
        track = getattr(event.item, "track", None)
        if track is not None:
            try:
                self.current_index = self.tracks.index(track)
            except ValueError:
                self.current_index = 0
            self._render_details(track)
            self._render_status()

    def on_list_view_selected(self, event) -> None:
        track = getattr(event.item, "track", None)
        if track is not None:
            try:
                self.current_index = self.tracks.index(track)
            except ValueError:
                self.current_index = 0
            self._play_track(track)

    def action_play_selected(self) -> None:
        track = self._selected_track()
        if track:
            self._play_track(track)

    def action_pause_resume(self) -> None:
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.resume()
        self._render_status()

    def action_stop(self) -> None:
        self.player.stop()
        self.now_playing = None
        self._render_status()

    def action_rescan(self) -> None:
        self.rescan_library()

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
    args = sys.argv[1:]

    if "--full-scan" in args:
        read_tags = True
        args = [arg for arg in args if arg != "--full-scan"]

    if "--root" in args:
        idx = args.index("--root")
        if idx + 1 < len(args):
            root = args[idx + 1]
    elif args:
        root = args[0]

    WaveTermMP3App(root=root, read_tags=read_tags).run()
