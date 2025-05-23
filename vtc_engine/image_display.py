import pygame
import time
import queue
from typing import Optional, Tuple, Dict, Any, List
import os # Added for directory operations

class ImageDisplay:
    def __init__(self, media_config: Dict[str, Dict[str, Any]], flash_duty_cycle: float, flash_duration: float, fullscreen: bool = True):
        self._flash_duty_cycle = flash_duty_cycle
        self._flash_duration = flash_duration
        self._preloaded_images: Dict[str, List[Tuple[pygame.Surface, Tuple[int, int]]]] = {} # Path maps to a LIST of images
        self._command_queue = queue.Queue()
        self._is_running_loop = False

        # Slideshow state variables
        self._current_slideshow_images: List[Tuple[pygame.Surface, Tuple[int, int]]] = []
        self._current_slideshow_index: int = 0
        self._slideshow_last_switch_time: float = 0.0
        self._is_slideshow_active: bool = False

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
        if fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode((800, 600)) # Or any other preferred size
        pygame.display.set_caption("ATC Engine Display")
        self.screen_size = self.screen.get_size()
        pygame.mouse.set_visible(False)

        self._current_text_surface: Optional[pygame.Surface] = None
        self._current_text_pos: Optional[Tuple[int, int]] = None

        for media_name, media_details in media_config.items():
            if media_details.get('mode') in ("image_still", "image_flash") and media_details.get('path'):
                dir_path = media_details['path']

                if not os.path.isdir(dir_path):
                    print(f"[ImageDisplay] Configured path '{dir_path}' for '{media_name}' is not a directory. Skipping preloading for this item.")
                    # Optionally, could try to load as single file if that's a desired fallback:
                    # if os.path.isfile(dir_path):
                    #     surface, pos = self.load_and_scale_image(dir_path, self.screen_size)
                    #     if surface:
                    #         self._preloaded_images[dir_path] = [(surface, pos)] # Store as list of one
                    #         print(f"[ImageDisplay] Pre-loaded single image file: {dir_path}")
                    #     else:
                    #         print(f"[ImageDisplay] Failed to pre-load single image file: {dir_path}")
                    continue

                if dir_path not in self._preloaded_images: # Process each directory only once
                    loaded_images_for_dir = []
                    image_files_in_dir = []
                    valid_extensions = ('.jpg', '.jpeg', '.png', '.gif')
                    try:
                        # Sort files for consistent slideshow order
                        for filename in sorted(os.listdir(dir_path)):
                            if filename.lower().endswith(valid_extensions):
                                image_file_path = os.path.join(dir_path, filename)
                                image_files_in_dir.append(image_file_path)
                    except OSError as e:
                        print(f"[ImageDisplay] Error listing directory {dir_path}: {e}")
                        self._preloaded_images[dir_path] = [] # Mark as processed with error
                        continue

                    if not image_files_in_dir:
                        print(f"[ImageDisplay] No valid image files found in directory: {dir_path}")
                        self._preloaded_images[dir_path] = [] # Mark as processed but empty
                        continue
                    
                    print(f"[ImageDisplay] Found {len(image_files_in_dir)} potential images in {dir_path}. Attempting to load...")
                    for image_file_path in image_files_in_dir:
                        surface, pos = self.load_and_scale_image(image_file_path, self.screen_size)
                        if surface:
                            loaded_images_for_dir.append((surface, pos))
                            # print(f"[ImageDisplay] Successfully pre-loaded image: {image_file_path}") # Verbose
                        else:
                            print(f"[ImageDisplay] Failed to pre-load image: {image_file_path}")
                    
                    if loaded_images_for_dir:
                        self._preloaded_images[dir_path] = loaded_images_for_dir
                        print(f"[ImageDisplay] Successfully pre-loaded {len(loaded_images_for_dir)} images from directory: {dir_path}")
                    else:
                        print(f"[ImageDisplay] Found image files in {dir_path} but failed to load any of them.")
                        self._preloaded_images[dir_path] = [] # Mark as processed, all failed

        self._current_image_surface: Optional[pygame.Surface] = None
        self._current_image_pos: Optional[Tuple[int, int]] = None
        self._current_image_path: Optional[str] = None
        self._display_mode: str = "still"  # "still" or "flash"
        self._flash_start_time: float = 0.0
        
        # Default on/off times for "image_flash" mode
        if self._flash_duration > 0:
            self._on_time: float = self._flash_duty_cycle * self._flash_duration
            self._off_time: float = self._flash_duration - self._on_time
        else: # Avoid division by zero if duration is zero
            self._on_time: float = 0.0 # Effectively always on if duration is 0
            self._off_time: float = 0.0

        # Active on/off times for the currently displayed image
        self._active_on_time: float = 0.0
        self._active_off_time: float = 0.0
  
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
                        dir_path = command['path'] # This is now a directory path
                        mode = command['mode']

                        # Reset slideshow state before setting new image/slideshow
                        self._is_slideshow_active = False
                        self._current_slideshow_images = []
                        self._current_slideshow_index = 0
                        self._current_image_surface = None # Ensure cleared if path not found or empty
                        self._current_image_path = None

                        if dir_path in self._preloaded_images:
                            images_in_dir = self._preloaded_images[dir_path]

                            if not images_in_dir:
                                print(f"[ImageDisplay] CMD Error: No images successfully pre-loaded for directory: {dir_path}. Skipping display.")
                                # Keep display clear (already done by clearing _current_image_surface)
                            elif len(images_in_dir) == 1:
                                # Single image display
                                self._current_image_surface, self._current_image_pos = images_in_dir[0]
                                self._current_image_path = dir_path # Represents the item being displayed
                                self._display_mode = mode
                                self._flash_start_time = time.time()
                                print(f"[ImageDisplay] CMD: Set single image from {dir_path}, Mode: {mode}")
                            else:
                                # Multiple images: Start slideshow
                                self._is_slideshow_active = True
                                self._current_slideshow_images = images_in_dir
                                self._current_slideshow_index = 0
                                self._current_image_surface, self._current_image_pos = self._current_slideshow_images[self._current_slideshow_index]
                                self._current_image_path = dir_path # Represents the directory slideshow
                                self._display_mode = mode # This mode applies to each slide
                                self._flash_start_time = time.time() # For the first image in slideshow
                                self._slideshow_last_switch_time = time.time()
                                print(f"[ImageDisplay] CMD: Start slideshow from {dir_path} ({len(images_in_dir)} images), Mode: {mode}")
                            
                            # Common logic if an image is to be displayed (single or first of slideshow)
                            if self._current_image_surface:
                                if mode == "image_still":
                                    if self._flash_duration > 0: # For slideshow, still image lasts for flash_duration
                                        self._active_on_time = self._flash_duration
                                        self._active_off_time = 0.0
                                    else: # If flash_duration is 0, treat as always on
                                        self._active_on_time = 1.0
                                        self._active_off_time = 0.0
                                elif mode == "image_flash":
                                    self._active_on_time = self._on_time
                                    self._active_off_time = self._off_time
                                
                                print(f"[ImageDisplay] Effective display mode: {self._display_mode}, Active ON: {self._active_on_time:.2f}s, OFF: {self._active_off_time:.2f}s, Flash Cycle Duration: {self._flash_duration:.2f}s")
                        else:
                            print(f"[ImageDisplay] CMD Error: Directory path '{dir_path}' not found in pre-loaded images or failed preloading.")
                            # Ensure display is clear
                            self._current_image_surface = None
                            self._current_image_path = None
                        
                        # Clear text/scrolling when an image/slideshow command is processed (even if it fails to set an image)
                        self._current_text_surface = None
                        self._current_text_pos = None
                        self._is_scrolling = False
                        self._scrolling_text_lines = None
                        self._current_scroll_surface = None

                    elif command['type'] == 'clear_image':
                        print(f"[ImageDisplay] CMD: Clear image")
                        self._current_image_surface = None
                        self._current_image_path = None
                        self._current_text_surface = None
                        self._current_text_pos = None
                        self._is_scrolling = False
                        self._scrolling_text_lines = None
                        self._current_scroll_surface = None
                        # Reset slideshow state as well
                        self._is_slideshow_active = False
                        self._current_slideshow_images = []
                        self._current_slideshow_index = 0
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

            # Slideshow advancement logic
            if self._is_slideshow_active and self._current_slideshow_images and len(self._current_slideshow_images) > 1:
                # Slide duration is _flash_duration for both still and flash modes in a slideshow.
                # This is the total time one slide is shown (either statically or flashing).
                slide_total_duration = self._flash_duration

                if slide_total_duration > 0: # Only switch if duration is meaningful
                    current_time = time.time()
                    if (current_time - self._slideshow_last_switch_time >= slide_total_duration):
                        self._current_slideshow_index = (self._current_slideshow_index + 1) % len(self._current_slideshow_images)
                        self._current_image_surface, self._current_image_pos = self._current_slideshow_images[self._current_slideshow_index]
                        self._slideshow_last_switch_time = current_time
                        self._flash_start_time = current_time # Reset flash timer for the new image in slideshow
                        # _active_on_time and _active_off_time remain based on the overall slideshow mode
                        print(f"[ImageDisplay] Slideshow: Switched to image {self._current_slideshow_index + 1}/{len(self._current_slideshow_images)}")

            if self._is_scrolling and self._current_scroll_surface:
                self._current_scroll_x_pos -= self._scroll_speed
                self.screen.blit(self._current_scroll_surface, (self._current_scroll_x_pos, self._current_scroll_y_pos))
                
                if self._current_scroll_x_pos + self._current_scroll_surface.get_width() < 0:
                    self._current_scroll_line_index += 1
                    self._prepare_next_scroll_line()
                    
            elif self._current_text_surface and self._current_text_pos: # Static text
                self.screen.blit(self._current_text_surface, self._current_text_pos)
            elif self._current_image_surface and self._current_image_pos: # Image display
                # Unified flashing logic using _active_on_time and _flash_duration
                if self._flash_duration <= 0: # Always ON if duration is not positive (e.g. image_still with duration 0)
                    self.screen.blit(self._current_image_surface, self._current_image_pos)
                else: # Positive flash duration
                    if self._active_on_time >= self._flash_duration: # 100% duty cycle (e.g. image_still with positive duration)
                        self.screen.blit(self._current_image_surface, self._current_image_pos)
                    elif self._active_on_time <= 0: # 0% duty cycle (always off, for image_flash with 0% duty)
                        pass # Don't blit
                    else: # Standard flashing for image_flash with duty < 100%
                        cycle_time = (time.time() - self._flash_start_time) % self._flash_duration
                        is_on_phase = cycle_time < self._active_on_time
                        if is_on_phase:
                            self.screen.blit(self._current_image_surface, self._current_image_pos)
            
            pygame.display.flip()
            pygame.time.wait(10) # Manage frame rate / yield CPU
            # clock.tick(60) # Alternative: Limit to 60 FPS

        pygame.quit()
        print("[ImageDisplay] Pygame quit.")

