"""Write rendered frames to a video or image sequence through ffmpeg.

Frames come from `Renderer.read_pixels()` at a fixed frame rate, never the wall
clock, so a recording is the same however long each frame took to render.
"""

import shutil
import subprocess
from pathlib import Path

import numpy as np


class FrameRecorder:
    """`path` ending in .mp4/.mov encodes H.264; a pattern like `frames/%05d.png`
    writes numbered images. Use as a context manager, or call `close()`."""

    def __init__(
        self, path: str | Path, size: tuple[int, int], fps: int = 30, crf: int = 16
    ):
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("ffmpeg is not on PATH; install it to record frames")
        self.path = Path(path)
        self.size = size
        self.frames = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        w, h = size
        command = [
            ffmpeg, "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        ]  # fmt: skip
        if "%" not in self.path.name:
            command += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf)]
            command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        self._process = subprocess.Popen(
            command + [str(self.path)], stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )

    def write(self, frame: np.ndarray) -> None:
        """One (height, width, 3) uint8 frame, top row first."""
        if frame.shape != (self.size[1], self.size[0], 3):
            raise ValueError(f"Frame is {frame.shape}, recorder expects {self.size}")
        try:
            self._process.stdin.write(np.ascontiguousarray(frame, np.uint8).tobytes())
        except BrokenPipeError:
            self.close()  # raises with ffmpeg's error message
        self.frames += 1

    def close(self) -> None:
        if self._process.stdin.closed:
            return
        self._process.stdin.close()
        error = self._process.stderr.read().decode(errors="replace")
        if self._process.wait() != 0:
            raise RuntimeError(f"ffmpeg failed writing {self.path}: {error.strip()}")

    def __enter__(self) -> "FrameRecorder":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
