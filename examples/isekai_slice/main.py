"""2.5D vertical slice: render a 10 second portrait clip headless and save it as video.

A pixel-art hero walks behind and in front of a house, a slime appears, the hero
casts a water spell, the camera tracks, zooms and shakes. Every frame is a pure
function of its frame number, so two runs produce the same video.

    uv run python examples/isekai_slice/main.py                  # isekai_slice.mp4
    uv run python examples/isekai_slice/main.py frames/%04d.png  # image sequence
"""

import argparse
import math
from pathlib import Path

import moderngl
import numpy as np
import pygame
from pyglm import glm

from soragl.graphics.camera import Camera3D
from soragl.graphics.recorder import FrameRecorder
from soragl.graphics.renderer3d import Renderer
from soragl.graphics.scene3d import (
    DirectionalLight,
    Material,
    Mesh,
    MeshInstance,
    ParticleEmitter,
    Scene,
    Sprite3D,
)
from soragl.graphics.shot import Key, Shake, Shot

ARCHER = Path(__file__).parent.parent / "archer_demo/assets/entities/archer"

# hero path: (time, x, z); the house covers x and z in [-2, 2]
PATH = [(0.0, -6.0, 3.5), (2.5, -3.5, -3.5), (4.0, 1.0, -4.5), (5.5, 4.0, 1.5)]
SLIME_AT = glm.vec3(6.5, 0, -1.0)
SLIME_IN, CAST_START, CAST_END, HIT = 5.5, 6.3, 7.0, 7.2


# ======================================================================== #
# placeholder art (drawn here so the example needs no new asset files)
# ======================================================================== #


def texture(ctx, surface: pygame.Surface, repeat: bool = False) -> moderngl.Texture:
    tex = ctx.texture(surface.get_size(), 4, pygame.image.tobytes(surface, "RGBA"))
    tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
    tex.repeat_x = tex.repeat_y = repeat
    return tex


