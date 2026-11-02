import logging
import math
import os
from pathlib import Path

from pyglm import glm
import pygame
import numpy as np

import soragl
from soragl import state
from soragl.config import EngineConfig

from soragl.ecs import c_task
from soragl.ecs import c_sprite
from soragl.ecs import c_particle_handler

from soragl.system import animation
from soragl.system import log

from soragl.graphics import buffer
from soragl.graphics import shader
from soragl.graphics import camera
from soragl.graphics import texture
from soragl.graphics import sprite_sheet
from soragl.graphics import constants as gfx_consts

from soragl.graphics.ecs import c_mesh
from soragl.graphics.ecs import c_camera_controller
from soragl.graphics.ecs import c_mouse_lock


from soragl.physics import entity
from soragl.physics import interact

from soragl.physics.ecs import c_aabb
from soragl.physics.ecs import c_sora_box2d

import cube_entity

# ------------------------------------------------------------------------ #

# asset paths in this demo (and inside its json files) are relative to this folder
os.chdir(Path(__file__).parent)

log.configure(logging.INFO)

soragl.init(
    EngineConfig(
        window_width=1280,
        window_height=720,
        window_title="Paint Gun Rogue-Lite",
        window_fps=60,
        background_color=(255, 224, 169),
        framebuffer_width=500,
        framebuffer_height=500,
        debug_mode=True,
    )
)

# ======================================================================== #
# loading resources
# ======================================================================== #


# ------------------------------------------------------------------------ #
# testing zone

if True:
    # test - loading images
    image1 = state.resource_manager.load("assets/entities/archer/idle.png")
    image2 = state.resource_manager.load("assets/entities/archer/walk.png")

    # test - creating spritesheet
    s1 = sprite_sheet.SpriteSheet.from_image(
        "assets/entities/archer/idle.png",
        sprite_sheet.SpriteSheet.create_meta(
            source="assets/entities/archer/idle.png",
            uniform=True,
            uwidth=100,
            uheight=100,
        ),
    )
    s2 = sprite_sheet.SpriteSheet.from_image_array(
        [
            c_sprite.SpriteComponent(image2, "assets/entities/archer/walk.png"),
            c_sprite.SpriteComponent(image2, "assets/entities/archer/walk.png"),
        ]
    )

    # test - creating entity, adding component, rendering using task component!
    e1 = state.world.add_entity(entity.Entity(name="e1"))
    e1spr = e1.add_component(
        c_sprite.SpriteComponent(filepath="assets/entities/arrow/32xarrow.png")
    )
    e1spr._extra["offset"] = pygame.Vector2(50, 50)
    e1.add_component(c_sprite.SpriteRendererComponent(e1spr))
    e1._position = pygame.Vector2(100, 100)
    e1.zlayer = 2

    def draw_image():
        # ctx.W_FRAMEBUFFER.blit(image1, (100, 100))
        # ctx.W_FRAMEBUFFER.blit(s1._image, (200, 200))

        # # render sprites from spritesheet with spriterendereraspect
        # for i in range(len(s1._sprites)):
        #     ctx.W_FRAMEBUFFER.blit(s1._sprites[i].get_image(), (300 + 30, 300 + 100 * i))

        # # render s2
        # for i in range(len(s2._sprites)):
        #     ctx.W_FRAMEBUFFER.blit(s2._sprites[i].get_image(), (300, 300 + 100 * i))

        # print(e1._components)

        state.signal_handler.emit_signal(
            "draw_signal",
            (
                int(127 * math.sin(state.run_time) + 127),
                int(127 * math.cos(state.run_time) + 127),
                int(127 * math.sin(state.run_time + state.run_time * 0.5) + 127),
            ),
        )

    def draw_signal(color):
        pygame.draw.rect(state.framebuffer_surface, color, (100, 200, 100, 100))

    # test - add component using entity built in function
    t1 = e1.add_component(c_task.TaskComponent("draw_image", draw_image))

    # test - signal handler
    state.signal_handler.register_signal("draw_signal", [tuple])
    state.signal_handler.register_receiver("draw_signal", draw_signal)

    # test - particle handler
    e3 = state.world.add_entity(entity.Entity(name="e3"))
    e3.zlayer = -1
    ph1 = e3.add_component(
        c_particle_handler.ParticleHandlerComponent(updates_per_second=10)
    )
    e3._position += pygame.Vector2(300, 100)

    # test -- load animation
    reg1 = animation.Animation.from_json(
        "assets/entities/archer/walk_animation.json"
    ).get_register()
    reg2 = animation.Animation.from_json(
        "assets/entities/archer/idle_animation.json"
    ).get_register()
    reg3 = animation.Animation.from_array(
        [
            c_sprite.SpriteComponent(image2, "assets/entities/archer/walk.png"),
            c_sprite.SpriteComponent(image2, "assets/entities/archer/walk.png"),
        ]
    ).get_register()
    reg4 = animation.Animation.from_array(s1._sprites).get_register()

    e4 = state.world.add_entity(entity.Entity())
    e4.add_component(
        animation.AnimatedSpriteComponent(
            animation.Animation.from_json("assets/entities/archer/walk_animation.json")
        )
    )
    e4.add_component(c_sprite.SpriteComponent())
    e4.add_component(c_sprite.SpriteRendererComponent())
    e4._position += pygame.Vector2(300, 100)

    def draw_animation():
        reg1.update()
        state.framebuffer_surface.blit(
            reg1.get_current_sprite().get_image(), (100, 100)
        )

    e3.add_component(c_task.TaskComponent("draw_animation", draw_animation))


