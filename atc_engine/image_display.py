import pygame
import time
import threading
from typing import Optional, Tuple

class ImageDisplay(threading.Thread):
    def __init__(self, flash_duty_cycle: float, flash_duration: float):
        super().__init__()
        self.daemon = True  # Allow main program to exit even if this thread is running
        self._flash_duty_cycle = flash_duty_cycle
        self._flash_duration = flash_duration

        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.screen_size = self.screen.get_size()
        pygame.mouse.set_visible(False)

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


        self._running = threading.Event()
        self._lock = threading.Lock()

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
        with self._lock:
            scaled_image, pos = self.load_and_scale_image(image_path, self.screen_size)
            if scaled_image and pos:
                self._current_image_surface = scaled_image
                self._current_image_pos = pos
                self._current_image_path = image_path
                self._display_mode = mode
                if mode == "flash" or self._current_image_path != image_path: # Reset flash if mode is flash or image changes
                    self._flash_start_time = time.time()
            else:
                # Optionally clear if loading fails, or keep old image
                self.clear_image() # Clear if new image fails to load
                print(f"Failed to load image: {image_path}")


    def clear_image(self):
        with self._lock:
            self._current_image_surface = None
            self._current_image_pos = None
            self._current_image_path = None
            # self._display_mode = "still" # Or keep last mode? Task implies clearing image data only

    def run(self):
        self._running.clear() # Ensure it's not set initially
        clock = pygame.time.Clock()
        while not self._running.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running.set()
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        self._running.set()

            with self._lock:
                self.screen.fill((0, 0, 0))  # Black background

                if self._current_image_surface and self._current_image_pos:
                    if self._display_mode == "flash" and self._flash_duration > 0:
                        cycle_time = (time.time() - self._flash_start_time) % self._flash_duration
                        is_on_phase = cycle_time < self._on_time
                        if is_on_phase:
                            self.screen.blit(self._current_image_surface, self._current_image_pos)
                    else:  # Still mode or flash duration is zero (effectively still)
                        self.screen.blit(self._current_image_surface, self._current_image_pos)
                # If no image, screen is already filled black

            pygame.display.flip()
            clock.tick(60) # Limit to 60 FPS, sleep is handled by clock.tick

        pygame.quit()
        print("ImageDisplay thread finished and Pygame quit.")

    def stop(self):
        print("Stopping ImageDisplay thread...")
        self._running.set()

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    print("Starting ImageDisplay test...")
    # Parameters from a hypothetical config
    test_flash_duty_cycle = 0.5  # 50% on
    test_flash_duration = 2.0    # 2 second cycle

    image_display_thread = ImageDisplay(flash_duty_cycle=test_flash_duty_cycle,
                                        flash_duration=test_flash_duration)
    image_display_thread.start()

    try:
        # Test image paths (replace with actual paths in your project)
        # Ensure you have these images or similar in the specified paths for testing
        image_path1 = "../atc_engine/image_sets/set0/photo-1481349518771-20055b2a7b24.jpg"
        image_path2 = "../atc_engine/image_sets/set1/photo-1504309092620-4d0ec726efa4.jpg"
        
        # Check if test images exist
        import os
        if not os.path.exists(image_path1):
            print(f"Warning: Test image not found at {image_path1}")
            # Fallback to a placeholder if you have one, or skip this part of test
        if not os.path.exists(image_path2):
            print(f"Warning: Test image not found at {image_path2}")


        print("Displaying image 1 (still) for 5 seconds...")
        if os.path.exists(image_path1):
            image_display_thread.set_image(image_path1, "still")
        time.sleep(5)

        print("Displaying image 2 (flash) for 10 seconds...")
        if os.path.exists(image_path2):
            image_display_thread.set_image(image_path2, "flash")
        time.sleep(10)

        print("Clearing image for 3 seconds...")
        image_display_thread.clear_image()
        time.sleep(3)

        print("Displaying image 1 (flash) again for 10 seconds...")
        if os.path.exists(image_path1):
            image_display_thread.set_image(image_path1, "flash")
        time.sleep(10)

    except KeyboardInterrupt:
        print("Test interrupted by user.")
    finally:
        print("Stopping ImageDisplay thread from main...")
        image_display_thread.stop()
        image_display_thread.join() # Wait for the thread to finish
        print("ImageDisplay test finished.")