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

Dependencies point downward. `io/`, `sim/` and `audio/spatial.py` import nothing from the
rest of the engine, which is why they are unit-tested without a window.

## Config and state

- `soragl.config.EngineConfig` holds everything you choose before the engine starts. Pass it
  to `soragl.init()`. `window_width` / `window_height` track the live window size afterwards.
- `soragl.state` holds what `init()` creates: the GL context, framebuffer, `world`,
  `resource_manager`, `texture_manager`, `audio`, signal and input handlers, and timing
  (`run_time`, `delta_time`). Always read it as `state.x`, never `from soragl.state import x`,
  or you will keep a stale copy. `state.reset()` restores the import-time defaults; `run()`
  calls it on shutdown.

## Start-up, frame, shutdown

`init(config)` sets up these, in order:

1. pygame, the OpenGL 3.3 core context and the window.
2. `input_handler`, `signal_handler`, `ResourceManager`, `TextureManager` and `AudioEngine`.
3. `GameStateManager`, which creates the default world.
4. Either the 3D post-processing framebuffer, or, when `render_mode="2d"`, the `SurfacePresenter`.

Each frame in `run()`:

1. Advance time. `delta_time` is capped at `config.max_delta_time`, so a stalled window does
   not teleport anything.
2. Poll events. They are forwarded to `InputHandler.process_event` and kept as `state.events`
   for the frame.
3. Call `input_handler.update()`.
4. Draw the frame. Both modes call `game_state_manager.update()` and `signal_handler.handle()`.
   - 3D: either a two-pass render (the scene to the framebuffer, then the post shader, while E
     is held) or a direct render.
   - 2D: clear `framebuffer_surface`, update, then present the surface.
5. Call `audio.update()`, last, so it sees this frame's positions.
6. `display.flip()` and the frame limiter.

## 2D games

Set `EngineConfig(render_mode="2d")` and draw everything with pygame into
`state.framebuffer_surface`.

- Each frame `SurfacePresenter` uploads that surface to a texture and draws it letterboxed to
  fill the window. `present_scaling` picks the filter: `"sharp"` (sharp-bilinear: crisp pixels
  at any scale, the default), `"nearest"` or `"linear"`. `present_integer_scale=True` limits the
  scale to whole numbers.
- `soragl.context.mouse_surface_position()` maps the mouse into surface pixels.
- Scenes are `GameState` subclasses that override `update()`. `on_enter()` and `on_exit()` run
  when `set_game_state`, `push_state` and `pop_state` switch scenes, and `__post_init__` runs
  only the first time a state becomes current.

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

## Simulation

`soragl.sim` is for game rules that must not depend on rendering or frame rate.

- `FixedStepClock.advance(real_dt, step_fn)` turns frame time into whole fixed steps,
  scaled by `speed` (0 pauses) and capped by `max_steps`, so a stall drops its backlog
  instead of freezing the game. It keeps a smoothed and a peak step time in milliseconds.
- `noise.value_noise` / `noise.fbm` are seeded by a `numpy.random.Generator`, so the same
  seed produces the same world everywhere.
- `grid.distance_field` is a BFS flow field: build it once per destination and walkers
  follow `grid.downhill`. `majority_smooth`, `neighbours_any` and `disc` help with
  procedural tile maps.
- `grid.IncrementalDistanceField` computes the same field a bounded number of tiles per
  `advance(budget)` call, for large maps where a full BFS would stall a frame.
- `Modifiers` sums `(stat, amount)` effects into multipliers (`m`) and flat additions
  (`a`, stats ending in `_add`), plus unlock flags.
- `PhaseCycle` runs repeating phases (seasons, day and night) whose numeric properties
  blend into the next phase near the end of each one.

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

- `World2D.remove_entity` is deferred and only drops the entity from the world's table. Use
  `entity.alive = False` for a full teardown (chunks, components).
- Spatial audio is stereo panning, not HRTF.
