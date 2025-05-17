class ButtonState:
    """Tracks the state of a button including timing information."""
    def __init__(self):
        self.is_pressed: bool = False
        self.last_press_time: float = 0.0
        self.last_state: int = 1  # Default to HIGH (not pressed)
        self.was_in_combo: bool = False  # Track if button was part of a combo