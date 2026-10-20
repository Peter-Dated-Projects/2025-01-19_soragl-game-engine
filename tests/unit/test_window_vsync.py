"""EngineConfig.window_vsync reaches pygame's set_mode (and is left out when None)."""

import pygame
import pytest

import soragl
from soragl.config import EngineConfig


class _StopError(Exception):
    pass


def _calls(monkeypatch, cfg, fail_with_vsync=False):
    seen = []

    def fake(size, flags=0, depth=0, **kw):
        seen.append(kw)
        if kw and fail_with_vsync:
            raise pygame.error("no vsync")
        raise _StopError

    monkeypatch.setattr(pygame.display, "set_mode", fake)
    with pytest.raises(_StopError):
        soragl.init(cfg)
    return seen


def test_vsync_is_passed_only_when_set(monkeypatch):
    assert _calls(monkeypatch, EngineConfig()) == [{}]
    assert _calls(monkeypatch, EngineConfig(window_vsync=1)) == [{"vsync": 1}]
    assert _calls(monkeypatch, EngineConfig(window_vsync=0)) == [{"vsync": 0}]


def test_a_refused_vsync_falls_back_to_the_default(monkeypatch):
    assert _calls(monkeypatch, EngineConfig(window_vsync=1), True) == [
        {"vsync": 1},
        {},
    ]
