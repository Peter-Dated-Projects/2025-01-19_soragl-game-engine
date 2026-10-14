import pygame
from soragl import state
from soragl.system import ecs

# ============================================================================= #
# Mouse Lock Component
# ============================================================================= #


class MouseLockComponent(ecs.Component):
    """
    Component that handles mouse locking/unlocking behavior.

    Features:
    - Lock/unlock mouse cursor
    - ESC key to unlock
    - Mouse click to re-lock
    - Provides mouse delta when locked
    """

    def __init__(
        self,
        start_locked: bool = True,
        unlock_key: int = pygame.K_ESCAPE,
    ):
        """
        Args:
            start_locked: Whether to start with mouse locked
            unlock_key: Key to unlock the mouse (default: ESC)
        """
        super().__init__()

        self._is_locked = False
        self._unlock_key = unlock_key
        self._unlock_key_was_pressed = False
        self._start_locked = start_locked

        # Mouse delta tracking
        self._mouse_delta = pygame.Vector2(0, 0)
        self._center_x = state.config.window_width // 2
        self._center_y = state.config.window_height // 2

    def __post_init__(self):
        """Initialize mouse lock state after component is added to entity."""
        if self._start_locked:
            self.lock()

    # ------------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------------ #

    def lock(self):
        """Lock the mouse cursor to the window."""
        if not self._is_locked:
            pygame.mouse.set_visible(False)
            pygame.event.set_grab(True)
            self._is_locked = True
            # Center the mouse
            pygame.mouse.set_pos(self._center_x, self._center_y)
            # Reset delta
            self._mouse_delta.xy = (0, 0)

    def unlock(self):
        """Unlock the mouse cursor."""
        if self._is_locked:
            pygame.mouse.set_visible(True)
            pygame.event.set_grab(False)
            self._is_locked = False
            # Reset delta
            self._mouse_delta.xy = (0, 0)

    def toggle(self):
        """Toggle mouse lock state."""
        if self._is_locked:
            self.unlock()
        else:
            self.lock()

    @property
    def is_locked(self) -> bool:
        """Check if mouse is currently locked."""
        return self._is_locked

    @property
    def mouse_delta(self) -> pygame.Vector2:
        """Get the mouse movement delta since last frame (only when locked)."""
        return self._mouse_delta

    # ------------------------------------------------------------------------ #
    # Update Logic
    # ------------------------------------------------------------------------ #

    def update(self):
        """
        Update mouse lock state and calculate mouse delta.

        Handles:
        - ESC key to unlock
        - Mouse click to re-lock
        - Mouse delta calculation when locked
        """
        # Handle unlock key (ESC by default)
        unlock_pressed = state.input_handler.get_keyboard_pressed(self._unlock_key)
        if unlock_pressed and not self._unlock_key_was_pressed:
            if self._is_locked:
                self.unlock()
        self._unlock_key_was_pressed = unlock_pressed

        # Handle mouse click to re-lock
        if not self._is_locked:
            mouse_buttons = pygame.mouse.get_pressed()
            if any(mouse_buttons):  # Any mouse button clicked
                self.lock()

        # Calculate mouse delta when locked
        if self._is_locked:
            mouse_pos = pygame.mouse.get_pos()

            # Calculate delta from center
            self._mouse_delta.x = mouse_pos[0] - self._center_x
            self._mouse_delta.y = mouse_pos[1] - self._center_y

            # Re-center mouse if it moved
            if self._mouse_delta.x != 0 or self._mouse_delta.y != 0:
                pygame.mouse.set_pos(self._center_x, self._center_y)
        else:
            # No delta when unlocked
            self._mouse_delta.xy = (0, 0)

    def debug(self):
        """Debug method required by Component base class."""
        pass
