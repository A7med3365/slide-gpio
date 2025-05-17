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

        pygame.init()
        self.screen = pygame.display.set_mode((800, 600)) # Or any other preferred size
        pygame.display.set_caption("ATC Engine Display")
        self.screen_size = self.screen.get_size()
        pygame.mouse.set_visible(False)

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
                            print(f"[ImageDisplay] CMD: Set image to {path}, Mode: {mode}")
                        else:
                            print(f"[ImageDisplay] CMD Error: Image not pre-loaded: {path}")
                            self._current_image_surface = None
                            self._current_image_pos = None
                            self._current_image_path = None
                    elif command['type'] == 'clear_image':
                        self._current_image_surface = None
                        self._current_image_pos = None
                        self._current_image_path = None
                        # self._display_mode = "still" # Or keep current mode?
                        print(f"[ImageDisplay] CMD: Clear image")
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
            self.screen.fill((0, 0, 0))  # Black background

            if self._current_image_surface and self._current_image_pos:
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