# SoraGL

A Python game engine for 2D and 3D games, built on [pygame-ce](https://pyga.me),
[moderngl](https://github.com/moderngl/moderngl) and Box2D. It has an entity-component
system, 2D physics, a resource manager, GPU texture management, an OBJ model loader, and an
audio engine with 2D and 3D positional sound.

Status: pre-alpha. The API will change.

## Install

SoraGL needs Python 3.11 to 3.13 (Box2D has no wheels for 3.14 yet) and an OpenGL 3.3 core
driver. Use it from another project with [uv](https://docs.astral.sh/uv/):

```bash
# a pinned release from git
uv add git+https://github.com/<you>/soragl@v0.1.0

# or a local checkout you are still editing
uv add --editable ../soragl-game-engine
```

## Quick start

```python
import soragl
from soragl import state
from soragl.audio import Attenuation
from soragl.audio.ecs import c_audio_listener, c_audio_source
from soragl.config import EngineConfig
from soragl.physics import entity

soragl.init(EngineConfig(window_title="My game"))
state.resource_manager.add_search_path("assets")  # so you can write "hit.wav"

player = state.world.add_entity(entity.Entity(name="player"))
player.add_component(c_audio_listener.AudioListenerComponent())

campfire = state.world.add_entity(entity.Entity(name="campfire"))
campfire._position.xy = (300, 0)
campfire.add_component(
    c_audio_source.AudioSourceComponent(
        "fire.ogg",
        loop=True,
        attenuation=Attenuation(min_distance=50, max_distance=800),  # pixels in 2D
    )
)

soragl.run()
```

Asset paths are resolved against the working directory first, then against any directory
added with `add_search_path`. Run `uv run python examples/spatial_audio/main.py` for a
working version that circles a sound around you.

## What is in it

| Area | Module | Notes |
| --- | --- | --- |
| Config and state | `soragl.config`, `soragl.state` | `EngineConfig` is passed to `init()`. Runtime objects live on `state`. |
| ECS | `soragl.system.ecs`, `*/ecs/c_*.py` | Components sit next to the domain they belong to. |
| Resources | `soragl.io.resource_manager` | Image, audio, model, json, text and bytes. Cached, ref counted, scoped, with stats. |
| Models | `soragl.io.model` | `.obj` and `.mtl` into unindexed `float32` vertices (`3f 2f 3f`). |
| Textures | `soragl.graphics.texture` | Filter, wrap, anisotropy, mipmaps and flips are part of the cache key. Render targets. |
| Audio | `soragl.audio` | Buses, voice pool with priorities, music, distance models, stereo panning. |
| Physics | `soragl.physics` | AABB and Box2D-backed colliders, SAT detection and resolution. |
| Simulation | `soragl.sim` | Headless: fixed-step clock, seeded noise, grid flow fields, stat modifiers, phase cycles. |
| 2.5D rendering | `soragl.graphics.renderer3d`, `scene3d`, `shot`, `recorder` | Lit toon meshes, flat sprites in 3D, shadows, particles, camera shots, headless video export. |

### Resources and textures

```python
from soragl.graphics.texture import TextureSettings

resources = state.resource_manager
level = resources.load("levels/one.json")  # parsed json
cat = resources.load("models/cat.obj")  # ModelData: .vertices, .groups, .materials

with resources.scope() as scope:  # released and freed when the block ends
    scope.load("music/boss.ogg")

crisp = state.texture_manager.load(
    "hero.png", TextureSettings(filter="nearest", mipmaps=False)
)
state.texture_manager.release(crisp)
state.texture_manager.collect()  # frees textures nobody references
print(resources.stats())  # count, bytes, per kind
```

### Audio

```python
audio = state.audio
audio.set_bus_volume("music", 0.6)
audio.play("hit.wav", priority=5)  # plain sound
audio.play("growl.wav", position=(10, 0, -4))  # 3D position
audio.play_music("theme.ogg", fade_ms=1000)
```

Positioned sound uses distance attenuation (`INVERSE`, `LINEAR`, `EXPONENTIAL`, `NONE`) and
constant-power stereo panning relative to the listener. It does not do HRTF, front/back
cues or Doppler. If the machine has no audio device the engine logs a warning and every
audio call becomes a no-op.

### Headless simulation

`soragl.sim` imports nothing from the rest of the engine, so game rules built on it run in
tests and tools without a window.

```python
import numpy as np
from soragl.sim import FixedStepClock, Modifiers, PhaseCycle, grid, noise

clock = FixedStepClock(step=0.1, speed=2.0)  # 10 ticks per game second, double speed
clock.advance(state.delta_time, my_game.step)  # runs my_game.step(0.1) once per tick owed

height = noise.fbm(np.random.default_rng(seed), 128, 128, cell=32)  # same seed, same map
field = grid.distance_field(walkable, sources=[(64, 64)])  # flow field toward (64, 64)
# big maps: build it a slice per tick instead, so no frame pays for the whole BFS
builder = grid.IncrementalDistanceField(walkable, sources=[(64, 64)])
while not builder.advance(budget=3000): ...  # one call per tick; builder.field is partial meanwhile
x, y = grid.downhill(field, x, y)  # next tile for any walker

mods = Modifiers().apply([("worker.speed", 0.2), ("territory_add", 4)])
mods.m("worker.speed"), mods.a("territory")  # 1.2, 4

seasons = PhaseCycle([{"food": 1.0}, {"food": 0.2}], length=180.0, blend=0.2)
seasons.advance(dt)
seasons.value("food")  # blends into the next phase over its last 20%
```

### Multiplayer

`soragl.net` puts a game online in one of two ways, chosen by the player:

* `via="p2p"`: a player's machine hosts; everyone else connects to its IP and port
  (LAN, or the internet with that UDP port forwarded on the host's router).
* `via="steam"`: Steam carries the traffic. The host makes a Steam lobby, others join it
  by lobby id, and Steam relays everything, so nobody forwards ports. This needs
  `uv sync --extra steam` (the [py_steam_net](https://github.com/HeatXD/py_steam_net)
  wheels), Valve's `libsteam_api` from the Steamworks SDK put in place once with
  `python -m soragl.net.steam install <path>`, and Steam running and signed in. App id
  480 (Valve's Spacewar test app) works until the game has its own.

And one of two sync models:

* `model="lockstep"`: only inputs travel and every machine runs the same deterministic
  simulation (RTS, many units). Checksums catch a drifting peer and resync it from a
  snapshot; late joiners get a snapshot too.
* `model="authority"`: the host simulates; clients send inputs and show the host's
  snapshots, interpolated (physics and action games: nothing needs to be deterministic).

The game supplies four methods, all bytes in and out (the engine never unpickles network
data):

```python
class MyGame:
    def net_input(self) -> bytes: ...                   # the local player's input
    def net_step(self, dt, inputs: dict[int, bytes]): ...  # one tick, every player's input
    def net_snapshot(self) -> bytes: ...                # the whole state
    def net_restore(self, data: bytes): ...             # become that state
    # optional: net_checksum() -> int, net_interpolate(older, newer, t)

session = soragl.net.host(game, via="p2p", model="lockstep", game_id="my-game", version="1.0")
session = soragl.net.join(game, via="p2p", address="192.168.1.20:7777", model="lockstep",
                          game_id="my-game", version="1.0")
for event in session.update(state.delta_time): ...  # join, leave, joined, rejected, closed, desync
```

The handshake refuses a client with a different game, version or sync settings, with the
reason. A dedicated server is a host whose own input is empty, run without a window by
`soragl.net.run_headless(session)`. `examples/net_demo` is a playable example of all of
it.

### 2.5D scenes and recorded clips

Flat pixel-art sprites standing in a lit 3D world (Paper Mario style), rendered
headless at a fixed frame rate and written to video. A `Scene` is plain data, so a
simulation can build one per frame from its own state.

```python
import moderngl
from soragl.graphics.camera import Camera3D
from soragl.graphics.recorder import FrameRecorder
from soragl.graphics.renderer3d import Renderer
from soragl.graphics.scene3d import Material, Mesh, MeshInstance, Scene, Sprite3D
from soragl.graphics.shot import Key, Shot

ctx = moderngl.create_standalone_context(require=330)  # or state.gl_context
renderer = Renderer(ctx, (1440, 2560), pixel_scale=4)  # draws at 360x640, scales up sharp
camera = Camera3D(0, orthogonal=True, width=1440, height=2560)
shot = Shot([Key(0, (0, 1, 0), height=12), Key(5, (4, 1, 0), height=8)])
scene = Scene(
    meshes=[MeshInstance(Mesh.plane(40, 40)), MeshInstance(Mesh.box((4, 3, 4)))],
    sprites=[Sprite3D(hero_texture, (3, 0, 3), size=(1, 1.5))],
)
with FrameRecorder("clip.mp4", (1440, 2560), fps=30) as recorder:
    for i in range(150):
        shot.apply(camera, i / 30)
        renderer.render(scene, camera)  # renderer.render(scene, camera, ctx.screen) in a window
        recorder.write(renderer.read_pixels())
```

Passes: directional shadow map, toon-lit meshes, alpha-cut sprites (they cast
shadows and are hidden by walls through the depth buffer), blended particles, then
the upscale. Needs `ffmpeg` on PATH to record. `examples/isekai_slice` is a full
10 second scene.

### 2D games

```python
import pygame
import soragl
from soragl import state
from soragl.config import EngineConfig
from soragl.system.game_state import GameState

soragl.init(
    EngineConfig(render_mode="2d", framebuffer_width=480, framebuffer_height=270)
)


class Play(GameState):
    def update(self):
        pygame.draw.circle(state.framebuffer_surface, (255, 200, 80), (240, 135), 20)


state.game_state_manager.add_game_state("play", Play("play"))
state.game_state_manager.set_game_state("play")
soragl.run()  # scaled to the window, pixels kept sharp
```

## Layout

```
src/soragl/
  audio/       engine, spatial math, listener and source components
  ecs/         general-purpose components (sprites, tasks, particles)
  graphics/    buffers, camera, shaders, textures, sprite sheets
  io/          input, resource manager, model loader
  physics/     entities, interaction field, collision detection and resolution
  net/         multiplayer: UDP and Steam transports, sessions, lockstep and authority
  sim/         headless simulation helpers (clock, noise, grid, modifiers, cycles)
  system/      ECS core, world, game state, signals, animation, logging
  data/        shaders bundled with the package
examples/      archer_demo (full demo), spatial_audio, net_demo, isekai_slice (2.5D clip)
tests/         unit/ (pure logic) and e2e/ (real pygame, mixer and OpenGL objects)
docs/          architecture.md
```

## Development

```bash
uv sync                       # create .venv and install everything, including dev tools
uv run pytest                 # tests (OpenGL tests skip when no GL context is available)
uv run ruff check             # lint
uv run ruff format            # format
uv run python examples/archer_demo/main.py
uv build                      # sdist + wheel in dist/
```

Conventions: `snake_case` for modules, functions and variables, `PascalCase` for classes.
Component modules start with `c_`. Log through `logging.getLogger(__name__)`; call
`soragl.system.log.configure()` in your app to see the output.

## About the game

Welcome to game development with Peter! Today we will be coding the greatest game to ever
walk the earth. Walk. No.. more like `ink` the earth haha... yeah its an ink game.
**Splatoon** but better and rogue-lite and with **teleportation** because that's always nice.

Also...

We've got anime based lore lol. That's good right? Kinda like `Wistoria` but **ink** and
**squids** and **gun** and **teleport**.

### Development log

I should start a YouTube series for this if I want to get anywhere.

### Images

Hey. Here are some images of my work so far.

![image6](docs/images/img_4031.jpg)
![image5](docs/images/img_4030.jpg)
![image4](docs/images/img_4029.jpg)
![image3](docs/images/img_4028.jpg)
![image2](docs/images/img_4027.jpg)
![image1](docs/images/img_4026.jpg)
