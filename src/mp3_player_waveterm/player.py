from dataclasses import dataclass
from pathlib import Path
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
        import vlc  # type: ignore

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


def create_player() -> Player:
    try:
        return VLCPlayer()
    except Exception as exc:
        return NullPlayer(reason=f"no in-app audio backend: {exc.__class__.__name__}")


def _format_ms(value: int) -> str:
    seconds = max(0, int(value // 1000))
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"