def strip(ctx, path: Path, frame_size: int = 100):
    """A horizontal sprite strip cropped to its visible pixels: (texture, uvs, (w, h) px)."""
    surface = pygame.image.load(str(path))
    w, h = surface.get_size()
    alpha = pygame.surfarray.pixels_alpha(surface).T  # (h, w)
    frames = alpha.reshape(h, w // frame_size, frame_size).max(axis=1) > 0  # (h, size)
    rows = np.flatnonzero(alpha.max(axis=1))
    cols = np.flatnonzero(frames.max(axis=0))
    top, bottom, left, right = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    uvs = [
        ((i * frame_size + left) / w, top / h, (i * frame_size + right) / w, bottom / h)
        for i in range(w // frame_size)
    ]
    return texture(ctx, surface), uvs, (right - left, bottom - top)


def draw_slime() -> pygame.Surface:
    s = pygame.Surface((16, 12), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (60, 170, 90), (0, 2, 16, 10))
    pygame.draw.ellipse(s, (110, 220, 130), (3, 3, 7, 4))
    for x in (5, 10):
        pygame.draw.rect(s, (20, 30, 20), (x, 6, 2, 2))
    return s


def draw_tree() -> pygame.Surface:
    s = pygame.Surface((16, 24), pygame.SRCALPHA)
    pygame.draw.rect(s, (110, 70, 40), (6, 16, 4, 8))
    for (x, y, r), c in zip(
        [(8, 9, 7), (5, 11, 4), (11, 11, 4), (8, 5, 5)],
        [(40, 110, 60), (50, 130, 70), (50, 130, 70), (70, 160, 80)],
    ):
        pygame.draw.circle(s, c, (x, y), r)
    return s


def draw_grass() -> pygame.Surface:
    rng = np.random.default_rng(3)
    shade = rng.integers(0, 3, (16, 16))
    palette = np.array([[96, 168, 82], [104, 178, 88], [88, 156, 76]], np.uint8)
    rgb = palette[shade]
    s = pygame.Surface((16, 16), pygame.SRCALPHA)
    s.fill((255, 255, 255, 255))
    pygame.surfarray.blit_array(s, rgb.transpose(1, 0, 2))
    return s


# ======================================================================== #
# the story, as functions of time
# ======================================================================== #


def hero_pos(t: float) -> glm.vec3:
    if t <= PATH[0][0]:
        return glm.vec3(PATH[0][1], 0, PATH[0][2])
    for (t0, x0, z0), (t1, x1, z1) in zip(PATH, PATH[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return glm.vec3(x0 + (x1 - x0) * k, 0, z0 + (z1 - z0) * k)
    return glm.vec3(PATH[-1][1], 0, PATH[-1][2])


def build_world(ctx):
    walk_tex, walk_uvs, hero_px = strip(ctx, ARCHER / "walk.png")
    idle_tex, idle_uvs, _ = strip(ctx, ARCHER / "idle.png")
    px = 1 / 12  # world units per sprite pixel
    grass = texture(ctx, draw_grass(), repeat=True)
    tree = texture(ctx, draw_tree())
    slime = texture(ctx, draw_slime())

    walls = Material((0.86, 0.78, 0.62, 1))
    meshes = [
        MeshInstance(Mesh.plane(60, 60, uv_repeat=30), Material(texture=grass)),
        MeshInstance(Mesh.box((4, 3, 4)), walls),
        MeshInstance(
            Mesh.box((4.8, 0.6, 4.8), (0, 3, 0)), Material((0.6, 0.25, 0.2, 1))
        ),
        MeshInstance(
            Mesh.box((3.2, 0.6, 3.2), (0, 3.6, 0)), Material((0.6, 0.25, 0.2, 1))
        ),
        MeshInstance(
            Mesh.box((1, 1.8, 0.1), (0.8, 0, 2.0)), Material((0.4, 0.25, 0.15, 1))
        ),
    ]
    for x, z in [(-1.8, 2.05), (2.05, -0.9)]:
        meshes.append(
            MeshInstance(
                Mesh.box((0.7, 0.7, 0.1), (x, 1.4, z)), Material((0.6, 0.85, 1, 1))
            )
        )
    for x, z in [(-3, 4.5), (3.5, 3.5), (5.5, -3)]:
        meshes.append(
            MeshInstance(
                Mesh.box((0.6, 0.4, 0.5), (x, 0, z)), Material((0.55, 0.55, 0.6, 1))
            )
        )
    trees = [
        Sprite3D(tree, (x, 0, z), (16 * px * 2.2, 24 * px * 2.2))
        for x, z in [(-6, -2), (-4, -6), (2, -7), (6, -6), (10, -4), (-8, 2), (2, 6)]
    ]

    world = dict(
        walk=(walk_tex, walk_uvs),
        idle=(idle_tex, idle_uvs),
        hero_size=(hero_px[0] * px, hero_px[1] * px),
        slime=Sprite3D(slime, SLIME_AT, (16 * px * 1.6, 12 * px * 1.6), flip_x=True),
        dust=ParticleEmitter(
            tuple(SLIME_AT + glm.vec3(0, 0.2, 0)),
            seed=1,
            lifetime=(0.4, 0.8),
            speed=(1, 2.5),
            spread=1.2,
            gravity=(0, -1, 0),
            drag=2,
            size=(0.25, 0.05),
            color_start=(0.75, 0.65, 0.5, 0.9),
            color_end=(0.6, 0.55, 0.45, 0),
            additive=False,
        ),
        spell=ParticleEmitter(
            seed=2,
            lifetime=(0.35, 0.5),
            speed=(7, 9),
            spread=0.12,
            gravity=(0, 0, 0),
            size=(0.3, 0.1),
            color_start=(0.4, 0.75, 1.0, 1.0),
            color_end=(0.2, 0.4, 1.0, 0.0),
            round=True,
        ),
        splash=ParticleEmitter(
            tuple(SLIME_AT + glm.vec3(0, 0.6, 0)),
            seed=3,
            lifetime=(0.3, 0.7),
            speed=(2, 5),
            spread=1.0,
            gravity=(0, -6, 0),
            size=(0.22, 0.0),
            color_start=(0.8, 0.95, 1.0, 1.0),
            color_end=(0.3, 0.6, 1.0, 0.0),
            round=True,
        ),
    )
    base = Scene(
        meshes=meshes,
        sprites=trees,
        light=DirectionalLight(direction=(0.6, -1.0, -0.35), shadow_extent=14),
        background=(0.62, 0.8, 0.95),
        toon_bands=3,
    )
    return base, world


def frame_scene(base: Scene, world: dict, t: float, dt: float) -> Scene:
    hero = hero_pos(t)
    moving = t < PATH[-1][0]
    tex, uvs = world["walk"] if moving else world["idle"]
    velocity = hero_pos(t + 0.05) - hero_pos(t)
    right = glm.vec3(math.cos(math.radians(45)), 0, -math.sin(math.radians(45)))
    facing_left = glm.dot(velocity, right) < 0 if moving else False
    sprites = base.sprites + [
        Sprite3D(
            tex,
            tuple(hero),
            world["hero_size"],
            uv=uvs[int(t * 10) % len(uvs)],
            flip_x=facing_left,
        )
    ]

    if SLIME_IN <= t < HIT + 0.3:
        slime: Sprite3D = world["slime"]
        hop = abs(math.sin((t - SLIME_IN) * 6)) * 0.35
        w, h = 16 / 12 * 1.6, 12 / 12 * 1.6
        squash = 1 + 0.15 * math.cos((t - SLIME_IN) * 12)
        flash = HIT <= t
        sprites.append(
            Sprite3D(
                slime.texture,
                tuple(SLIME_AT + glm.vec3(0, hop, 0)),
                (w * squash, h / squash),
                flip_x=True,
                unlit=flash,
                color=(3, 3, 3, 1) if flash else (1, 1, 1, 1),
            )
        )

    dust, spell, splash = world["dust"], world["spell"], world["splash"]
    if SLIME_IN <= t < SLIME_IN + dt:
        dust.burst(40)
    if HIT + 0.3 <= t < HIT + 0.3 + dt:
        dust.burst(30)
    hand = hero + glm.vec3(0, world["hero_size"][1] * 0.6, 0)
    spell.position = tuple(hand)
    spell.direction = tuple(glm.normalize(SLIME_AT + glm.vec3(0, 0.6, 0) - hand))
    spell.rate = 160 if CAST_START <= t < CAST_END else 0
    if HIT <= t < HIT + dt:
        splash.burst(80)
    for emitter in (dust, spell, splash):
        emitter.update(dt)

    return Scene(
        meshes=base.meshes,
        sprites=sprites,
        emitters=[dust, spell, splash],
        light=base.light,
        background=base.background,
        toon_bands=base.toon_bands,
    )


def build_shot() -> Shot:
    def track(t):
        return tuple(hero_pos(t) + glm.vec3(0, 1, 0))

    def duel(t):
        return tuple((hero_pos(t) + SLIME_AT) * 0.5 + glm.vec3(0, 1, 0))

    return Shot(
        [
            Key(0.0, track, yaw=45, pitch=35, height=11),
            Key(4.5, track, yaw=45, pitch=35, height=10),
            Key(5.8, duel, yaw=40, pitch=30, height=10),
            Key(7.6, duel, yaw=40, pitch=30, height=9.5),
            Key(10.0, duel, yaw=48, pitch=38, height=13),
        ],
        shakes=[Shake(HIT, duration=0.5, amplitude=0.35)],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", nargs="?", default="isekai_slice.mp4")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument(
        "--size", default="1440x2560", help="output WxH (9:16 for Reels)"
    )
    parser.add_argument(
        "--pixel-scale", type=int, default=4, help="output pixels per art pixel"
    )
    args = parser.parse_args()
    width, height = map(int, args.size.split("x"))

    ctx = moderngl.create_standalone_context(require=330)
    renderer = Renderer(ctx, (width, height), pixel_scale=args.pixel_scale)
    camera = Camera3D(0, orthogonal=True, width=width, height=height, near=0.1, far=200)
    base, world = build_world(ctx)
    shot = build_shot()

    dt = 1 / args.fps
    frames = round(args.seconds * args.fps)
    with FrameRecorder(
        args.output, renderer.render_size, args.fps, upscale=args.pixel_scale
    ) as recorder:
        for i in range(frames):
            t = i * dt
            shot.apply(camera, t)
            renderer.render(frame_scene(base, world, t, dt), camera)
            recorder.write(renderer.read_pixels(native=True))
    print(f"wrote {frames} frames ({width}x{height} @ {args.fps} fps) to {args.output}")


if __name__ == "__main__":
    main()
