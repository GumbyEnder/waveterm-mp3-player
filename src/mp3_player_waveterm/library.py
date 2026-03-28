
from dataclasses import dataclass
from pathlib import Path
import os
import platform
from typing import Iterable

try:
    from mutagen import File as MutagenFile
except Exception:  # pragma: no cover - optional at runtime
    MutagenFile = None  # type: ignore[assignment]


@dataclass(frozen=True)
class Track:
    path: Path
    band: str
    album: str
    song: str
    duration: int | None

    @property
    def display(self) -> str:
        return f"{self.band} · {self.album} · {self.song}"

    @property
    def duration_text(self) -> str:
        if self.duration is None:
            return "--:--"
        minutes, seconds = divmod(max(0, int(self.duration)), 60)
        return f"{minutes:02d}:{seconds:02d}"


DEFAULT_WINDOWS_ROOT = r"K:\media vault\music"
DEFAULT_LINUX_ROOT = str(Path.home() / "Music")


def resolve_root(explicit_root: str | None = None) -> Path:
    root = explicit_root or os.environ.get("MP3_ROOT")
    if not root:
        root = DEFAULT_WINDOWS_ROOT if platform.system().lower().startswith("win") else DEFAULT_LINUX_ROOT
    return Path(root).expanduser()


def scan_library(root: Path) -> list[Track]:
    if not root.exists():
        return []

    mp3_paths = sorted(
        (p for p in root.rglob("*.mp3") if p.is_file()),
        key=lambda p: (str(p.parent).lower(), p.name.lower()),
    )
    return [track_from_path(path) for path in mp3_paths]


def track_from_path(path: Path) -> Track:
    band = path.stem
    album = path.parent.name or "Unknown Album"
    song = path.stem
    duration: int | None = None

    if MutagenFile is not None:
        try:
            audio = MutagenFile(path, easy=True)
            if audio:
                tags = audio.tags or {}
                band = _pick(tags, "albumartist", "artist", default=band)
                album = _pick(tags, "album", default=album)
                song = _pick(tags, "title", default=song)
                info = getattr(audio, "info", None)
                if info and getattr(info, "length", None):
                    duration = int(info.length)
        except Exception:
            pass

    return Track(path=path, band=band, album=album, song=song, duration=duration)


def _pick(tags: dict, *keys: str, default: str) -> str:
    for key in keys:
        value = tags.get(key)
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value:
            text = str(value).strip()
            if text:
                return text
    return default


def tracks_for_paths(paths: Iterable[Path]) -> list[Track]:
    return [track_from_path(path) for path in paths]