# test - physics
if True:
    eleft = state.world.add_entity(entity.Entity())
    eright = state.world.add_entity(entity.Entity())

    eleft.add_component(
        c_sora_box2d.SoraBox2DColliderComponent(20, 20, collision_conserve_coef=1.0)
    )
    eleft.add_component(c_sprite.SpriteComponent())
    eleft.add_component(
        animation.AnimatedSpriteComponent(
            animation.Animation.from_json("assets/entities/archer/idle_animation.json")
        )
    )
    eleft.add_component(c_sprite.SpriteRendererComponent())
    eleft.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001)
    )._velocity.x = 40

    eright.add_component(
        c_sora_box2d.SoraBox2DColliderComponent(20, 20, collision_conserve_coef=1.2)
    )
    eright.add_component(c_sprite.SpriteComponent())
    eright.add_component(
        animation.AnimatedSpriteComponent(
            animation.Animation.from_json("assets/entities/archer/walk_animation.json")
        )
    )
    eright.add_component(c_sprite.SpriteRendererComponent())
    eright.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001)
    )._velocity.xy = (-40, 5)

    edown = state.world.add_entity(entity.Entity())
    edown.add_component(
        c_sora_box2d.SoraBox2DColliderComponent(20, 20, collision_conserve_coef=0.9)
    )
    edown.add_component(c_sprite.SpriteComponent())
    edown.add_component(
        animation.AnimatedSpriteComponent(
            animation.Animation.from_json("assets/entities/archer/walk_animation.json")
        )
    )
    edown.add_component(c_sprite.SpriteRendererComponent())
    edown.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001)
    )._velocity.y = -50

    some_random_block = state.world.add_entity(entity.Entity())
    some_random_block.add_component(c_aabb.AABBColliderComponent(40, 40))
    some_random_block.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001, static=True)
    )
    some_random_block.add_component(c_sprite.SpriteComponent())
    some_random_block.add_component(
        animation.AnimatedSpriteComponent(
            animation.Animation.from_json("assets/entities/archer/walk_animation.json")
        )
    )
    some_random_block.add_component(c_sprite.SpriteRendererComponent())

# ------------------------------------------------------------------------ #
# walls
if True:
    left_wall = state.world.add_entity(entity.Entity(name="left-wall"))
    left_wall.add_component(c_aabb.AABBColliderComponent(20, 300))
    left_wall.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001, static=True)
    )
    left_wall.add_component(c_sprite.SpriteComponent())
    left_wall.add_component(c_sprite.SpriteRendererComponent())
    left_wall._position += pygame.Vector2(100, 200)

    right_wall = state.world.add_entity(entity.Entity())
    right_wall.add_component(c_aabb.AABBColliderComponent(20, 300))
    right_wall.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001, static=True)
    )
    right_wall.add_component(c_sprite.SpriteComponent())
    right_wall.add_component(c_sprite.SpriteRendererComponent())
    right_wall._position += pygame.Vector2(500, 200)

    top_wall = state.world.add_entity(entity.Entity())
    top_wall.add_component(c_aabb.AABBColliderComponent(600, 20))
    top_wall.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001, static=True)
    )
    top_wall.add_component(c_sprite.SpriteComponent())
    top_wall.add_component(c_sprite.SpriteRendererComponent())
    top_wall._position += pygame.Vector2(200, 100)

    bottom_wall = state.world.add_entity(entity.Entity(name="bottom-wall"))
    bottom_wall.add_component(c_aabb.AABBColliderComponent(600, 20))
    bottom_wall.add_component(
        interact.InteractionFieldComponent(collision_mask=0b00000001, static=True)
    )
    bottom_wall.add_component(c_sprite.SpriteComponent())
    bottom_wall.add_component(c_sprite.SpriteRendererComponent())
    bottom_wall._position += pygame.Vector2(200, 350)

# ------------------------------------------------------------------------ #
# entities

some_random_block._position += pygame.Vector2(300, 200)
eleft._position += pygame.Vector2(240, 200)
eright._position += pygame.Vector2(450, 200)
edown._position += pygame.Vector2(300, 300)


# some_random_block.alive = False
# eleft.alive = False
# edown.alive = False
# eright.alive = False
# left_wall.alive = False
# right_wall.alive = False
# top_wall.alive = False
# bottom_wall.alive = False

e1.alive = False
e3.alive = False
e4.alive = False


def kill_static():
    if state.input_handler.get_keyboard_pressed(pygame.K_SPACE):
        print(f"{state.run_time:.5f} | KILLING STATIC")
        some_random_block.alive = False
        print(f"{state.run_time:.5f} | FINISHED SENDING SIGNAL")


t2 = e1.add_component(c_task.TaskComponent("kill_static", kill_static))

# opengl testing
_campos = glm.vec3(0, 8, 0)
_3dcam = state.world.add_entity(
    camera.Camera3D(
        5,
        fov=45,
        near=0.1,
        far=1000,
        position=_campos,
        forward=camera.calculate_forward_from_target(_campos, glm.vec3(0, 0, 0)),
        orientation_lock=True,
        orientation_lock_vec=glm.vec3(0, 1, 0),
    )
)
complete_vert_data = buffer.GLBufferObject(
    np.hstack(
        [
            gfx_consts.Cube.get_cube_vert(),
            gfx_consts.Cube.get_cube_tex(),
            gfx_consts.generate_vertex_data(
                [(0.0,), (1.0,)],
                [
                    # front face
                    (0, 0, 0),
                    (0, 0, 0),
                    # back face
                    (0, 0, 0),
                    (0, 0, 0),
                    # left face
                    (1, 1, 1),
                    (1, 1, 1),
                    # right face
                    (1, 1, 1),
                    (1, 1, 1),
                    # top face
                    (0, 0, 0),
                    (0, 0, 0),
                    # bottom face
                    (0, 0, 0),
                    (0, 0, 0),
                ],
            ),
        ]
    )
)
shader_program = shader.ShaderProgram(
    vertex_shader=shader.Shader.builtin("default_vertex"),
    fragment_shader=shader.Shader.builtin("default_fragment"),
)


# create 100 random entities spinning and slightly moving up and down


# Create shared VAO once for all cubes (optimization to reduce GPU resource usage)
shared_cube_vao = buffer.VAOObject(
    shader_program,
    [
        (
            complete_vert_data(),
            "3f 2f 1f",
            "in_position",
            "in_texcoords",
            "in_tex",
        )
    ],
)

for i in range(100):
    state.world.add_entity(
        cube_entity.CubeEntity(
            name=f"cube-{i}",
            shader_program=shader_program,
            complete_vert_data=complete_vert_data,
            shared_vao=shared_cube_vao,
        )
    )


render_entity = state.world.add_entity(entity.Entity(name="star!"))
rman = render_entity.add_component(
    c_mesh.MeshComponent(
        buffer.RenderingManifold(
            vao=buffer.VAOObject(
                shader_program,
                [
                    (
                        complete_vert_data(),
                        "3f 2f 1f",
                        "in_position",
                        "in_texcoords",
                        "in_tex",
                    )
                ],
            ),
        )
    )
)

rman().set_texture(0, texture.Texture(raw_image=state.framebuffer_surface))

# Create persistent texture for framebuffer updates (prevents memory leak)
# This texture is reused every frame instead of creating new textures
framebuffer_texture_slot0 = texture.Texture.create_non_file_texture(
    width=state.config.framebuffer_width,
    height=state.config.framebuffer_height,
    channels=4,
    color_buffer=True,
)

m_model_rman = glm.mat4()

rman().write_uniform("m_model", m_model_rman)
rman().write_uniform("m_proj", _3dcam._projection)
rman().write_uniform("m_view", _3dcam._view)


def sub_task1():
    global m_model_rman, rman, framebuffer_texture_slot0
    result = glm.scale(m_model_rman, glm.vec3(0.2))
    result = glm.translate(result, glm.vec3(0, math.sin(state.run_time) * 20, 0))
    result = glm.rotate(result, state.run_time, glm.vec3(0, 1, 0))

    rman().write_uniform("m_model", result)
    # Update texture data instead of creating new texture (prevents memory leak)
    framebuffer_texture_slot0.update_from_surface(state.framebuffer_surface)
    rman().set_texture(0, framebuffer_texture_slot0)
    rman().set_texture(1, texture.Texture.get_texture("assets/snowman.jpg"))


render_entity.add_component(c_task.TaskComponent("sub_task", sub_task1), priority=1)


# render entity 2

render_entity2 = state.world.add_entity(entity.Entity(name="orbit"))
rman2 = render_entity2.add_component(
    c_mesh.MeshComponent(
        buffer.RenderingManifold(
            vao=buffer.VAOObject(
                shader_program,
                [
                    (
                        complete_vert_data(),
                        "3f 2f 1f",
                        "in_position",
                        "in_texcoords",
                        "in_tex",
                    )
                ],
            ),
        )
    )
)

# no need to reset texture at location = 0 (because same shader + already set)

m_model_rman2 = glm.mat4()
m_model_rman2 = glm.translate(m_model_rman2, glm.vec3(0, 0, 0))

# no need to write projection, view, and model matrices (because same shader + already set)


def sub_task2():
    global m_model_rman2, rman2
    result = glm.translate(
        m_model_rman2,
        glm.vec3(
            math.sin(state.run_time) * 1.5,
            0,
            math.cos(state.run_time) * 1.5,
        ),
    )
    result = glm.rotate(result, -state.run_time, glm.vec3(0, 1, 0))
    result = glm.scale(result, glm.vec3(0.1))

    rman2().write_uniform("m_model", result)
    rman2().set_texture(1, texture.Texture.get_texture("assets/cult.jpg"))


render_entity2.add_component(c_task.TaskComponent("sub_task", sub_task2), priority=1)


# framebuffer background rendering
ortho_cam = camera.Camera3D(
    5,
    fov=45,
    near=0.1,
    far=1000,
    position=glm.vec3(0, 0, -3),
    forward=-glm.normalize(glm.vec3(0, 0, -3)),
    orthogonal=True,
)

complete_vert_data2 = buffer.GLBufferObject(
    np.hstack(
        [
            gfx_consts.Plane.get_plane_vert(),
            gfx_consts.Plane.get_plane_tex(),
            gfx_consts.generate_vertex_data(
                [(0.0,)],
                [
                    (0, 0, 0),
                    (0, 0, 0),
                ],
            ),
        ]
    )
)
shader_program2 = shader.ShaderProgram(
    vertex_shader=shader.Shader.builtin("default_vertex"),
    fragment_shader=shader.Shader.builtin("default_fragment"),
)

render_entity3 = state.world.add_entity(entity.Entity(zlayer=1, name="fb"))
rman3 = render_entity3.add_component(
    c_mesh.MeshComponent(
        buffer.RenderingManifold(
            vao=buffer.VAOObject(
                shader_program2,
                [
                    (
                        complete_vert_data2(),
                        "3f 2f 1f",
                        "in_position",
                        "in_texcoords",
                        "in_tex",
                    )
                ],
            ),
        )
    )
)

