import glm


from soragl import state

from soragl.physics import entity

# ======================================================================== #
# Camera
# ======================================================================== #


class BaseCamera(entity.Entity):
    def __init__(self, render_distance: int):
        super().__init__()

        self._render_distance = render_distance


# ======================================================================== #
# 2D Camera
# ======================================================================== #


class Camera2D(BaseCamera):
    def __init__(self, render_distance: int):
        super().__init__(render_distance)

        self._chunk_pos = (0, 0)

    # ------------------------------------------------------------------------ #
    # logic
    # ------------------------------------------------------------------------ #

    def generate_visible_chunks(self):
        self._chunk_pos = (
            self._position.x // state.config.default_chunk_pixel_width,
            self._position.y // state.config.default_chunk_pixel_height,
        )
        # generate visible chunks
        for x in range(-self._render_distance, self._render_distance):
            for y in range(-self._render_distance, self._render_distance):
                yield (x + self._chunk_pos[0], y + self._chunk_pos[1])


# ======================================================================== #
# 3D Camera
# ======================================================================== #


class Camera3D(BaseCamera):
    def __init__(
        self,
        render_distance: int,
        fov: float = 45.0,
        near: float = 0.1,
        far: float = 1000.0,
        position: glm.vec3 = glm.vec3(0, 0, 0),
        forward: glm.vec3 = glm.vec3(0, 0, 1),
        up: glm.vec3 = glm.vec3(0, 1, 0),
        orthogonal: bool = False,
        width: int = state.config.window_width,
        height: int = state.config.window_height,
        orientation_lock: bool = False,
        orientation_lock_vec: glm.vec3 = glm.vec3(0, 1, 0),
    ):
        """
        A camera class that maintains an orthonormal triad of (forward, right, up).
        forward: which direction the camera is looking
        up: what the camera considers 'vertical'
        position: where the camera is located
        """
        super().__init__(render_distance)

        self._fov = fov
        self._near = near
        self._far = far

        self._position = position
        self._forward = forward
        self._up = up  # We'll keep a true up vector, not derived from rotation.
        self._orthogonal = orthogonal
        self._width = width
        self._height = height

        # orientation lock
        self._lock_orientation = orientation_lock
        self._lock_vec = glm.normalize(orientation_lock_vec)

        # Prepare projection
        self._projection = None
        self._recalculate_projection()

        # Calculate the initial view matrix
        self._view = glm.mat4(1.0)
        self._recalculate_view()

    # ------------------------------------------------------------------------ #
    # Internal Utility
    # ------------------------------------------------------------------------ #
    def _recalculate_view(self):
        """
        Force forward and up to form an orthonormal basis.
        Then construct a view matrix via lookAt.
        """
        # 1) Normalize forward
        if glm.length(self._forward) < 1e-8:
            # Fallback: if forward is degenerate, pick a default
            self._forward = glm.vec3(0, 0, 1)
        else:
            self._forward = glm.normalize(self._forward)

        # 2) Remove any component of up that lies along forward, then normalize
        #    This ensures up is orthogonal to forward.
        if not self._lock_orientation:
            proj_coeff = glm.dot(self._up, self._forward)
            self._up = self._up - proj_coeff * self._forward

            if glm.length(self._up) < 1e-8:
                # Fallback: if up is near parallel to forward, pick a default
                # e.g. if forward is (0,0,1), we can pick up = (0,1,0)
                # but if that's also parallel, use something else.
                fallback = glm.vec3(0, 1, 0)
                if abs(glm.dot(self._forward, fallback)) > 0.9999:
                    fallback = glm.vec3(1, 0, 0)
                self._up = fallback

            self._up = glm.normalize(self._up)
        else:
            self._up = self._lock_vec

        # 3) Compute the right vector (cross product)
        #    For a standard right-handed system, do forward x up => right
        right = glm.cross(self._forward, self._up)
        if glm.length(right) < 1e-8:
            # Another edge case fallback if forward ~ up
            right = glm.vec3(1, 0, 0)

        # 4) Recompute up to ensure perfect orthonormal triad
        #    up = right x forward
        self._up = glm.normalize(glm.cross(right, self._forward))

        # Finally, build the view matrix
        target = self._position + self._forward
        self._view = glm.lookAt(self._position, target, self._up)

    def _recalculate_projection(self):
        """
        Update the camera's projection matrix (orthographic or perspective).
        """
        if self._orthogonal:
            # Orthographic
            self._projection = glm.ortho(
                -self._width / 2.0,
                self._width / 2.0,
                -self._height / 2.0,
                self._height / 2.0,
                self._near,
                self._far,
            )
        else:
            # Perspective
            aspect_ratio = self._width / float(self._height)
            self._projection = glm.perspective(
                glm.radians(self._fov), aspect_ratio, self._near, self._far
            )

    # ------------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------------ #
    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value: glm.vec3):
        self._position = value
        self._recalculate_view()

    @property
    def forward(self):
        """
        The camera's forward vector in world space.
        """
        return self._forward

    @forward.setter
    def forward(self, value: glm.vec3):
        self._forward = value
        self._recalculate_view()

    @property
    def up(self):
        """
        The camera's notion of 'vertical'.
        """
        return self._up

    @up.setter
    def up(self, value: glm.vec3):
        self._up = value
        self._recalculate_view()

    @property
    def target(self):
        """
        A convenient property: read = position + forward,
        write => sets forward to point from position to the new value.
        """
        return self._position + self._forward

    @target.setter
    def target(self, value: glm.vec3):
        self._forward = value - self._position
        self._recalculate_view()

    @property
    def view(self):
        """
        The final view matrix.
        """
        return self._view

    @property
    def projection(self):
        """
        The final projection matrix.
        """
        return self._projection

    @property
    def near(self):
        return self._near

    @near.setter
    def near(self, value: float):
        self._near = value
        self._recalculate_projection()

    @property
    def far(self):
        return self._far

    @far.setter
    def far(self, value: float):
        self._far = value
        self._recalculate_projection()

    @property
    def fov(self):
        return self._fov

    @fov.setter
    def fov(self, value: float):
        self._fov = value
        self._recalculate_projection()

    @property
    def orthogonal(self):
        return self._orthogonal

    @orthogonal.setter
    def orthogonal(self, value: bool):
        self._orthogonal = value
        self._recalculate_projection()

    @property
    def orientation_lock(self):
        return self._lock_orientation

    @orientation_lock.setter
    def orientation_lock(self, value: bool):
        self._lock_orientation = value

    @property
    def orientation_lock_vec(self):
        return self._lock_vec

    @orientation_lock_vec.setter
    def orientation_lock_vec(self, value: glm.vec3):
        self._lock_vec = value


# ======================================================================== #
# Camera Utils
# ======================================================================== #


def calculate_forward_from_target(position: glm.vec3, target: glm.vec3):
    return target - position
