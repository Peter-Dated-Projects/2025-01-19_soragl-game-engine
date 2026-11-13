"""Write rendered frames to a video or image sequence through ffmpeg.

Frames come from `Renderer.read_pixels()` at a fixed frame rate, never the wall
clock, so a recording is the same however long each frame took to render.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np


class FrameRecorder:
    """`path` ending in .mp4/.mov encodes H.264; a pattern like `frames/%05d.png`
    writes numbered images. Use as a context manager, or call `close()`.

    `size` is the size of the frames you write. `upscale` > 1 makes the output that
    many times bigger with nearest-neighbour scaling, so you can write
    `read_pixels(native=True)` frames and still get a full-size pixel-art video.
    """

    def __init__(
        self,
        path: str | Path,
        size: tuple[int, int],
        fps: int = 30,
        crf: int = 16,
        upscale: int = 1,
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
        if upscale != 1:
            command += ["-vf", f"scale={w * upscale}:{h * upscale}:flags=neighbor"]
        if "%" not in self.path.name:
            command += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf)]
            command += ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        # a file, not a pipe: a pipe nobody drains can fill up and block ffmpeg
        self._errors = tempfile.TemporaryFile()
        self._process = subprocess.Popen(
            command + [str(self.path)], stdin=subprocess.PIPE, stderr=self._errors
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
        try:
            self._process.stdin.close()
        except BrokenPipeError:
            pass  # ffmpeg already exited; its exit code says why
        code = self._process.wait()
        self._errors.seek(0)
        error = self._errors.read().decode(errors="replace")
        self._errors.close()
        if code != 0:
            raise RuntimeError(f"ffmpeg failed writing {self.path}: {error.strip()}")

    def __enter__(self) -> "FrameRecorder":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
