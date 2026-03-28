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
DEFAULT_MAC_ROOT = str(Path.home() / "Music")
DEFAULT_LINUX_ROOT = str(Path.home() / "Music")
CACHE_DIR = Path.home() / ".waveterm-mp3"
CACHE_FILE = CACHE_DIR / "library-cache.json"
STATE_FILE = CACHE_DIR / "player-state.json"


def resolve_root(explicit_root: str | None = None) -> Path:
    root = explicit_root or os.environ.get("MP3_ROOT")
    if not root:
        system = platform.system().lower()
        if system.startswith("win"):
            root = DEFAULT_WINDOWS_ROOT
        elif system == "darwin":
            root = DEFAULT_MAC_ROOT
        else:
            root = DEFAULT_LINUX_ROOT
    return Path(root).expanduser()


def iter_mp3_paths(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort(key=str.lower)
        for filename in sorted(filenames, key=str.lower):
            if filename.lower().endswith(".mp3"):
                yield Path(dirpath) / filename


def scan_library_batches(root: Path, read_tags: bool = False, batch_size: int = 50) -> Iterable[list[Track]]:
    batch: list[Track] = []
    for path in iter_mp3_paths(root):
        batch.append(track_from_path(path, read_tags=read_tags))
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def load_cached_tracks(root: Path, read_tags: bool) -> list[Track] | None:
    return _load_cache(root, read_tags)


def scan_library(root: Path, read_tags: bool = False, use_cache: bool = True) -> list[Track]:
    cached = load_cached_tracks(root, read_tags) if use_cache else None
    if cached is not None:
        return cached

    tracks: list[Track] = []
    for batch in scan_library_batches(root, read_tags=read_tags):
        tracks.extend(batch)
    if use_cache:
        _save_cache(root, read_tags, tracks)
    return tracks


def track_from_path(path: Path, read_tags: bool = False) -> Track:
    band = path.stem
    album = path.parent.name or "Unknown Album"
    song = path.stem
    duration: int | None = None

    if read_tags and MutagenFile is not None:
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


def enrich_track(track: Track) -> Track:
    return track_from_path(track.path, read_tags=True)


def enrich_tracks(tracks: Iterable[Track]) -> list[Track]:
    return [enrich_track(track) for track in tracks]


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


def _cache_signature(root: Path) -> dict:
    try:
        stat = root.stat()
        return {"root_mtime_ns": stat.st_mtime_ns, "root_exists": True}
    except FileNotFoundError:
        return {"root_exists": False, "root_mtime_ns": 0}


def _load_cache(root: Path, read_tags: bool) -> list[Track] | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None

    if data.get("root") != str(root):
        return None
    if data.get("read_tags") != read_tags:
        return None
    if data.get("signature") != _cache_signature(root):
        return None

    tracks: list[Track] = []
    for item in data.get("tracks", []):
        try:
            tracks.append(
                Track(
                    path=Path(item["path"]),
                    band=item.get("band", Path(item["path"]).stem),
                    album=item.get("album", Path(item["path"]).parent.name),
                    song=item.get("song", Path(item["path"]).stem),
                    duration=item.get("duration"),
                )
            )
        except Exception:
            continue
    return tracks


def _save_cache(root: Path, read_tags: bool, tracks: list[Track]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "root": str(root),
            "read_tags": read_tags,
            "signature": _cache_signature(root),
            "tracks": [
                {
                    "path": str(track.path),
                    "band": track.band,
                    "album": track.album,
                    "song": track.song,
                    "duration": track.duration,
                }
                for track in tracks
            ],
        }
        CACHE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


def save_cached_tracks(root: Path, read_tags: bool, tracks: list[Track]) -> None:
    _save_cache(root, read_tags, tracks)


def load_state() -> dict:
    try:
        if not STATE_FILE.exists():
            return {}
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass
