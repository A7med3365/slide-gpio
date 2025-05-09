import argparse
import sys

try:
    import pygame
except ImportError:
    print("Error: Pygame library not found. Please install it (e.g., python -m pip install pygame).")
    sys.exit(1)

def parse_color(color_str):
    """Parses a color string into a Pygame color tuple."""
    color_str = color_str.lower()
    # Check for named colors pygame might recognize
    try:
        return pygame.Color(color_str)
    except ValueError:
        # Try to parse as R,G,B
        try:
            r, g, b = map(int, color_str.split(','))
            return (r, g, b)
        except ValueError:
            print(f"Error: Invalid color format '{color_str}'. Use name (e.g., 'white') or R,G,B (e.g., '255,0,0').")
            sys.exit(1)

def main():
    # Script-level configuration variables
    DEFAULT_TEXT = "Hello from the script!\nThis is line 2.\nEnjoy scrolling!"
    DEFAULT_SPEED = 20  # pixels per frame
    DEFAULT_FONT_SIZE = 500  # 0 for auto-calculate
    DEFAULT_FONT_COLOR = "white"  # e.g., "white", "255,0,0"
    DEFAULT_BG_COLOR = "black"  # e.g., "black", "0,0,128"

    parser = argparse.ArgumentParser(description="Scrolls text lines fullscreen using Pygame.")
    # Changed text_to_display to be optional, defaulting to DEFAULT_TEXT
    parser.add_argument("text_to_display", type=str, nargs='?', default=DEFAULT_TEXT,
                        help=f"The text string to be scrolled (default: '{DEFAULT_TEXT[:20]}...').")
    parser.add_argument("--speed", type=int, default=DEFAULT_SPEED,
                        help=f"Scrolling speed in pixels per frame (default: {DEFAULT_SPEED}).")
    parser.add_argument("--font_size", type=int, default=DEFAULT_FONT_SIZE,
                        help=f"Font size. Default {DEFAULT_FONT_SIZE} for auto-calculate based on screen height.")
    parser.add_argument("--font_color", type=str, default=DEFAULT_FONT_COLOR,
                        help=f"Font color (name or R,G,B string, default: '{DEFAULT_FONT_COLOR}').")
    parser.add_argument("--bg_color", type=str, default=DEFAULT_BG_COLOR,
                        help=f"Background color (name or R,G,B string, default: '{DEFAULT_BG_COLOR}').")

    args = parser.parse_args()

    pygame.init()

    screen_info = pygame.display.Info()
    screen_width = screen_info.current_w
    screen_height = screen_info.current_h
    
    # Attempt to enable hardware acceleration and double buffering for smoother rendering
    flags = pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF
    screen = pygame.display.set_mode((screen_width, screen_height), flags)
    pygame.display.set_caption("Text Scroller")

    font_color = parse_color(args.font_color)
    bg_color = parse_color(args.bg_color)

    font_size_to_use = args.font_size
    if font_size_to_use == 0:
        # Auto-calculate font size to make a single line approximately 1/5th of screen height
        # This is a heuristic; true "fill screen height" might be too large for practical scrolling.
        # A smaller fraction like 1/5 or 1/10 might be more visually appealing for scrolling lines.
        # Let's aim for a large, readable font, e.g. 1/4th of screen height.
        font_size_to_use = screen_height // 4
        if font_size_to_use < 20: # Ensure a minimum font size
            font_size_to_use = 20


    try:
        font = pygame.font.Font(None, font_size_to_use) # Use default system font
    except pygame.error as e:
        print(f"Error loading font: {e}. Using fallback size 48.")
        font = pygame.font.Font(None, 48)


    lines = args.text_to_display.splitlines()
    if not lines: # Handle case where input is empty or only newlines
        lines = [" "] # Scroll a blank space if no actual text

    clock = pygame.time.Clock()
    running = True

    for line_text in lines:
        if not running:
            break

        if not line_text.strip(): # If line is empty or whitespace, render a single space
            rendered_text = font.render(" ", True, font_color)
        else:
            rendered_text = font.render(line_text, True, font_color)
        
        text_width = rendered_text.get_width()
        text_height = rendered_text.get_height()

        # Start position: text surface just off-screen to the right
        # Center vertically
        x_pos = screen_width
        y_pos = (screen_height - text_height) // 2

        line_scrolling = True
        while line_scrolling and running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    line_scrolling = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        line_scrolling = False

            if not running:
                break

            x_pos -= args.speed

            screen.fill(bg_color)
            screen.blit(rendered_text, (x_pos, y_pos))
            pygame.display.flip()

            # Line is done scrolling when it has completely moved off-screen to the left
            if x_pos + text_width < 0:
                line_scrolling = False

            clock.tick(60) # Aim for 60 FPS

    pygame.quit()
    # sys.exit() # Not strictly necessary if pygame.quit() is the last Pygame call

if __name__ == "__main__":
    main()