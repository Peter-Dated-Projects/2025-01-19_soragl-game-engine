import pygame
from typing import Dict, Tuple, Optional, List

# ======================================================================== #
# Input handler
# ======================================================================== #


class InputHandler:

    # Current state (pygame sequences)
    KEYBOARD_INPUTS = ()
    MOUSE_INPUTS = ()

    # Previous state for tracking changes
    _prev_keyboard_inputs = ()
    _prev_mouse_inputs = ()

    # Mouse tracking
    _mouse_position = (0, 0)
    _prev_mouse_position = (0, 0)
    _mouse_scroll = (0, 0)

    # Text input buffer
    _text_input_buffer: List[str] = []

    # Input mapping system
    _action_mappings: Dict[str, int] = {}

    # Gamepad/Joystick tracking
    _gamepads: Dict[int, pygame.joystick.Joystick] = {}
    _gamepad_buttons: Dict[int, Dict[int, bool]] = {}
    _prev_gamepad_buttons: Dict[int, Dict[int, bool]] = {}
    _gamepad_axes: Dict[int, Dict[int, float]] = {}

    # ------------------------------------------------------------------------ #
    # Core Update (maintains backward compatibility)
    # ------------------------------------------------------------------------ #

    @classmethod
    def update(cls):
        # Store previous state (pygame returns sequences, not dicts)
        cls._prev_keyboard_inputs = cls.KEYBOARD_INPUTS
        cls._prev_mouse_inputs = cls.MOUSE_INPUTS
        cls._prev_mouse_position = cls._mouse_position

        # Update current state
        cls.KEYBOARD_INPUTS = pygame.key.get_pressed()
        cls.MOUSE_INPUTS = pygame.mouse.get_pressed()

        # Update mouse position
        cls._mouse_position = pygame.mouse.get_pos()

        # Reset scroll (will be updated by process_event)
        cls._mouse_scroll = (0, 0)

        # Clear text input buffer
        cls._text_input_buffer.clear()

        # Update gamepad state
        cls._update_gamepads()

    @classmethod
    def process_event(cls, event: pygame.event.Event):
        """Process pygame events for advanced input tracking.
        Call this in your event loop for scroll and text input support."""
        if event.type == pygame.MOUSEWHEEL:
            cls._mouse_scroll = (event.x, event.y)
        elif event.type == pygame.TEXTINPUT:
            cls._text_input_buffer.append(event.text)
        elif event.type == pygame.JOYDEVICEADDED:
            cls._init_gamepad(event.device_index)
        elif event.type == pygame.JOYDEVICEREMOVED:
            cls._remove_gamepad(event.instance_id)

    # ------------------------------------------------------------------------ #
    # Keyboard (backward compatible + enhanced)
    # ------------------------------------------------------------------------ #

    @classmethod
    def get_keyboard_pressed(cls, key: int) -> bool:
        """Check if a key is currently held down."""
        return cls.KEYBOARD_INPUTS[key]

    @classmethod
    def get_key_down(cls, key: int) -> bool:
        """Check if a key was just pressed this frame."""
        if not cls.KEYBOARD_INPUTS or not cls._prev_keyboard_inputs:
            return False
        current = cls.KEYBOARD_INPUTS[key] if key < len(cls.KEYBOARD_INPUTS) else False
        previous = cls._prev_keyboard_inputs[key] if key < len(cls._prev_keyboard_inputs) else False
        return current and not previous

    @classmethod
    def get_key_up(cls, key: int) -> bool:
        """Check if a key was just released this frame."""
        if not cls.KEYBOARD_INPUTS or not cls._prev_keyboard_inputs:
            return False
        current = cls.KEYBOARD_INPUTS[key] if key < len(cls.KEYBOARD_INPUTS) else False
        previous = cls._prev_keyboard_inputs[key] if key < len(cls._prev_keyboard_inputs) else False
        return not current and previous

    # ------------------------------------------------------------------------ #
    # Mouse (backward compatible + enhanced)
    # ------------------------------------------------------------------------ #

    @classmethod
    def get_mouse_pressed(cls, button: int) -> bool:
        """Check if a mouse button is currently held down."""
        return cls.MOUSE_INPUTS[button]

    @classmethod
    def get_mouse_down(cls, button: int) -> bool:
        """Check if a mouse button was just pressed this frame."""
        if not cls.MOUSE_INPUTS or not cls._prev_mouse_inputs:
            return False
        current = cls.MOUSE_INPUTS[button] if button < len(cls.MOUSE_INPUTS) else False
        previous = cls._prev_mouse_inputs[button] if button < len(cls._prev_mouse_inputs) else False
        return current and not previous

    @classmethod
    def get_mouse_up(cls, button: int) -> bool:
        """Check if a mouse button was just released this frame."""
        if not cls.MOUSE_INPUTS or not cls._prev_mouse_inputs:
            return False
        current = cls.MOUSE_INPUTS[button] if button < len(cls.MOUSE_INPUTS) else False
        previous = cls._prev_mouse_inputs[button] if button < len(cls._prev_mouse_inputs) else False
        return not current and previous

    @classmethod
    def get_mouse_pos(cls) -> Tuple[int, int]:
        """Get the current mouse position (x, y)."""
        return cls._mouse_position

    @classmethod
    def get_mouse_delta(cls) -> Tuple[int, int]:
        """Get the mouse movement delta from last frame (dx, dy)."""
        dx = cls._mouse_position[0] - cls._prev_mouse_position[0]
        dy = cls._mouse_position[1] - cls._prev_mouse_position[1]
        return (dx, dy)

    @classmethod
    def get_mouse_scroll(cls) -> Tuple[int, int]:
        """Get the mouse scroll wheel delta (x, y).
        Requires calling process_event() in the event loop."""
        return cls._mouse_scroll

    # ------------------------------------------------------------------------ #
    # Text Input
    # ------------------------------------------------------------------------ #

    @classmethod
    def get_text_input(cls) -> str:
        """Get accumulated text input from this frame.
        Requires calling process_event() in the event loop."""
        return ''.join(cls._text_input_buffer)

    @classmethod
    def clear_text_buffer(cls):
        """Manually clear the text input buffer."""
        cls._text_input_buffer.clear()

    # ------------------------------------------------------------------------ #
    # Input Mapping System
    # ------------------------------------------------------------------------ #

    @classmethod
    def bind_action(cls, action_name: str, key: int):
        """Bind an action name to a keyboard key.
        Example: bind_action('jump', pygame.K_SPACE)"""
        cls._action_mappings[action_name] = key

    @classmethod
    def unbind_action(cls, action_name: str):
        """Remove an action binding."""
        if action_name in cls._action_mappings:
            del cls._action_mappings[action_name]

    @classmethod
    def get_action_key(cls, action_name: str) -> Optional[int]:
        """Get the key bound to an action."""
        return cls._action_mappings.get(action_name)

    @classmethod
    def is_action_pressed(cls, action_name: str) -> bool:
        """Check if the key bound to an action is currently held."""
        key = cls._action_mappings.get(action_name)
        if key is None:
            return False
        return cls.get_keyboard_pressed(key)

    @classmethod
    def is_action_just_pressed(cls, action_name: str) -> bool:
        """Check if the key bound to an action was just pressed."""
        key = cls._action_mappings.get(action_name)
        if key is None:
            return False
        return cls.get_key_down(key)

    @classmethod
    def is_action_just_released(cls, action_name: str) -> bool:
        """Check if the key bound to an action was just released."""
        key = cls._action_mappings.get(action_name)
        if key is None:
            return False
        return cls.get_key_up(key)

    # ------------------------------------------------------------------------ #
    # Gamepad/Joystick Support
    # ------------------------------------------------------------------------ #

    @classmethod
    def _init_gamepad(cls, device_index: int):
        """Initialize a gamepad at the given device index."""
        try:
            gamepad = pygame.joystick.Joystick(device_index)
            gamepad.init()
            instance_id = gamepad.get_instance_id()
            cls._gamepads[instance_id] = gamepad
            cls._gamepad_buttons[instance_id] = {}
            cls._prev_gamepad_buttons[instance_id] = {}
            cls._gamepad_axes[instance_id] = {}
            print(f"Gamepad connected: {gamepad.get_name()} (ID: {instance_id})")
        except pygame.error as e:
            print(f"Failed to initialize gamepad at index {device_index}: {e}")

    @classmethod
    def _remove_gamepad(cls, instance_id: int):
        """Remove a gamepad by its instance ID."""
        if instance_id in cls._gamepads:
            gamepad = cls._gamepads[instance_id]
            print(f"Gamepad disconnected: {gamepad.get_name()} (ID: {instance_id})")
            gamepad.quit()
            del cls._gamepads[instance_id]
            del cls._gamepad_buttons[instance_id]
            del cls._prev_gamepad_buttons[instance_id]
            del cls._gamepad_axes[instance_id]

    @classmethod
    def _update_gamepads(cls):
        """Update gamepad state. Called automatically by update()."""
        for instance_id, gamepad in cls._gamepads.items():
            # Store previous button state
            cls._prev_gamepad_buttons[instance_id] = dict(cls._gamepad_buttons[instance_id])

            # Update button state
            for button in range(gamepad.get_numbuttons()):
                cls._gamepad_buttons[instance_id][button] = gamepad.get_button(button)

            # Update axis state
            for axis in range(gamepad.get_numaxes()):
                cls._gamepad_axes[instance_id][axis] = gamepad.get_axis(axis)

    @classmethod
    def init_gamepads(cls):
        """Initialize all connected gamepads. Call once at startup."""
        pygame.joystick.init()
        for i in range(pygame.joystick.get_count()):
            cls._init_gamepad(i)

    @classmethod
    def get_gamepad_count(cls) -> int:
        """Get the number of connected gamepads."""
        return len(cls._gamepads)

    @classmethod
    def get_gamepad_button(cls, gamepad_id: int, button: int) -> bool:
        """Check if a gamepad button is currently pressed."""
        if gamepad_id not in cls._gamepads:
            return False
        return cls._gamepad_buttons.get(gamepad_id, {}).get(button, False)

    @classmethod
    def get_gamepad_button_down(cls, gamepad_id: int, button: int) -> bool:
        """Check if a gamepad button was just pressed this frame."""
        if gamepad_id not in cls._gamepads:
            return False
        current = cls._gamepad_buttons.get(gamepad_id, {}).get(button, False)
        previous = cls._prev_gamepad_buttons.get(gamepad_id, {}).get(button, False)
        return current and not previous

    @classmethod
    def get_gamepad_button_up(cls, gamepad_id: int, button: int) -> bool:
        """Check if a gamepad button was just released this frame."""
        if gamepad_id not in cls._gamepads:
            return False
        current = cls._gamepad_buttons.get(gamepad_id, {}).get(button, False)
        previous = cls._prev_gamepad_buttons.get(gamepad_id, {}).get(button, False)
        return not current and previous

    @classmethod
    def get_gamepad_axis(cls, gamepad_id: int, axis: int) -> float:
        """Get the value of a gamepad axis (-1.0 to 1.0)."""
        if gamepad_id not in cls._gamepads:
            return 0.0
        return cls._gamepad_axes.get(gamepad_id, {}).get(axis, 0.0)

    @classmethod
    def get_gamepad_name(cls, gamepad_id: int) -> Optional[str]:
        """Get the name of a connected gamepad."""
        gamepad = cls._gamepads.get(gamepad_id)
        return gamepad.get_name() if gamepad else None
