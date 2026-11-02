"""Loading, caching and releasing of files, images, audio, textures and models.

Every resource is identified by (kind, resolved path, loader options). Loading
the same thing twice returns the cached object and adds one reference;
`release` removes one. Resources nobody references are freed by `collect()`.
"""

import json
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pygame

from soragl.io import model

logger = logging.getLogger(__name__)


# ======================================================================== #
# resource kinds
# ======================================================================== #


@dataclass(frozen=True)
class ResourceKind:
    """How to read one type of resource from disk, and how to free it again."""

    name: str
    extensions: tuple[str, ...]
    load: Callable[..., Any]
    """`load(path: Path, **options)` returns the resource."""
    unload: Callable[[Any], None] | None = None
    """Frees native memory (GPU objects etc). Plain Python objects need none."""
    size_of: Callable[[Any], int] | None = None
    """Approximate bytes held by a loaded resource, for `stats()`."""


def _load_image(path: Path) -> pygame.Surface:
    return pygame.image.load(str(path)).convert_alpha()


def _image_size(surface: pygame.Surface) -> int:
    return surface.get_width() * surface.get_height() * surface.get_bytesize()


def _audio_size(sound: pygame.mixer.Sound) -> int:
    settings = pygame.mixer.get_init()
    if settings is None:
        return 0
    frequency, bits, channels = settings
    return int(sound.get_length() * frequency * channels * abs(bits) // 8)


DEFAULT_KINDS = (
    ResourceKind(
        "image",
        (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".ico", ".webp"),
        _load_image,
        size_of=_image_size,
    ),
    ResourceKind(
        "audio",
        (".wav", ".mp3", ".ogg", ".flac"),
        lambda path: pygame.mixer.Sound(str(path)),
        size_of=_audio_size,
    ),
    ResourceKind("model", (".obj",), model.load_obj, size_of=lambda data: data.nbytes),
    ResourceKind(
        "json", (".json",), lambda path: json.loads(path.read_text(encoding="utf-8"))
    ),
    ResourceKind(
        "text",
        (".txt", ".md", ".glsl", ".vert", ".frag"),
        lambda path: path.read_text(encoding="utf-8"),
        size_of=len,
    ),
    ResourceKind("bytes", (), lambda path: path.read_bytes(), size_of=len),
)


# ======================================================================== #
# manager
# ======================================================================== #


@dataclass
class _Entry:
    kind: ResourceKind
    value: Any
    size: int
    refs: int = 0


@dataclass(frozen=True)
class ResourceStats:
    count: int
    bytes: int
    by_kind: dict[str, tuple[int, int]] = field(default_factory=dict)
    """kind name -> (resource count, bytes)"""


class ResourceManager:
    def __init__(self, search_paths: tuple[str | Path, ...] = ()):
        self._kinds: dict[str, ResourceKind] = {}
        self._kind_by_extension: dict[str, str] = {}
        self._entries: dict[tuple, _Entry] = {}
        self._search_paths: list[Path] = [Path(p) for p in search_paths]
        self._clearing = False

        for kind in DEFAULT_KINDS:
            self.register_kind(kind)

    # ------------------------------------------------------------------------ #
    # configuration
    # ------------------------------------------------------------------------ #

    def register_kind(self, kind: ResourceKind) -> None:
        """Add (or replace) a resource kind. Extensions are matched case-insensitively."""
        self._kinds[kind.name] = kind
        for extension in kind.extensions:
            self._kind_by_extension[extension.lower()] = kind.name

    def add_search_path(self, directory: str | Path) -> None:
        """Relative resource paths are also looked up under this directory."""
        self._search_paths.append(Path(directory))

    def resolve(self, path: str | Path) -> Path:
        """The absolute path of an existing file: tried as given, then under each search path."""
        given = Path(path)
        candidates = (
            [given]
            if given.is_absolute()
            else [given, *(p / given for p in self._search_paths)]
        )
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError(f"Resource `{path}` not found")

    # ------------------------------------------------------------------------ #
    # loading + releasing
    # ------------------------------------------------------------------------ #

    def load(self, path: str | Path, kind: str | None = None, **options) -> Any:
        """Return the resource at `path`, loading it if needed, and add a reference.

        `kind` defaults to the one registered for the file extension.
        `options` are passed to the kind's loader and are part of the cache key.
        """
        key, resolved, kind_ = self._identify(path, kind, options)
        entry = self._entries.get(key)
        if entry is None:
            value = kind_.load(resolved, **options)
            size = kind_.size_of(value) if kind_.size_of else resolved.stat().st_size
            entry = self._entries[key] = _Entry(kind_, value, size)
            logger.debug("loaded %s %s (%d bytes)", kind_.name, resolved, size)
        entry.refs += 1
        return entry.value

    def __getitem__(self, path: str | Path) -> Any:
        return self.load(path)

    def preload(self, paths: list[str | Path]) -> None:
        """Load each path now. The references are held until released."""
        for path in paths:
            self.load(path)

    def release(self, path: str | Path, kind: str | None = None, **options) -> None:
        """Remove one reference added by `load`. The resource stays cached until `collect()`."""
        if self._clearing:
            return  # unloaders release their dependencies; `clear()` frees those anyway
        key, resolved, _ = self._identify(path, kind, options)
        entry = self._entries.get(key)
        if entry is None or entry.refs == 0:
            raise ValueError(f"`{resolved}` was released more often than it was loaded")
        entry.refs -= 1

    def collect(self) -> int:
        """Free every resource with no references left. Returns how many were freed."""
        freed = 0
        while True:
            unused = [key for key, entry in self._entries.items() if entry.refs == 0]
            if not unused:
                return freed
            for key in unused:
                self._free(self._entries.pop(key))
            freed += len(unused)

    def clear(self) -> None:
        """Free everything, ignoring references. Used at shutdown."""
        entries, self._entries = list(self._entries.values()), {}
        self._clearing = True
        try:
            for entry in entries:
                self._free(entry)
        finally:
            self._clearing = False

    @contextmanager
    def scope(self) -> Iterator["ResourceScope"]:
        """Everything loaded through the scope is released and collected on exit."""
        scope = ResourceScope(self)
        try:
            yield scope
        finally:
            scope.close()

    # ------------------------------------------------------------------------ #
    # inspection
    # ------------------------------------------------------------------------ #

    def is_loaded(self, path: str | Path, kind: str | None = None, **options) -> bool:
        try:
            key, _, _ = self._identify(path, kind, options)
        except FileNotFoundError:
            return False
        return key in self._entries

    def ref_count(self, path: str | Path, kind: str | None = None, **options) -> int:
        key, _, _ = self._identify(path, kind, options)
        entry = self._entries.get(key)
        return entry.refs if entry else 0

    def stats(self) -> ResourceStats:
        by_kind: dict[str, tuple[int, int]] = {}
        for entry in self._entries.values():
            count, size = by_kind.get(entry.kind.name, (0, 0))
            by_kind[entry.kind.name] = (count + 1, size + entry.size)
        return ResourceStats(
            count=len(self._entries),
            bytes=sum(size for _, size in by_kind.values()),
            by_kind=by_kind,
        )

    # ------------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------------ #

    def _identify(self, path, kind, options):
        resolved = self.resolve(path)
        kind_ = self._kinds.get(kind) if kind else self._kind_for(resolved)
        if kind_ is None:
            raise ValueError(f"Unknown resource kind: {kind}")
        key = (kind_.name, str(resolved), tuple(sorted(options.items())))
        return key, resolved, kind_

    def _kind_for(self, path: Path) -> ResourceKind:
        name = self._kind_by_extension.get(path.suffix.lower())
        if name is None:
            raise ValueError(f"Unsupported resource type: {path}")
        return self._kinds[name]

    def _free(self, entry: _Entry) -> None:
        if entry.kind.unload:
            entry.kind.unload(entry.value)


class ResourceScope:
    """Loads resources and remembers them, so a level or screen can drop them together."""

    def __init__(self, manager: ResourceManager):
        self._manager = manager
        self._held: list[tuple[str | Path, str | None, dict]] = []

    def load(self, path: str | Path, kind: str | None = None, **options) -> Any:
        value = self._manager.load(path, kind, **options)
        self._held.append((path, kind, options))
        return value

    def close(self) -> None:
        for path, kind, options in self._held:
            self._manager.release(path, kind, **options)
        self._held.clear()
        self._manager.collect()
