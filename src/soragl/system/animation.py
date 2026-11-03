import os
import json
import pygame

from soragl import state

from soragl.system import ecs

from soragl.ecs import c_sprite

from soragl.graphics import sprite_sheet

# ======================================================================== #
# Animation
# ======================================================================== #


class Animation:
    """
    This class will be used to handle the animation of a sprite.
    """

    # stores animations by filepath -- png path or json path
    ANIMATION_CACHE = {}

    def __init__(self, filepath: str):
        self._filepath = filepath
        self._sprites = []

    @classmethod
    def from_array(cls, sprite_array: list[c_sprite.SpriteComponent]):
        # verify if correct type
        if not isinstance(sprite_array, list):
            raise ValueError("sprite_array must be a list")
        for spr in sprite_array:
            if not isinstance(spr, c_sprite.SpriteComponent):
                raise ValueError(
                    "sprite_array must be a list of SpriteComponent objects"
                )

        # create animation
        result = cls(filepath="")
        for spr in sprite_array:
            result._sprites.append(spr)
        return result

    @classmethod
    def from_json(cls, json_path: str):
        if json_path in cls.ANIMATION_CACHE:
            return cls.ANIMATION_CACHE[json_path]

        # load json file
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        meta = data["meta"]
        frames = data["frames"]

        # load resources -- 2 types: [image, or spritesheet]
        resources = {}
        _base_path = os.path.dirname(json_path)
        for resource in meta["resources"]:
            # if not loaded, load from file
            if resource["type"] == "image":
                resources[resource["file"]] = state.resource_manager.load(
                    os.path.join(_base_path, resource["file"])
                )
            elif resource["type"] == "spritesheet":
                resources[resource["file"]] = sprite_sheet.SpriteSheet.from_json(
                    os.path.join(_base_path, resource["file"])
                )

        # stage 1: create animation objects
        result = cls(filepath=json_path)

        # stage 2: add frames to png based animations
        # presort all frame data by source and by frame number if not spritesheet
        frames.sort(
            key=lambda x: (
                x["source"],
                x["frame_number"] if x["area"] is not None else -1,
            )
        )

        for frame in frames:
            source = frame["source"]
            area = (
                pygame.Rect(
                    frame["area"]["x"],
                    frame["area"]["y"],
                    frame["area"]["w"],
                    frame["area"]["h"],
                )
                if frame["area"] is not None
                else None
            )
            duration = frame["duration"]
            frame_number = frame["frame_number"]

            # get (or create) the SpriteComponent object and add it to the animation
            if source.endswith(".json"):
                # from spritesheet
                res = resources[source]
                for i in range(len(res._sprites)):
                    res._sprites[i]._extra["duration"] = duration[i]
                    res._sprites[i]._extra["frame_number"] = frame_number[i]
                    result._sprites.append(res._sprites[i])
            else:
                _spr = c_sprite.SpriteComponent(
                    image=resources[source].subsurface(area),
                    filepath=source,
                    rm_uuid=sprite_sheet.SpriteSheet.generate_frame_uuid(
                        source, frame_number
                    ),
                )
                _spr._extra["duration"] = duration
                _spr._extra["frame_number"] = frame_number

                result._sprites.append(_spr)

        # done
        cls.ANIMATION_CACHE[json_path] = result
        return result

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def get_register(self):
        return AnimationRegister(self)


# ======================================================================== #
# Animation Register
# ======================================================================== #


class AnimationRegister:
    def __init__(self, animation: Animation):
        self._animation = animation

        # handle frame grabbing
        self._current_frame = 0
        self._delta_time = 0

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        self._delta_time += state.delta_time
        if self._delta_time > self.get_current_sprite_duration():
            self._current_frame += 1
            if self._current_frame >= len(self._animation._sprites):
                self._current_frame = 0
            self._delta_time = 0

    def get_current_sprite(self):
        return self._animation._sprites[self._current_frame]

    def get_current_sprite_duration(self):
        return self._animation._sprites[self._current_frame]._extra["duration"]

    def get_current_frame_number(self):
        return self._animation._sprites[self._current_frame]._extra["frame_number"]


# ======================================================================== #
# Animated Sprite Component
# ======================================================================== #


class AnimatedSpriteComponent(ecs.Component):
    def __init__(self, animation: Animation, target: c_sprite.SpriteComponent = None):
        super().__init__()

        self._animation = animation
        self._register = animation.get_register()
        self._target_comp = target

    def __post_init__(self):
        if self._target_comp is not None:
            self._target_comp._image = self._register.get_current_sprite().get_image()
        else:
            # try to find a sprite component in the entity
            for comp in self._entity._components.values():
                if isinstance(comp, c_sprite.SpriteComponent):
                    self._target_comp = comp
                    break

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def update(self):
        self._register.update()
        if self._target_comp is not None:
            self._target_comp._image = self._register.get_current_sprite().get_image()
            self._target_comp._rect.size = (
                self._target_comp._image.get_size()
            )  # update rect size.
