import os
import json
import pygame

from soragl import state

from soragl.ecs import c_sprite

# ======================================================================== #
# SpriteSheet
# ======================================================================== #

WIDTH = "w"
HEIGHT = "h"
PADX = "padx"
PADY = "pady"
SPACINGX = "spacingx"
SPACINGY = "spacingy"

DEFAULT_CONFIG = {
    "w": 16,
    "h": 16,
    "padx": 0,
    "pady": 0,
    "spacingx": 0,
    "spacingy": 0,
}


class SpriteSheet:
    """
    This will be a base class for all "types" of spritesheets.

    For example:
    - uniform spritesheets (uniform spritesheets are the most common type)
        - all sprites are the same size
    - non-uniform spritesheets (non-uniform spritesheets are the least common type)
        - sprites are different sizes
    """

    SPRITESHEET_UUID_COUNTER = 0
    SPRITESHEET_CACHE = {}

    def __init__(self, meta: dict):
        self._meta = meta
        self._uuid = self.generate_uuid()

        # image data
        self._image = None
        self._sprites = []

    """ You are only supposed to 'create' spritesheets from the factory methods """

    @classmethod
    def from_json(cls, json_path: str):
        # load json + parse
        # only add json to cache
        if json_path in cls.SPRITESHEET_CACHE:
            return cls.SPRITESHEET_CACHE[json_path]

        # open json file and retrieve meta data + sprite loading data
        with open(json_path, "r") as f:
            data = json.load(f)

        # create spritesheet
        result = cls(data["meta"])
        result._load_nonuniform(data["sprites"])
        cls.SPRITESHEET_CACHE[json_path] = result
        return result

    @classmethod
    def from_image_array(cls, sprites: list):
        # just create - no config, no meta, not uniform

        # check if sprites is correct type
        for i in range(len(sprites)):
            if not isinstance(sprites[i], c_sprite.SpriteComponent):
                raise ValueError(f"Sprite at index {i} is not a valid sprite object")

        # create spritesheet purely from given data
        result = cls(cls.create_meta(source="", uniform=False))
        # no need to create or load anything new
        for sprite in sprites:
            result._sprites.append(sprite)
        return result

    @classmethod
    def from_image(cls, image_path: str, meta: dict, force_image: bool = False):
        # load image + create json

        # check if there is a json
        if (
            os.path.exists(os.path.splitext(image_path)[0] + ".json")
            and not force_image
        ):
            # instead load from json
            return cls.from_json(os.path.splitext(image_path)[0] + ".json")

        # load from image
        result = cls(meta)
        result._load_uniform()
        return result

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def _load_uniform(self):
        # load base image first
        self._image = state.resource_manager.load(self._meta["source"])
        _xpad = self._meta["padx"]
        _ypad = self._meta["pady"]
        _spacingx = self._meta["spacingx"]
        _spacingy = self._meta["spacingy"]

        _uwidth = self._meta["uwidth"]
        _uheight = self._meta["uheight"]

        # load sprites
        left = _spacingx
        top = _spacingy

        max_width = self._image.get_width()
        max_height = self._image.get_height()

        # y axis
        while top < max_height:
            top += _ypad

            # x axis
            while left < max_width:
                left += _xpad

                # get area
                rect = pygame.Rect(left, top, _uwidth, _uheight)
                subimg = self._image.subsurface(rect)
                sprite = c_sprite.SpriteComponent(
                    image=subimg,
                    filepath=self._meta["source"],
                    rm_uuid=self.generate_frame_uuid(
                        self._meta["source"], len(self._sprites)
                    ),
                )
                self._sprites.append(sprite)

                left += _xpad + _spacingx + _uwidth

            # move down
            top += _ypad + _spacingy + _uheight

        # generate a json file for this
        json_data = {
            "meta": self._meta,
            "sprites": [
                {
                    "area": {
                        "x": sprite.get_image().get_offset()[0],
                        "y": sprite.get_image().get_offset()[1],
                        "w": sprite.get_image().get_width(),
                        "h": sprite.get_image().get_height(),
                    },
                    "extra": {},
                }
                for sprite in self._sprites
            ],
        }

        with open(os.path.splitext(self._meta["source"])[0] + ".json", "w") as f:
            json.dump(json_data, f)

        # end

    def _load_nonuniform(self, data: list, cancel_json: bool = False):

        self._image = state.resource_manager.load(self._meta["source"])

        for sprite in data:
            rect = pygame.Rect(
                sprite["area"]["x"],
                sprite["area"]["y"],
                sprite["area"]["w"],
                sprite["area"]["h"],
            )
            subimg = self._image.subsurface(rect)
            sprite = c_sprite.SpriteComponent(
                image=subimg,
                rm_uuid=f"{self._meta['source']}||{self._sprites.__len__()}",
            )
            sprite._spritesheet = self
            self._sprites.append(sprite)

        # create json if not existent
        if (
            not os.path.exists(os.path.splitext(self._meta["source"])[0] + ".json")
            and not cancel_json
        ):
            # create the json
            json_data = {
                "meta": self._meta,
                "sprites": [
                    {
                        "area": {
                            "x": sprite.get_image().get_offset()[0],
                            "y": sprite.get_image().get_offset()[1],
                            "w": sprite.get_image().get_width(),
                            "h": sprite.get_image().get_height(),
                        },
                        "extra": {},
                    }
                ],
            }

            with open(os.path.splitext(self._meta["source"])[0] + ".json", "w") as f:
                json.dump(json_data, f)

        # end

    @staticmethod
    def generate_frame_uuid(path: str, frame_number: int):
        return f"{path}||{frame_number}"

    # ------------------------------------------------------------------------ #
    # special methods
    # ------------------------------------------------------------------------ #

    @classmethod
    def generate_uuid(cls):
        cls.SPRITESHEET_UUID_COUNTER += 1
        return cls.SPRITESHEET_UUID_COUNTER

    @classmethod
    def create_meta(
        cls,
        source: str,
        uniform: bool,
        padx: int = 0,
        pady: int = 0,
        spacingx: int = 0,
        spacingy: int = 0,
        uwidth: int = 0,
        uheight: int = 0,
    ):
        return {
            "padx": padx,
            "pady": pady,
            "spacingx": spacingx,
            "spacingy": spacingy,
            "source": source,
            "uniform": uniform,
            "uwidth": uwidth,
            "uheight": uheight,
        }

    def __str__(self):
        return f"SpriteSheet(id={self._id}, path={self._path})"

    def __id__(self):
        return self._uuid
