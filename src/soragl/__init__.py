"""SoraGL: a 2D/3D Python game engine built on pygame-ce and moderngl."""

from importlib.metadata import PackageNotFoundError, version

from soragl.config import EngineConfig

try:
    __version__ = version("soragl")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["EngineConfig", "init", "run", "stop", "__version__"]


def __getattr__(name: str):
    # context pulls in OpenGL, so only import it when the engine is actually used
    if name in ("init", "run", "stop"):
        from soragl import context

        return getattr(context, name)
    raise AttributeError(f"module 'soragl' has no attribute {name!r}")
