import pygame
import time
import queue
from typing import Optional, Tuple, Dict, Any

class ImageDisplay:
    def __init__(self, media_config: Dict[str, Dict[str, Any]], flash_duty_cycle: float, flash_duration: float):
        self._flash_duty_cycle = flash_duty_cycle
        self._flash_duration = flash_duration
        self._preloaded_images: Dict[str, Tuple[pygame.Surface, Tuple[int, int]]] = {}
        self._command_queue = queue.Queue()
        self._is_running_loop = False

        # Scrolling state variables
        self._scrolling_text_lines: Optional[List[str]] = None
        self._current_scroll_line_index: int = 0
        self._current_scroll_surface: Optional[pygame.Surface] = None
        self._current_scroll_x_pos: int = 0
        self._current_scroll_y_pos: int = 0
        # self._scroll_speed, self._scroll_font_color, self._scroll_bg_color are now set in 'start_scroll_text' command processing
        self._scroll_speed: int = 3 # Default, will be overridden
        self._scroll_font_color: pygame.Color = pygame.Color("white") # Default, will be overridden
        self._scroll_bg_color: Optional[pygame.Color] = None # Default, will be overridden
        self._is_scrolling: bool = False
        self._current_scroll_font: Optional[pygame.font.Font] = None # Font for scrolling text

        pygame.init()
        # It's good practice to check if font was initialized, though pygame.init() usually handles it.
        if not pygame.font.get_init():
            pygame.font.init()
        self._font = pygame.font.Font(None, 74) # Default font for static text (display_text)
        self.screen = pygame.display.set_mode((800, 600)) # Or any other preferred size
        pygame.display.set_caption("ATC Engine Display")
        self.screen_size = self.screen.get_size()
        pygame.mouse.set_visible(False)

        self._current_text_surface: Optional[pygame.Surface] = None
        self._current_text_pos: Optional[Tuple[int, int]] = None

        for media_name, media_details in media_config.items():
            if media_details.get('mode') in ("image_still", "image_flash") and media_details.get('path'):
                image_path = media_details['path']
                if image_path not in self._preloaded_images:
                    surface, pos = self.load_and_scale_image(image_path, self.screen_size)
                    if surface:
                        self._preloaded_images[image_path] = (surface, pos)
                        print(f"[ImageDisplay] Pre-loaded image: {image_path}")
                    else:
                        print(f"[ImageDisplay] Failed to pre-load image: {image_path}")

        self._current_image_surface: Optional[pygame.Surface] = None
        self._current_image_pos: Optional[Tuple[int, int]] = None
        self._current_image_path: Optional[str] = None
        self._display_mode: str = "still"  # "still" or "flash"
        self._flash_start_time: float = 0.0

        if self._flash_duration > 0:
            self._on_time: float = self._flash_duty_cycle * self._flash_duration
            self._off_time: float = self._flash_duration - self._on_time
        else: # Avoid division by zero if duration is zero
            self._on_time: float = 0.0
            self._off_time: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._is_running_loop

    def load_and_scale_image(self, file_path: str, screen_size: Tuple[int, int]) -> Tuple[Optional[pygame.Surface], Optional[Tuple[int, int]]]:
        """Loads an image, scales it to fit the screen while maintaining aspect ratio, and returns the scaled image and its centered position."""
        try:
            img = pygame.image.load(file_path) #.convert() # Keep alpha for PNGs if any
            if img.get_alpha() is None:
                img = img.convert()
            else:
                img = img.convert_alpha()
        except pygame.error as e:
            print(f"Error loading image {file_path}: {e}")
            return None, None

        img_rect = img.get_rect()
        screen_width, screen_height = screen_size

        scale_w = screen_width / img_rect.width
        scale_h = screen_height / img_rect.height
        scale_factor = min(scale_w, scale_h)

        new_width = int(img_rect.width * scale_factor)
        new_height = int(img_rect.height * scale_factor)

        try:
            img_scaled = pygame.transform.smoothscale(img, (new_width, new_height))
        except ValueError: # Happens if new_width or new_height is 0
             img_scaled = pygame.transform.scale(img, (new_width, new_height))


        pos_x = (screen_width - new_width) // 2
        pos_y = (screen_height - new_height) // 2

        return img_scaled, (pos_x, pos_y)

    def set_image(self, image_path: str, mode: str):
        self._command_queue.put({'type': 'set_image', 'path': image_path, 'mode': mode})

    def clear_image(self):
        self._command_queue.put({'type': 'clear_image'})

    def display_text(self, text: str, color: Tuple[int, int, int] = (255, 255, 255), bg_color: Optional[Tuple[int, int, int]] = None):
        """Queues a command to display text on the screen."""
        self._command_queue.put({'type': 'display_text', 'text': text, 'color': color, 'bg_color': bg_color})

    def start_scroll_text(self, file_path: str, speed: int = 3, font_size: int = 60, font_color_str: str = "white", bg_color_str: Optional[str] = None):
        """Queues a command to start scrolling text from a file with specified parameters."""
        self._command_queue.put({
            'type': 'start_scroll_text',
            'path': file_path,
            'speed': speed,
            'font_size': font_size,
            'font_color': font_color_str,
            'bg_color': bg_color_str
        })

    def _prepare_next_scroll_line(self) -> None:
        if not self._scrolling_text_lines:
            print("[ImageDisplay] No scroll lines available.")
            self._is_scrolling = False
            self._current_scroll_surface = None
            return

        if self._current_scroll_line_index >= len(self._scrolling_text_lines):
            self._current_scroll_line_index = 0 # Wrap around for endless scrolling
            print("[ImageDisplay] Wrapping scroll text to beginning.")

        if not self._current_scroll_font:
            print("[ImageDisplay] Error: Scroll font not initialized.")
            # Fallback to default font if scroll font isn't set; ideally, this shouldn't happen if start_scroll_text was called.
            self._current_scroll_font = pygame.font.Font(None, 30)


        line_text = self._scrolling_text_lines[self._current_scroll_line_index].strip()
        if not line_text: # If line is empty or whitespace after strip, render a single space
            line_text = " "
        
        try:
            # Render text (True for antialiasing)
            self._current_scroll_surface = self._current_scroll_font.render(
                line_text, True, self._scroll_font_color, self._scroll_bg_color
            )
            text_rect = self._current_scroll_surface.get_rect()
            self._current_scroll_x_pos = self.screen_size[0] # Start off-screen right
            self._current_scroll_y_pos = (self.screen_size[1] - text_rect.height) // 2 # Center vertically
            print(f"[ImageDisplay] Prepared scroll line {self._current_scroll_line_index + 1}/{len(self._scrolling_text_lines)}: '{line_text}'")
        except Exception as e:
            print(f"[ImageDisplay] Error rendering scroll line '{line_text}' with current font: {e}")
            self._current_scroll_surface = None
            # Potentially skip to next line or stop scrolling if error persists
            self._current_scroll_line_index += 1 # Move to next line to avoid getting stuck
            if self._current_scroll_line_index < len(self._scrolling_text_lines):
                self._prepare_next_scroll_line() # Try next line
            else: # Reached end after an error, wrap or stop
                self._current_scroll_line_index = 0
                if len(self._scrolling_text_lines) > 0 : # only prepare if there are lines
                    self._prepare_next_scroll_line()
                else:
                    self._is_scrolling = False # No lines to scroll
        # Removed the 'else' block that previously set _is_scrolling = False,
        # as wrapping handles continuation. _is_scrolling is set False if _scrolling_text_lines is None/empty.

    def stop_display(self):
        self._command_queue.put({'type': 'stop'})

    def run(self):
        self._is_running_loop = True
        # clock = pygame.time.Clock() # Use pygame.time.wait() for simplicity or clock.tick()

        print("[ImageDisplay] Starting Pygame event loop...")
        while self._is_running_loop:
            # Process Pygame Events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._is_running_loop = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        self._is_running_loop = False
            
            if not self._is_running_loop: # Check if QUIT event was processed
                break

            # Process Command Queue
            while not self._command_queue.empty():
                try:
                    command = self._command_queue.get_nowait()
                    print(f"[ImageDisplay] Dequeued command: {command}")
                    if command['type'] == 'set_image':
                        path = command['path']
                        mode = command['mode']
                        if path in self._preloaded_images:
                            self._current_image_surface, self._current_image_pos = self._preloaded_images[path]
                            self._current_image_path = path
                            self._display_mode = mode
                            self._flash_start_time = time.time() # Reset flash timer
                            self._current_text_surface = None # Clear any active text
                            self._current_text_pos = None
                            self._is_scrolling = False # Stop scrolling
                            self._scrolling_text_lines = None
                            self._current_scroll_surface = None
                            print(f"[ImageDisplay] CMD: Set image to {path}, Mode: {mode}")
                        else:
                            print(f"[ImageDisplay] CMD Error: Image not pre-loaded: {path}")
                            self._current_image_surface = None
                            self._current_image_pos = None
                            self._current_image_path = None
                            self._current_text_surface = None # Also clear text if image loading failed
                            self._current_text_pos = None
                            self._is_scrolling = False # Stop scrolling
                            self._scrolling_text_lines = None
                            self._current_scroll_surface = None
                    elif command['type'] == 'clear_image':
                        print(f"[ImageDisplay] CMD: Clear image")
                        self._current_image_surface = None
                        self._current_image_path = None
                        self._current_text_surface = None # Clear any active text
                        self._current_text_pos = None
                        self._is_scrolling = False # Stop scrolling
                        self._scrolling_text_lines = None
                        self._current_scroll_surface = None
                    elif command['type'] == 'display_text':
                        text_to_display = command['text']
                        text_color = command.get('color', (255, 255, 255))
                        bg_color = command.get('bg_color') # Can be None for transparent background

                        print(f"[ImageDisplay] CMD: Display text: '{text_to_display}'")
                        try:
                            # Clear previous image/text
                            self._current_image_surface = None
                            self._current_image_path = None
                            self._is_scrolling = False # Stop scrolling
                            self._scrolling_text_lines = None
                            self._current_scroll_surface = None
                            
                            # Render text
                            # The second argument to render is antialiasing (True/False)
                            text_surf = self._font.render(text_to_display, True, text_color, bg_color)
                            text_rect = text_surf.get_rect(center=(self.screen_size[0] // 2, self.screen_size[1] // 2))
                            
                            self._current_text_surface = text_surf
                            self._current_text_pos = text_rect.topleft
                        except Exception as e:
                            print(f"[ImageDisplay] Error rendering text '{text_to_display}': {e}")
                            self._current_text_surface = None
                            self._current_text_pos = None
                    elif command['type'] == 'start_scroll_text':
                        file_path = command['path']
                        self._scroll_speed = command.get('speed', 3)
                        font_size_to_use = command.get('font_size', 60)
                        font_color_str = command.get('font_color', 'white')
                        bg_color_str = command.get('bg_color')

                        try:
                            self._current_scroll_font = pygame.font.Font(None, font_size_to_use)
                        except Exception as e:
                            print(f"[ImageDisplay] Error creating font size {font_size_to_use}: {e}. Using fallback.")
                            self._current_scroll_font = pygame.font.Font(None, 30) # Fallback font

                        try:
                            self._scroll_font_color = pygame.Color(font_color_str)
                        except ValueError:
                            print(f"[ImageDisplay] Invalid font color string '{font_color_str}'. Using white.")
                            self._scroll_font_color = pygame.Color('white')

                        if bg_color_str:
                            try:
                                self._scroll_bg_color = pygame.Color(bg_color_str)
                            except ValueError:
                                print(f"[ImageDisplay] Invalid background color string '{bg_color_str}'. Using None.")
                                self._scroll_bg_color = None
                        else:
                            self._scroll_bg_color = None

                        print(f"[ImageDisplay] CMD: Start scroll text from '{file_path}', Speed: {self._scroll_speed}, Font Size: {font_size_to_use}, Color: {self._scroll_font_color}, BG: {self._scroll_bg_color}")
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                self._scrolling_text_lines = f.readlines()
                            if not self._scrolling_text_lines:
                                print(f"[ImageDisplay] Scroll text file '{file_path}' is empty. Displaying placeholder.")
                                self._scrolling_text_lines = ["(Empty File)"]
                            
                            self._current_scroll_line_index = 0
                            self._is_scrolling = True
                            
                            # Clear other display modes
                            self._current_image_surface = None
                            self._current_image_path = None
                            self._current_text_surface = None # Clear static text
                            
                            self._prepare_next_scroll_line()
                        except FileNotFoundError:
                            print(f"[ImageDisplay] Error: Scroll text file not found: {file_path}")
                            self._is_scrolling = False
                            self._scrolling_text_lines = None
                            self._current_scroll_font = None # Clear font if file not found
                        except Exception as e:
                            print(f"[ImageDisplay] Error reading or preparing scroll text file '{file_path}': {e}")
                            self._is_scrolling = False
                            self._scrolling_text_lines = None
                            self._current_scroll_font = None # Clear font on other errors
                    elif command['type'] == 'stop':
                        self._is_running_loop = False
                        print(f"[ImageDisplay] CMD: Stop display loop")
                        break # Break from command processing loop
                except queue.Empty:
                    pass # Should not happen due to the check, but good practice
                except Exception as e:
                    print(f"[ImageDisplay] Error processing command: {command} - {e}")
            
            if not self._is_running_loop: # Check if 'stop' command was processed
                break

            # Render Logic
            # --- Update Display ---
            self.screen.fill((0, 0, 0)) # Clear screen with black

            if self._is_scrolling and self._current_scroll_surface:
                self._current_scroll_x_pos -= self._scroll_speed
                self.screen.blit(self._current_scroll_surface, (self._current_scroll_x_pos, self._current_scroll_y_pos))
                
                if self._current_scroll_x_pos + self._current_scroll_surface.get_width() < 0:
                    self._current_scroll_line_index += 1
                    self._prepare_next_scroll_line()
                    
            elif self._current_text_surface and self._current_text_pos: # Static text
                self.screen.blit(self._current_text_surface, self._current_text_pos)
            elif self._current_image_surface and self._current_image_pos: # Image display
                if self._display_mode == "flash" and self._flash_duration > 0 and self._on_time > 0: # Ensure on_time is positive
                    cycle_time = (time.time() - self._flash_start_time) % self._flash_duration
                    is_on_phase = cycle_time < self._on_time
                    if is_on_phase:
                        self.screen.blit(self._current_image_surface, self._current_image_pos)
                else:  # Still mode or flash duration/on_time is zero (effectively still)
                    self.screen.blit(self._current_image_surface, self._current_image_pos)
            
            pygame.display.flip()
            pygame.time.wait(10) # Manage frame rate / yield CPU
            # clock.tick(60) # Alternative: Limit to 60 FPS

        pygame.quit()
        print("[ImageDisplay] Pygame quit.")

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    print("Starting ImageDisplay test...")
    # Parameters from a hypothetical config
    test_flash_duty_cycle = 0.5  # 50% on
    test_flash_duration = 2.0    # 2 second cycle

    # Example media_config for testing
    test_media_config = {
        "image1": {
            "path": "../atc_engine/image_sets/set0/photo-1481349518771-20055b2a7b24.jpg",
            "mode": "image_still",
            "duration": 5
        },
        "image2": {
            "path": "../atc_engine/image_sets/set1/photo-1504309092620-4d0ec726efa4.jpg",
            "mode": "image_flash",
            "duration": 10
        },
        "non_image": {
            "path": "some_video.mp4",
            "mode": "video_loop"
        },
        "missing_path_image": {
            "mode": "image_still"
        },
        "bad_path_image": {
            "path": "non_existent_image.jpg",
            "mode": "image_still"
        }
    }

    # Example Usage (for testing purposes - needs to be run in the main thread)
    # To test this, you would typically call image_display.run() from your main application thread.
    # The following is a conceptual test and won't run as a separate thread anymore.

    image_display = ImageDisplay(media_config=test_media_config,
                                 flash_duty_cycle=test_flash_duty_cycle,
                                 flash_duration=test_flash_duration)

    # --- This part would be in your main application logic ---
    # Start a separate thread to send commands, as image_display.run() will block.
    def command_sender(display_controller):
        try:
            image_path1 = "../atc_engine/image_sets/set0/photo-1481349518771-20055b2a7b24.jpg"
            image_path2 = "../atc_engine/image_sets/set1/photo-1504309092620-4d0ec726efa4.jpg"
            import os

            print("Sending: Display image 1 (still) for 5 seconds...")
            if os.path.exists(image_path1):
                display_controller.set_image(image_path1, "still")
            time.sleep(5)

            print("Sending: Display image 2 (flash) for 10 seconds...")
            if os.path.exists(image_path2):
                display_controller.set_image(image_path2, "flash")
            time.sleep(10)

            print("Sending: Clear image for 3 seconds...")
            display_controller.clear_image()
            time.sleep(3)

            print("Sending: Display image 1 (flash) again for 10 seconds...")
            if os.path.exists(image_path1):
                display_controller.set_image(image_path1, "flash")
            time.sleep(10)

        except Exception as e:
            print(f"Command sender error: {e}")
        finally:
            print("Sending: Stop display command...")
            display_controller.stop_display()

    # For testing, we can run command_sender in a thread, and image_display.run() in main.
    import threading
    cmd_thread = threading.Thread(target=command_sender, args=(image_display,))
    cmd_thread.daemon = True # So it exits when main thread (image_display.run) exits
    
    print("Starting command sender thread...")
    cmd_thread.start()
    
    print("Calling image_display.run() (this will block until quit)...")
    try:
        image_display.run() # This is now a blocking call
    except KeyboardInterrupt:
        print("Main loop interrupted by user. Sending stop command.")
        image_display.stop_display() # Ensure Pygame quits cleanly if run() was interrupted
        # Wait for run() to finish processing the stop command and quit Pygame
        # This might require image_display.run() to handle KeyboardInterrupt or have a timeout
        # For simplicity, we assume stop_display() will lead to run() exiting.
    
    # cmd_thread.join() # Wait for command thread to finish (optional, as it's daemon)
    print("ImageDisplay test finished (or run() exited).")