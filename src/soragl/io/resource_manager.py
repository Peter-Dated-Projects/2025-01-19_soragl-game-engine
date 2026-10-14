import logging
import pygame

import os

logger = logging.getLogger(__name__)

# ======================================================================== #
# class
# ======================================================================== #

IMAGE_SUFFIX = [
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".gif",
    ".tiff",
    ".ico",
]

AUDIO_SUFFIX = [
    ".wav",
    ".mp3",
    ".ogg",
    ".flac",
]


class ResourceManager:
    def __init__(self):
        self._cached = {}

    def load(self, path: str):
        # check if file exists
        if not os.path.exists(path):
            raise FileNotFoundError(f"Resource `{path}` not found")

        result = None
        if path in self._cached:
            return self._cached[path]

        # laod the resource
        ext = os.path.splitext(path)[1].lower()
        logger.debug(f"File extension of file: {path} = {ext}")
        if ext in IMAGE_SUFFIX:
            result = pygame.image.load(path).convert_alpha()
        elif ext in AUDIO_SUFFIX:
            result = pygame.mixer.Sound(path)
        else:
            raise ValueError(f"Unsupported resource type: {path}")

        # check if valid resource was loaded
        if not result:
            raise FileNotFoundError(f"Resource {path} not found")

        self._cached[path] = result
        return result

    def __getitem__(self, name: str):
        return self.load(name)