rman3().set_texture(0, texture.Texture(raw_image=state.framebuffer_surface))

# Create persistent texture for framebuffer updates (prevents memory leak)
# This texture is reused every frame instead of creating new textures
framebuffer_texture_slot0_copy = texture.Texture.create_non_file_texture(
    width=state.config.framebuffer_width,
    height=state.config.framebuffer_height,
    channels=4,
    color_buffer=True,
)

m_model_rman3 = glm.mat4()
m_model_rman3 = glm.rotate(m_model_rman3, math.pi / 2, glm.vec3(1, 0, 0))
m_model_rman3 = glm.translate(m_model_rman3, glm.vec3(0, 0, 20))
m_model_rman3 = glm.scale(m_model_rman3, glm.vec3(10))

rman3().write_uniform("m_model", m_model_rman3)
# rman3().write_uniform("m_proj", ortho_cam._projection)
# rman3().write_uniform("m_view", ortho_cam._view)
rman3().write_uniform("m_proj", _3dcam._projection)
rman3().write_uniform("m_view", _3dcam._view)


def sub_task3():
    global rman3, m_model_rman3, framebuffer_texture_slot0_copy

    # Update texture data instead of creating new texture (prevents memory leak)
    framebuffer_texture_slot0_copy.update_from_surface(state.framebuffer_surface)
    rman3().set_texture(0, framebuffer_texture_slot0_copy)
    # rman3().set_texture(0, state.gl_framebuffer.get_color_attachments()[0])


render_entity3.add_component(c_task.TaskComponent("sub_task", sub_task3))


# # load the bugatti model and render it
# cat_shader = shader.ShaderProgram(
#     vertex_shader=shader.Shader.builtin("model_vertex"),
#     fragment_shader=shader.Shader.builtin("model_fragment"),
# )
# c_name, c_material = pywavefront.Wavefront(
#     "assets/models/cat/20430_Cat_v1_NEW.obj", parse=True
# ).materials.popitem()
# c_vdata = buffer.GLBufferObject(np.array(c_material.vertices, dtype="float32"))
# c_tex = texture.Texture.get_texture(
#     "assets/models/cat/20430_cat_diff_v1.jpg", yflip=True
# )

# cat_entity = state.world.add_entity(entity.Entity(name="cat model"))

# cat_model_mesh = cat_entity.add_component(
#     c_mesh.MeshComponent(
#         buffer.RenderingManifold(
#             vao=buffer.VAOObject(
#                 cat_shader,
#                 [
#                     (
#                         c_vdata(),
#                         "2f 3f 3f",
#                         "in_texcoords",
#                         "in_normal",
#                         "in_position",
#                     )
#                 ],
#             ),
#             tex_count=1,
#         )
#     )
# )

# model = glm.mat4()
# model = glm.rotate(model, -math.pi / 2, glm.vec3(1, 0, 0))
# model = glm.scale(model, glm.vec3(0.3))

# cat_model_mesh().write_uniform("m_model", model)
# cat_model_mesh().write_uniform("m_proj", _3dcam._projection)
# cat_model_mesh().write_uniform("m_view", _3dcam._view)
# cat_model_mesh().set_texture(0, c_tex)


# Add mouse lock component (must be added before camera controller)
mouse_lock = _3dcam.add_component(c_mouse_lock.MouseLockComponent(start_locked=True))

# Add camera controller for keyboard input handling
camera_controller = _3dcam.add_component(
    c_camera_controller.CameraController3D(move_speed=10.0, rotation_speed=3.0)
)


# Update shader view matrices and print debug info
def camera_shader_update():
    global _3dcam, shader_program, shader_program2
    # update data in shader
    shader_program["m_view"].write(_3dcam._view)
    shader_program2["m_view"].write(_3dcam._view)

    # print out fps
    print(f"{state.run_time:.5f} | FPS: {state.clock.get_fps()}")
    print(f"{state.run_time:.5f} | CAMERA POS: {_3dcam.position}")
    print(f"{state.run_time:.5f} | CAMERA UP: {_3dcam.up}")


_3dcam.add_component(c_task.TaskComponent("camera_shader_update", camera_shader_update))

# ======================================================================== #
# run game
# ======================================================================== #


soragl.run()
