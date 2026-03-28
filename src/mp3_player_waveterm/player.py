from dataclasses import dataclass
from pathlib import Path
import os
import platform
from typing import Protocol


class Player(Protocol):
    name: str

    def play(self, path: Path) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...
    def is_playing(self) -> bool: ...
    def position_text(self) -> str: ...


@dataclass
class NullPlayer:
    name: str = "null"
    last_path: Path | None = None
    reason: str = "audio backend unavailable"

    def play(self, path: Path) -> None:
        self.last_path = path

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def is_playing(self) -> bool:
        return False

    def position_text(self) -> str:
        return self.reason


class VLCPlayer:
    name = "vlc"

    def __init__(self) -> None:
        vlc = import_vlc()
        self._instance = vlc.Instance("--no-video", "--quiet")
        self._player = self._instance.media_player_new()
        self._player.audio_set_volume(100)
        self._current_path: Path | None = None
        self._state = "stopped"

    def play(self, path: Path) -> None:
        media = self._instance.media_new_path(str(path))
        self._player.set_media(media)
        rc = self._player.play()
        if rc == -1:
            raise RuntimeError("VLC failed to start playback")
        self._player.audio_set_volume(100)
        self._current_path = path
        self._state = "playing"

    def pause(self) -> None:
        self._player.pause()
        self._state = "paused"

    def resume(self) -> None:
        self._player.set_pause(0)
        self._state = "playing"

    def stop(self) -> None:
        self._player.stop()
        self._state = "stopped"

    def is_playing(self) -> bool:
        try:
            return bool(self._player.is_playing())
        except Exception:
            return self._state == "playing"

    def position_text(self) -> str:
        try:
            length = self._player.get_length()
            time_ms = self._player.get_time()
            if length and time_ms is not None and time_ms >= 0:
                return f"{_format_ms(time_ms)} / {_format_ms(length)}"
        except Exception:
            pass
        if self._current_path:
            return self._current_path.name
        return self._state


class BackendProbe:
    def __init__(self, available: bool, detail: str) -> None:
        self.available = available
        self.detail = detail


def probe_vlc() -> BackendProbe:
    try:
        vlc = import_vlc()
    except Exception as exc:
        return BackendProbe(False, f"python-vlc import failed: {exc}")

    try:
        instance = vlc.Instance("--no-video", "--quiet")
        _ = instance.media_player_new()
        return BackendProbe(True, "VLC/libVLC available")
    except Exception as exc:
        return BackendProbe(False, f"VLC/libVLC init failed: {exc}")


def create_player() -> Player:
    probe = probe_vlc()
    if probe.available:
        return VLCPlayer()
    return NullPlayer(reason=f"no in-app audio backend: {probe.detail}")


def doctor() -> None:
    probe = probe_vlc()
    print(f"VLC available: {probe.available}")
    print(f"Detail: {probe.detail}")
    if platform.system().lower().startswith("win"):
        print(r"Windows VLC search paths checked: Program Files\VideoLAN\VLC and Program Files (x86)\VideoLAN\VLC")


def import_vlc():
    if platform.system().lower().startswith("win"):
        _add_windows_vlc_paths()
    import vlc  # type: ignore

    return vlc


def _add_windows_vlc_paths() -> None:
    candidates = []
    for env_key in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        base = os.environ.get(env_key)
        if base:
            candidates.append(Path(base) / "VideoLAN" / "VLC")
    candidates.extend([
        Path(r"C:\Program Files\VideoLAN\VLC"),
        Path(r"C:\Program Files (x86)\VideoLAN\VLC"),
    ])

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(candidate))
        except Exception:
            pass
        os.environ["PATH"] = f"{candidate}{os.pathsep}" + os.environ.get("PATH", "")
        break


def _format_ms(value: int) -> str:
    seconds = max(0, int(value // 1000))
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"