if __name__ == '__main__':
    import threading
    import os

    print("Starting ImageDisplay Comprehensive Test...")

    # Configuration for ImageDisplay
    test_flash_duty_cycle = 0.5  # 50% on time for flashing
    test_flash_duration = 1.0    # 1 second flash cycle (0.5s on, 0.5s off)

    # Define image paths (ensure these images exist at the specified locations)
    # Using paths relative to the workspace root, as seen in environment_details
    image_path_still = "demo3/6_Bahrain flag-1.jpg"
    image_path_flash = "demo3/5_vtc-1.jpg"
    scroll_text_file = "test_scroll_text.txt" # Created in the previous step

    # Media configuration for preloading images
    # The 'path' here is what ImageDisplay uses to load, and what set_image refers to.
    test_media_config = {
        "still_image_test": {
            "path": image_path_still,
            "mode": "image_still" # This mode in config is for initial setup, set_image overrides
        },
        "flash_image_test": {
            "path": image_path_flash,
            "mode": "image_flash"
        }
    }

    # Create ImageDisplay instance
    image_display = ImageDisplay(media_config=test_media_config,
                                 flash_duty_cycle=test_flash_duty_cycle,
                                 flash_duration=test_flash_duration)

    def command_scheduler(display_controller):
        """Sends a sequence of commands to the ImageDisplay controller."""
        try:
            print("[Test] Waiting for Pygame window to initialize (2s)...")
            time.sleep(2) # Give Pygame a moment to initialize window

            # 1. Test: Display Still Image
            print(f"[Test] CMD: Display still image: {image_path_still}")
            if os.path.exists(image_path_still):
                display_controller.set_image(image_path_still, "still")
            else:
                print(f"[Test] Error: Still image not found at {image_path_still}")
                display_controller.display_text(f"Error: Missing {image_path_still.split('/')[-1]}", color=(255,0,0))
            time.sleep(5)

            # 2. Test: Display Flashing Image
            print(f"[Test] CMD: Display flashing image: {image_path_flash}")
            if os.path.exists(image_path_flash):
                display_controller.set_image(image_path_flash, "flash")
            else:
                print(f"[Test] Error: Flash image not found at {image_path_flash}")
                display_controller.display_text(f"Error: Missing {image_path_flash.split('/')[-1]}", color=(255,0,0))
            time.sleep(5) # Display for 5 seconds (5 flash cycles)

            # 3. Test: Clear Image
            print("[Test] CMD: Clear image")
            display_controller.clear_image()
            time.sleep(3)

            # 4. Test: Display Static Text
            print("[Test] CMD: Display static text 'Hello World!'")
            display_controller.display_text("Hello Pygame!", color=(0, 255, 0), bg_color=(50, 50, 50))
            time.sleep(5)

            # 5. Test: Display Scrolling Text
            print(f"[Test] CMD: Start scrolling text from {scroll_text_file}")
            if os.path.exists(scroll_text_file):
                display_controller.start_scroll_text(
                    file_path=scroll_text_file,
                    speed=2,
                    font_size=50,
                    font_color_str="yellow",
                    bg_color_str="navy"
                )
            else:
                print(f"[Test] Error: Scroll text file not found at {scroll_text_file}")
                display_controller.display_text(f"Error: Missing {scroll_text_file}", color=(255,0,0))
            time.sleep(15) # Let it scroll for a while

            # 6. Test: Display another static text after scrolling
            print("[Test] CMD: Display static text 'Test Complete'")
            display_controller.display_text("Test Complete!", color=(255, 255, 255), bg_color=(0,0,100))
            time.sleep(5)

        except Exception as e:
            print(f"[Test] Command scheduler error: {e}")
        finally:
            print("[Test] CMD: Stop display")
            display_controller.stop_display()

    # Start the command scheduler in a separate thread
    # This is crucial because image_display.run() is a blocking call.
    scheduler_thread = threading.Thread(target=command_scheduler, args=(image_display,))
    scheduler_thread.daemon = True  # Allows main program to exit even if thread is running

    print("[Test] Starting command scheduler thread...")
    scheduler_thread.start()

    print("[Test] Calling image_display.run() (blocking call)...")
    try:
        image_display.run()  # This will block until stop_display() is called or an error occurs
    except KeyboardInterrupt:
        print("[Test] KeyboardInterrupt received. Stopping display...")
        image_display.stop_display()
    except Exception as e:
        print(f"[Test] Error during image_display.run(): {e}")
        image_display.stop_display() # Attempt to clean up
    finally:
        print("[Test] image_display.run() has exited.")
        if scheduler_thread.is_alive():
            print("[Test] Waiting for command scheduler thread to finish...")
            scheduler_thread.join(timeout=5) # Wait for the scheduler to finish
            if scheduler_thread.is_alive():
                print("[Test] Warning: Command scheduler thread did not finish cleanly.")
        print("[Test] ImageDisplay Comprehensive Test Finished.")