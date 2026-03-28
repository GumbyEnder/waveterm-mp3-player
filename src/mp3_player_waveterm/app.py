from threading import Thread
import sys

try:
    from textual.app import App, ComposeResult
except Exception:  # pragma: no cover - lets import fail loudly later if needed
    App = object  # type: ignore[assignment]
    ComposeResult = object  # type: ignore[assignment]

from textual.widgets import Footer, Header, Input, ListItem, ListView, Static

from .library import Track, load_cached_tracks, load_state, resolve_root, save_cached_tracks, save_state, scan_library_batches
from .player import Player, create_player


class WaveTermMP3App(App):
    TITLE = "WaveTerm MP3 Player"
    SUB_TITLE = "compact file-based browser/player"
    CSS = """
    Screen {
        layout: vertical;
    }

    #search {
        height: 3;
        padding: 0 1;
        border: heavy $accent;
    }

    #status {
        height: 4;
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
        height: 7;
        padding: 0 1;
        border: heavy $accent;
    }
    """

    BINDINGS = [
        ("/", "focus_search", "Search"),
        ("enter", "play_selected", "Play"),
        ("space", "pause_resume", "Play/Pause"),
        ("a", "enqueue_selected", "Queue"),
        ("c", "clear_queue", "Clear Queue"),
        ("n", "next_track", "Next"),
        ("p", "previous_track", "Previous"),
        ("s", "stop", "Stop"),
        ("r", "rescan", "Rescan"),
        ("escape", "focus_tracks", "Tracks"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        root: str | None = None,
        read_tags: bool = False,
        visuals: bool = False,
        visual_mode: str = "pulse",
        use_cache: bool = True,
    ) -> None:
        super().__init__()
        self._explicit_root = root
        self._read_tags = read_tags
        self._visuals = visuals
        self._visual_mode = visual_mode
        self._use_cache = use_cache
        self.root_path: Path = resolve_root(root)
        self.tracks: list[Track] = []
        self.filtered_tracks: list[Track] = []
        self.player: Player = create_player()
        self.current_index: int = 0
        self.now_playing: Track | None = None
        self.queue: list[Track] = []
        self.search_query = ""
        self._loading = True
        self._scan_generation = 0
        self._visual_frame = 0
        self._saved_state = load_state()
        self._pending_selected_path: str | None = None
        self._pending_resume_path: str | None = None
        self._pending_queue_paths: set[str] = set()
        self._restored_queue_paths: set[str] = set()
        self._selection_initialized = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search artist / album / song", id="search")
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

    def on_unmount(self) -> None:
        self._save_state()

    def _state_matches_root(self) -> bool:
        return self._saved_state.get("root") == str(self.root_path)

    def _schedule_scan(self) -> None:
        self._scan_generation += 1
        generation = self._scan_generation
        self._loading = True
        self.tracks = []
        self.filtered_tracks = []
        self.current_index = 0
        self._visual_frame = 0
        self._selection_initialized = False
        self._prepare_restore_state()
        try:
            self.query_one("#search", Input).value = self.search_query
        except Exception:
            pass
        self._clear_tracks_view()
        self._render_status()
        self._render_details(None)
        self._render_visualizer()
        Thread(target=self._load_library_thread, args=(generation,), daemon=True).start()

    def _prepare_restore_state(self) -> None:
        self._pending_selected_path = None
        self._pending_resume_path = None
        self._pending_queue_paths = set()
        self._restored_queue_paths = set()
        if not self._state_matches_root():
            self.search_query = ""
            self.queue = []
            return

        self.search_query = str(self._saved_state.get("search_query", "") or "")
        self._pending_selected_path = self._saved_state.get("selected_path") or None
        self._pending_resume_path = self._saved_state.get("now_playing_path") or None
        self._pending_queue_paths = {
            str(path)
            for path in self._saved_state.get("queue_paths", [])
            if path
        }
        self.queue = []

    def _load_library_thread(self, generation: int) -> None:
        if self._use_cache:
            cached = load_cached_tracks(self.root_path, self._read_tags)
            if cached is not None:
                self.call_from_thread(self._apply_cached_result, generation, cached)
                return

        all_tracks: list[Track] = []
        for batch in scan_library_batches(self.root_path, read_tags=self._read_tags):
            if generation != self._scan_generation:
                return
            all_tracks.extend(batch)
            self.call_from_thread(self._append_scan_batch, generation, batch)

        if generation != self._scan_generation:
            return
        if self._use_cache:
            save_cached_tracks(self.root_path, self._read_tags, all_tracks)
        self.call_from_thread(self._finish_scan_result, generation)

    def _apply_cached_result(self, generation: int, tracks: list[Track]) -> None:
        if generation != self._scan_generation:
            return
        self.tracks = list(tracks)
        self.filtered_tracks = [track for track in self.tracks if self._track_matches_query(track, self.search_query)]
        self.queue = []
        self._loading = False
        self._rebuild_tracks_view()
        self._restore_pending_track_state()
        self._render_status()
        self._render_details(self._selected_track() or self.now_playing)
        self._render_visualizer()
        self._save_state()

    def _append_scan_batch(self, generation: int, batch: list[Track]) -> None:
        if generation != self._scan_generation or not batch:
            return

        self.tracks.extend(batch)
        visible = [track for track in batch if self._track_matches_query(track, self.search_query)]
        if visible:
            self.filtered_tracks.extend(visible)
            tracks_view = self.query_one("#tracks", ListView)
            for track in visible:
                item = ListItem(Static(track.display))
                item.track = track  # type: ignore[attr-defined]
                tracks_view.append(item)
            self._restore_pending_track_state(batch)
            self._maybe_initialize_selection(visible)
        else:
            self._restore_pending_track_state(batch)

        self._render_status()
        self._render_details(self._selected_track() or self.now_playing)
        self._render_visualizer()
        self._save_state()

    def _finish_scan_result(self, generation: int) -> None:
        if generation != self._scan_generation:
            return
        self._loading = False
        if self.filtered_tracks and not self._selection_initialized:
            self._selection_initialized = True
            try:
                self.query_one("#tracks", ListView).index = 0  # type: ignore[attr-defined]
            except Exception:
                pass
        self._render_status()
        self._render_details(self._selected_track() or self.now_playing)
        self._render_visualizer()
        self._save_state()

    def _maybe_initialize_selection(self, visible: list[Track]) -> None:
        if self._selection_initialized:
            return
        selected = self._selected_track()
        if selected is None and visible:
            try:
                self.query_one("#tracks", ListView).index = 0  # type: ignore[attr-defined]
            except Exception:
                pass
            self.current_index = self.tracks.index(visible[0]) if visible[0] in self.tracks else 0
        self._selection_initialized = True

    def _restore_pending_track_state(self, batch: list[Track] | None = None) -> None:
        batch = batch or self.tracks
        for track in batch:
            path_text = str(track.path)
            if self._pending_selected_path and path_text == self._pending_selected_path:
                self._set_selected_track(track)
                self._pending_selected_path = None
            if self._pending_resume_path and path_text == self._pending_resume_path and self.now_playing is None:
                self._play_track(track, persist=False, notify=False)
                self._pending_resume_path = None
            if (
                path_text in self._pending_queue_paths
                and path_text not in self._restored_queue_paths
                and all(str(item.path) != path_text for item in self.queue)
            ):
                self.queue.append(track)
                self._restored_queue_paths.add(path_text)
        if self._pending_queue_paths and self._restored_queue_paths:
            self._pending_queue_paths.difference_update(self._restored_queue_paths)

    def _set_selected_track(self, track: Track) -> None:
        try:
            self.current_index = self.tracks.index(track)
        except ValueError:
            self.current_index = 0
        self._selection_initialized = True
        try:
            self.query_one("#tracks", ListView).index = self.filtered_tracks.index(track)  # type: ignore[attr-defined]
        except Exception:
            pass

    def _clear_tracks_view(self) -> None:
        try:
            self.query_one("#tracks", ListView).clear()
        except Exception:
            pass

    def _rebuild_tracks_view(self) -> None:
        tracks_view = self.query_one("#tracks", ListView)
        tracks_view.clear()
        for track in self.filtered_tracks:
            item = ListItem(Static(track.display))
            item.track = track  # type: ignore[attr-defined]
            tracks_view.append(item)
        if self.filtered_tracks:
            selected = self._selected_track()
            if selected in self.filtered_tracks:
                try:
                    tracks_view.index = self.filtered_tracks.index(selected)  # type: ignore[attr-defined]
                except Exception:
                    pass
            else:
                try:
                    tracks_view.index = 0  # type: ignore[attr-defined]
                except Exception:
                    pass

    def _track_matches_query(self, track: Track, query: str) -> bool:
        if not query:
            return True
        haystack = " ".join(
            [track.band, track.album, track.song, track.path.name, str(track.path)]
        ).lower()
        return query.lower() in haystack

    def _track_from_path(self, path_value: str | Path | None) -> Track | None:
        if not path_value:
            return None
        path_text = str(path_value)
        for track in self.tracks:
            if str(track.path) == path_text:
                return track
        return None

    def _tracks_from_paths(self, paths: list[str]) -> list[Track]:
        mapped: list[Track] = []
        for path in paths:
            track = self._track_from_path(path)
            if track is not None:
                mapped.append(track)
        return mapped

    def _selected_track(self) -> Track | None:
        if not self.filtered_tracks:
            return None
        tracks_view = self.query_one("#tracks", ListView)
        highlighted = getattr(tracks_view, "highlighted_child", None)
        if highlighted is not None:
            track = getattr(highlighted, "track", None)
            if track is not None:
                return track
        if 0 <= self.current_index < len(self.tracks):
            current = self.tracks[self.current_index]
            if current in self.filtered_tracks:
                return current
        return self.filtered_tracks[0]

    def _queue_paths(self) -> list[str]:
        return [str(track.path) for track in self.queue]

    def _save_state(self) -> None:
        state = {
            "root": str(self.root_path),
            "search_query": self.search_query,
            "selected_path": str(self._selected_track().path) if self._selected_track() else None,
            "queue_paths": self._queue_paths(),
            "now_playing_path": str(self.now_playing.path) if self.now_playing else None,
            "was_playing": self.player.is_playing(),
            "read_tags": self._read_tags,
            "visuals": self._visuals,
            "visual_mode": self._visual_mode,
        }
        save_state(state)

    def _render_status(self) -> None:
        now = self.now_playing.display if self.now_playing else "idle"
        position = self.player.position_text()
        backend = getattr(self.player, "name", self.player.__class__.__name__)
        scan_mode = "full" if self._read_tags else "fast"
        load_state = "loading" if self._loading else "ready"
        visuals_state = self._visual_mode if self._visuals else "off"
        queue_state = f"queue {len(self.queue)}"
        filter_state = self.search_query or "all"
        status = (
            f"Root: {self.root_path}\n"
            f"Tracks: {len(self.filtered_tracks)}/{len(self.tracks)} | Filter: {filter_state} | Scan: {scan_mode} | Load: {load_state}\n"
            f"Now: {now} | State: {'playing' if self.player.is_playing() else 'stopped'} | {position} | {backend} | Visuals: {visuals_state} | {queue_state}"
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
            queue_preview = ", ".join(item.song for item in self.queue[:3]) or "empty"
            detail = (
                f"Selected: {track.display}\n"
                f"Band: {track.band}\n"
                f"Album: {track.album}\n"
                f"Song: {track.song}\n"
                f"Dur: {track.duration_text}\n"
                f"Queue: {len(self.queue)} ({queue_preview})\n"
                f"File: {track.path}"
            )
        self.query_one("#details", Static).update(detail)

    def _play_track(self, track: Track, persist: bool = True, notify: bool = True) -> None:
        backend = getattr(self.player, "name", self.player.__class__.__name__)
        try:
            self.player.play(track.path)
        except Exception as exc:
            self.notify(f"play failed: {exc}", severity="error")
            self._render_status()
            return

        self.now_playing = track
        try:
            self.current_index = self.tracks.index(track)
        except ValueError:
            self.current_index = 0
        if notify:
            self.notify(f"playing via {backend}: {track.display}")
        self._render_status()
        self._render_details(track)
        self._render_visualizer()
        if persist:
            self._save_state()

    def _play_selected_or_start(self) -> None:
        track = self._selected_track()
        if track:
            self._play_track(track)

    def _play_next_in_sequence(self) -> None:
        if self.queue:
            track = self.queue.pop(0)
            self._play_track(track)
            return

        if not self.tracks:
            return

        if self.now_playing is not None:
            try:
                current = self.tracks.index(self.now_playing)
            except ValueError:
                current = self.current_index
        else:
            current = self.current_index

        next_index = min(len(self.tracks) - 1, current + 1)
        if next_index == current and current >= len(self.tracks) - 1:
            self.notify("end of library", severity="information")
            return
        self.current_index = next_index
        self._play_track(self.tracks[next_index])

    def on_list_view_highlighted(self, event) -> None:  # textual event API varies by version
        track = getattr(event.item, "track", None)
        if track is not None:
            try:
                self.current_index = self.tracks.index(track)
            except ValueError:
                self.current_index = 0
            self._selection_initialized = True
            self._render_details(track)
            self._render_status()
            self._render_visualizer()
            self._save_state()

    def on_list_view_selected(self, event) -> None:
        track = getattr(event.item, "track", None)
        if track is not None:
            try:
                self.current_index = self.tracks.index(track)
            except ValueError:
                self.current_index = 0
            self._selection_initialized = True
            self._play_track(track)

    def on_input_changed(self, event) -> None:
        if getattr(event.input, "id", None) != "search":
            return
        self.search_query = event.value
        self.filtered_tracks = [track for track in self.tracks if self._track_matches_query(track, self.search_query)]
        self._rebuild_tracks_view()
        self._render_status()
        self._render_details(self._selected_track() or self.now_playing)
        self._render_visualizer()
        self._save_state()

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_tracks(self) -> None:
        self.query_one("#tracks", ListView).focus()

    def action_play_selected(self) -> None:
        self._play_selected_or_start()

    def action_enqueue_selected(self) -> None:
        track = self._selected_track()
        if track is None:
            return
        self.queue.append(track)
        self.notify(f"queued: {track.display}")
        self._render_status()
        self._render_details(self._selected_track() or self.now_playing)
        self._save_state()

    def action_clear_queue(self) -> None:
        if not self.queue:
            return
        self.queue.clear()
        self.notify("queue cleared")
        self._render_status()
        self._render_details(self._selected_track() or self.now_playing)
        self._save_state()

    def action_pause_resume(self) -> None:
        if self.player.is_playing():
            self.player.pause()
            self._render_status()
            self._render_visualizer()
            self._save_state()
            return

        if self.now_playing is None or self.player.position_text() in {"stopped", "player unavailable"} or getattr(self.player, "name", "") == "null":
            self._play_selected_or_start()
            return

        self.player.resume()
        self._render_status()
        self._render_visualizer()
        self._save_state()

    def action_stop(self) -> None:
        self.player.stop()
        self.now_playing = None
        self._render_status()
        self._render_visualizer()
        self._save_state()

    def action_rescan(self) -> None:
        self._schedule_scan()

    def action_next_track(self) -> None:
        self._play_next_in_sequence()

    def action_previous_track(self) -> None:
        if not self.tracks:
            return
        if self.now_playing is not None:
            try:
                current = self.tracks.index(self.now_playing)
            except ValueError:
                current = self.current_index
        else:
            current = self.current_index
        previous_index = max(0, current - 1)
        self.current_index = previous_index
        self._play_track(self.tracks[previous_index])


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

    WaveTermMP3App(
        root=root,
        read_tags=read_tags,
        visuals=visuals,
        visual_mode=visual_mode,
        use_cache=use_cache,
    ).run()
