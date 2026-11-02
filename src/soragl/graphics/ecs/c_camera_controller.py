from pyglm import glm
import pygame

from soragl.system import ecs
from soragl import state

# ============================================================================= #
# Camera Controller
# ============================================================================= #


class CameraController3D(ecs.Component):
    def __init__(
        self,
        move_speed: float = 5.0,
        rotation_speed: float = 2.0,
        mouse_sensitivity: float = 0.002,
        enable_mouse_look: bool = True,
        pitch_limit: float = 89.0,  # Degrees from horizontal
    ):
        super().__init__()

        self._camera = None
        self._move_speed = move_speed
        self._rotation_speed = rotation_speed
        self._mouse_sensitivity = mouse_sensitivity
        self._enable_mouse_look = enable_mouse_look
        self._pitch_limit = pitch_limit

        # Track pitch and yaw separately to avoid gimbal lock
        self._yaw = 0.0  # Rotation around up axis (left/right)
        self._pitch = 0.0  # Rotation around right axis (up/down)

        # Reference to mouse lock component (will be set in __post_init__)
        self._mouse_lock = None

    def __post_init__(self):
        self._camera = self._entity
        # Calculate initial pitch and yaw from camera's forward vector
        self._calculate_initial_angles()
        # Get reference to mouse lock component
        from soragl.graphics.ecs import c_mouse_lock

        self._mouse_lock = self._entity.get_component(c_mouse_lock.MouseLockComponent)

    def _calculate_initial_angles(self):
        """Calculate initial pitch and yaw from the camera's forward vector."""
        forward = glm.normalize(self._camera.forward)

        # Yaw: angle in XZ plane
        self._yaw = glm.atan(forward.x, forward.z)

        # Pitch: angle from horizontal plane
        horizontal_length = glm.sqrt(forward.x * forward.x + forward.z * forward.z)
        self._pitch = glm.atan(forward.y, horizontal_length)

    def _update_camera_forward(self):
        """Update camera forward vector from pitch and yaw angles."""
        # Clamp pitch to prevent gimbal lock
        max_pitch = glm.radians(self._pitch_limit)
        self._pitch = glm.clamp(self._pitch, -max_pitch, max_pitch)

        # Calculate forward vector from pitch and yaw
        forward = glm.vec3(
            glm.cos(self._pitch) * glm.sin(self._yaw),
            glm.sin(self._pitch),
            glm.cos(self._pitch) * glm.cos(self._yaw),
        )

        self._camera.forward = glm.normalize(forward)

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def change_position(self, direction: glm.vec3):
        self._camera._position += direction

    def change_rotation(self, rotation: glm.vec3):
        self._camera.up = rotation

    def change_perspective(self, fov: float, near: float = 0, far: float = 0):
        self._camera.fov += fov
        self._camera.near += near
        self._camera.far += far

    def change_forward(self, forward: glm.vec3):
        self._camera.forward += forward

    # ------------------------------------------------------------------------ #
    # setters
    # ------------------------------------------------------------------------ #

    # position
    def set_position(self, position: glm.vec3):
        self._camera.position = position

    # rotation
    def set_rotation(self, rotation: glm.vec3):
        self._camera.rotation = rotation

    def set_x_rotation(self, rotation: float):
        self._camera.rotation.x = rotation

    def set_y_rotation(self, rotation: float):
        self._camera.rotation.y = rotation

    def set_z_rotation(self, rotation: float):
        self._camera.rotation.z = rotation

    # projection setters
    def set_perspective(self, fov: float, near: float = 0, far: float = 0):
        self._camera.fov = fov
        self._camera.near = near
        self._camera.far = far
        self._camera.calculate_projection()

    def set_fov(self, fov: float):
        self._camera.fov = fov
        self._camera.calculate_projection()

    def set_near(self, near: float):
        self._camera.near = near
        self._camera.calculate_projection()

    def set_far(self, far: float):
        self._camera.far = far
        self._camera.calculate_projection()

    def set_width(self, width: int):
        self._camera.width = width
        self._camera.calculate_projection()

    def set_height(self, height: int):
        self._camera.height = height
        self._camera.calculate_projection()

    # targets + lookat
    def set_target(self, target: glm.vec3):
        self._camera.target = target

    def set_forward(self, forward: glm.vec3):
        self._camera.forward = forward

    # ------------------------------------------------------------------------ #
    # input handling
    # ------------------------------------------------------------------------ #

    def update(self):
        """
        Process keyboard and mouse input and update camera position/orientation.

        Controls:
        - W/S: Move forward/backward (aligned to global UP if defined)
        - A/D: Strafe left/right (aligned to global UP if defined)
        - Space: Move up
        - Shift: Move down
        - Mouse: Look around (when mouse locked)
        - Arrow keys: Rotate camera (when mouse not locked)

        Note: Mouse locking is handled by the MouseLockComponent
        """
        dt = state.clock.get_time() / 1000.0  # Delta time in seconds

        # Determine which UP vector to use
        if self._camera.orientation_lock:
            # Use global UP axis
            global_up = glm.normalize(self._camera.orientation_lock_vec)

            # Calculate forward and right vectors aligned to global UP
            # Project camera forward onto the horizontal plane (perpendicular to global UP)
            camera_forward = glm.normalize(self._camera.forward)
            forward_horizontal = (
                camera_forward - glm.dot(camera_forward, global_up) * global_up
            )

            # Handle case where camera is looking straight up/down
            if glm.length(forward_horizontal) < 0.001:
                # Use camera's right vector projected onto horizontal plane
                camera_right = glm.normalize(glm.cross(camera_forward, self._camera.up))
                forward_horizontal = glm.cross(global_up, camera_right)

            forward = glm.normalize(forward_horizontal)
            right = glm.normalize(glm.cross(forward, global_up))
            up = global_up
        else:
            # Use camera's local axes
            forward = glm.normalize(self._camera.forward)
            right = glm.normalize(glm.cross(forward, self._camera.up))
            up = glm.normalize(self._camera.up)

        # Movement (WASD + Space/Shift)
        movement = glm.vec3(0, 0, 0)

        if state.input_handler.get_keyboard_pressed(pygame.K_w):
            movement += forward * self._move_speed * dt
        if state.input_handler.get_keyboard_pressed(pygame.K_s):
            movement -= forward * self._move_speed * dt
        if state.input_handler.get_keyboard_pressed(pygame.K_a):
            movement -= right * self._move_speed * dt
        if state.input_handler.get_keyboard_pressed(pygame.K_d):
            movement += right * self._move_speed * dt
        if state.input_handler.get_keyboard_pressed(pygame.K_SPACE):
            movement += up * self._move_speed * dt
        if state.input_handler.get_keyboard_pressed(
            pygame.K_LSHIFT
        ) or state.input_handler.get_keyboard_pressed(pygame.K_RSHIFT):
            movement -= up * self._move_speed * dt

        if glm.length(movement) > 0:
            self._camera.position += movement

        # Mouse look (when locked) - using pitch/yaw system
        if self._enable_mouse_look and self._mouse_lock and self._mouse_lock.is_locked:
            # Get mouse delta from the mouse lock component
            mouse_delta = self._mouse_lock.mouse_delta

            if mouse_delta.x != 0 or mouse_delta.y != 0:
                # Update yaw (horizontal) and pitch (vertical) angles
                self._yaw -= mouse_delta.x * self._mouse_sensitivity
                self._pitch -= mouse_delta.y * self._mouse_sensitivity

                # Update camera forward vector from angles
                self._update_camera_forward()

        # Rotation with arrow keys (when mouse not locked)
        elif not self._mouse_lock or not self._mouse_lock.is_locked:
            if state.input_handler.get_keyboard_pressed(pygame.K_LEFT):
                self._yaw += self._rotation_speed * dt
                self._update_camera_forward()

            if state.input_handler.get_keyboard_pressed(pygame.K_RIGHT):
                self._yaw -= self._rotation_speed * dt
                self._update_camera_forward()

            if state.input_handler.get_keyboard_pressed(pygame.K_UP):
                self._pitch += self._rotation_speed * dt
                self._update_camera_forward()

            if state.input_handler.get_keyboard_pressed(pygame.K_DOWN):
                self._pitch -= self._rotation_speed * dt
                self._update_camera_forward()

    def debug(self):
        """Debug method required by Component base class."""
        pass
