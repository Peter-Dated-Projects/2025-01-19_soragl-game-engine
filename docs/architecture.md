# Architecture

## Layers

```
examples/, your game
        │
   soragl.init / run / stop            (context.py)
        │
   soragl.state  ◄── soragl.config     runtime objects, EngineConfig
        │
 ┌──────┼───────────────┬──────────────┬───────────┐
 system/ (ECS, world,   graphics/      audio/      io/
 game state, signals)   physics/                   (resources, models, input)
```

Dependencies point downward. `io/` and `audio/spatial.py` import nothing from the rest of
the engine, which is why they are unit-tested without a window.

## Config and state

- `soragl.config.EngineConfig` holds everything you choose before the engine starts. Pass it
  to `soragl.init()`. `window_width` / `window_height` track the live window size afterwards.
- `soragl.state` holds what `init()` creates: the GL context, framebuffer, `world`,
  `resource_manager`, `texture_manager`, `audio`, signal and input handlers, and timing
  (`run_time`, `delta_time`). Always read it as `state.x`, never `from soragl.state import x`,
  or you will keep a stale copy. `state.reset()` restores the import-time defaults; `run()`
  calls it on shutdown.

## Start-up, frame, shutdown

`init(config)`: pygame and the OpenGL 3.3 core context, window, then `input_handler`,
`signal_handler`, `ResourceManager`, `TextureManager`, `AudioEngine`, `GameStateManager`
(which creates the default world), and finally the post-processing framebuffer.

Each frame in `run()`: events, clear, `input_handler.update()`, then either a two-pass render
(3D scene to the framebuffer, then the post shader; hold `E`) or a direct render. Both call
`game_state_manager.update()` and `signal_handler.handle()`. `audio.update()` runs last so it
sees this frame's positions. Then `display.flip()` and the frame limiter.

Shutdown: game states, shader programs, buffers, VAOs, framebuffers, then `audio.shutdown()`,
`texture_manager.shutdown()` and `resource_manager.clear()` in that order, then `state.reset()`.

## ECS

- `system/ecs.py` is the framework: `ECSHandler` and `Component`.
- Concrete components live beside their domain in an `ecs/` folder: `ecs/` (general),
  `graphics/ecs/`, `physics/ecs/`, `audio/ecs/`. File names start with `c_`.
- A component can define `update()`, `debug()`, `__post_init__()` (runs again whenever
  another component joins the entity, so keep it idempotent), `__on_remove__()` (taken off
  its entity at runtime) and `__on_clean__()` (engine shutdown).
- Entities die through `entity.alive = False`, which emits a signal that the world handles.

## Resources

`ResourceManager.load(path, kind=None, **options)` resolves the path (as given, then each
search path), picks the kind from the extension, and caches by `(kind, absolute path,
options)`. Each `load` adds a reference; `release` removes one; `collect()` frees what has
none; `clear()` frees everything. A kind is a `ResourceKind(name, extensions, load, unload,
size_of)`, so other systems plug in their own. `TextureManager` does this with a `"texture"`
kind: file textures are ordinary resources whose loader reads the `"image"` resource and
whose unloader releases it.

## Audio

`AudioEngine` is a thin mixer over `pygame.mixer`: a fixed pool of channels ("voices"), a
volume per bus (`master`, `sfx`, `music`, `ui`), priority-based stealing when the pool is
full, and streamed music. A positioned voice gets its left and right gain each frame from
`audio.spatial.spatialize(listener, position, attenuation)`. Attenuation distances are in
world units, so use pixels in 2D and metres (or whatever you pick) in 3D.

## Logging

The library logs through `logging.getLogger("soragl.*")` with a `NullHandler`, so it is
silent by default. `soragl.system.log.configure(level)` prints to stderr.

## Testing

- `tests/unit/`: pure logic with no GL context (model parser, spatial audio math, resource
  manager, signals).
- `tests/e2e/`: real objects. The `engine` fixture builds the engine's objects without
  OpenGL, on SDL's dummy video and audio drivers. GPU tests use a standalone OpenGL context
  and skip if the machine cannot create one.

## Known gaps

- There is no built-in 2D presenter: the CPU `framebuffer_surface` only reaches the screen if
  your game uploads it as a texture and draws it, as `examples/archer_demo` does.
- `World2D.remove_entity` is deferred and only drops the entity from the world's table. Use
  `entity.alive = False` for a full teardown (chunks, components).
- Spatial audio is stereo panning, not HRTF.
