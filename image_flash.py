import pygame
import os
import sys
import time

# Import the correct GPIO module from pyA64
try:
    from pyA64.gpio import port
    from pyA64.gpio import gpio
except ImportError:
    print("Error: pyA64 library not found. Please install it (`sudo pip3 install pyA64`).")
    sys.exit(1)

# --- Configuration ---

# Flashing configuration
FLASH_DUTY_CYCLE = 0.75  # 75% of time image is shown
FLASH_DURATION = 1.0    # Total time for one flash cycle in seconds

# ** IMPORTANT: REPLACE THESE VALUES WITH YOUR ACTUAL GPIO PIN NUMBERS **
# List of GPIO pin numbers for your 8 buttons
# The index of the button in this list corresponds to the image index it will show
BUTTON_GPIO_PINS = [
    32,  # Example: Replace with your button 1 GPIO pin number
    33,  # Example: Replace with your button 2 GPIO pin number
    34,  # Example: Replace with your button 3 GPIO pin number
    35,  # Example: Replace with your button 4 GPIO pin number
    # 36,  # Example: Replace with your button 5 GPIO pin number
    # 37,  # Example: Replace with your button 6 GPIO pin number
    # 38,  # Example: Replace with your button 7 GPIO pin number
    # 39   # Example: Replace with your button 8 GPIO pin number
]

# List of image files to display.
# Make sure these paths are correct.
# The index of the image in this list corresponds to the button index it's linked to.
IMAGE_FILES = [
    "gpio_slideshow/image_sets/set0/photo-1481349518771-20055b2a7b24.jpg", # Replace with actual path
    "gpio_slideshow/image_sets/set0/photo-1494253109108-2e30c049369b.jpg", # Replace with actual path
    "gpio_slideshow/image_sets/set1/photo-1504309092620-4d0ec726efa4.jpg", # Replace with actual path
    "gpio_slideshow/image_sets/set1/photo-1613336026275-d6d473084e85.jpg", # Replace with actual path
    # "path/to/your/image5.jpg", # Replace with actual path
    # "path/to/your/image6.png", # Replace with actual path
    # "path/to/your/image7.jpg", # Replace with actual path
    # "path/to/your/image8.png"  # Replace with actual path
]

# Debounce delay in seconds. Prevents multiple triggers from a single button press.
DEBOUNCE_DELAY = 0.2

# --- Script Logic ---

def load_and_scale_image(file_path, screen_size):
    """Loads an image, scales it to fit the screen while maintaining aspect ratio, and returns the scaled image and its centered position."""
    try:
        img = pygame.image.load(file_path).convert()
    except pygame.error as e:
        print(f"Error loading image {file_path}: {e}")
        return None, None

    img_rect = img.get_rect()
    screen_width, screen_height = screen_size

    # Calculate scaling factor preserving aspect ratio
    scale_w = screen_width / img_rect.width
    scale_h = screen_height / img_rect.height
    scale_factor = min(scale_w, scale_h)

    new_width = int(img_rect.width * scale_factor)
    new_height = int(img_rect.height * scale_factor)

    img_scaled = pygame.transform.scale(img, (new_width, new_height))

    # Calculate centered position
    pos_x = (screen_width - new_width) // 2
    pos_y = (screen_height - new_height) // 2

    return img_scaled, (pos_x, pos_y)

def main():
    pygame.init()

    # Set up fullscreen display
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen_info = pygame.display.Info()
    screen_size = (screen_info.current_w, screen_info.current_h)

    pygame.mouse.set_visible(False) # Hide mouse cursor

    print("Loading images...")
    loaded_images_data = []
    for img_file in IMAGE_FILES:
        img_data, pos = load_and_scale_image(img_file, screen_size)
        if img_data:
            loaded_images_data.append((img_data, pos))
        else:
            print(f"Skipping image {img_file}")
            loaded_images_data.append((None, None)) # Placeholder for skipped image

    if not any(img is not None for img, pos in loaded_images_data):
        print("No images loaded successfully. Exiting.")
        pygame.quit()
        sys.exit(1)

    if len(BUTTON_GPIO_PINS) != len(IMAGE_FILES):
        print("Warning: Number of buttons does not match the number of images.")

    print("Initializing GPIO (using pyA64.gpio)...")
    try:
        gpio.init()
        valid_buttons = []
        for pin in BUTTON_GPIO_PINS:
            try:
                # Configure the button pin as input with pull-up resistor
                gpio.setcfg(pin, gpio.INPUT)
                gpio.pullup(pin, gpio.PULLUP)
                valid_buttons.append(pin)
                print(f"Initialized pin {pin} as input with pull-up.")
            except Exception as e:
                print(f"Error setting up GPIO pin {pin}: {e}")
                print("Please check the pin number and permissions.")

        if not valid_buttons:
            print("No GPIO pins initialized successfully. Exiting.")
            pygame.quit()
            sys.exit(1)

        # Update pin list to only include valid pins
        BUTTON_GPIO_PINS[:] = valid_buttons
        print("GPIO initialized.")

    except Exception as e:
        print(f"Error initializing GPIO: {e}")
        print("Please ensure you are running with sudo and the pyA64 library is correctly installed.")
        pygame.quit()
        sys.exit(1)

    current_image_index = 0
    # Ensure the initial image index corresponds to a successfully loaded image
    while current_image_index < len(loaded_images_data) and loaded_images_data[current_image_index][0] is None:
        current_image_index += 1
    if current_image_index >= len(loaded_images_data):
        print("No initial valid image to display. Exiting.")
        gpio.cleanup()
        pygame.quit()
        sys.exit(1)

    last_press_time = 0 # For debouncing
    flash_start_time = time.time() # For tracking flash cycles

    # Calculate flash timing
    on_time = FLASH_DUTY_CYCLE * FLASH_DURATION
    off_time = FLASH_DURATION - on_time

    # Initial draw
    screen.fill((0, 0, 0)) # Black background
    if loaded_images_data[current_image_index][0]:
        screen.blit(loaded_images_data[current_image_index][0], loaded_images_data[current_image_index][1])
    pygame.display.flip()

    print("Starting display loop. Press buttons to change images. Press Ctrl+C in terminal or Esc/q on keyboard to exit.")

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE or (hasattr(event, 'unicode') and event.unicode == 'q'):
                    running = False

        # --- Read Button States ---
        current_time = time.time()

        needs_redraw = False
        for i, pin in enumerate(BUTTON_GPIO_PINS):
            try:
                # Read the state of the pin
                button_state = gpio.input(pin)

                # Check if button is pressed (state is LOW/0) and debounce time has passed
                if button_state == gpio.LOW and (current_time - last_press_time) > DEBOUNCE_DELAY:
                    # Map the button index (i) to the image index
                    if i < len(loaded_images_data) and loaded_images_data[i][0]:
                        print(f"Button {i+1} (Pin {pin}) pressed. Switching to image {i+1}.")
                        current_image_index = i
                        last_press_time = current_time # Update last press time
                        flash_start_time = current_time # Reset flash cycle
                        needs_redraw = True
                    else:
                        print(f"Button {i+1} (Pin {pin}) pressed, but no valid image found for this index.")

            except Exception as e:
                print(f"Error reading state from pin {pin}: {e}")
                time.sleep(0.01) # Prevent tight loop on error if one pin is problematic
                continue

        # Calculate time within the flash cycle
        cycle_time = (current_time - flash_start_time) % FLASH_DURATION
        is_on_phase = cycle_time < on_time

        # --- Update Display for Flashing ---
        screen.fill((0, 0, 0)) # Clear screen with black
        if is_on_phase and loaded_images_data[current_image_index][0]:
            screen.blit(loaded_images_data[current_image_index][0], loaded_images_data[current_image_index][1])
        pygame.display.flip()

        # Add a small delay to reduce CPU usage
        time.sleep(0.01)

    print("Exiting.")
    # --- Cleanup ---
    try:
        gpio.cleanup() # Clean up GPIO settings
        print("GPIO cleanup performed.")
    except Exception as cleanup_e:
        print(f"Error during GPIO cleanup: {cleanup_e}")
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    # pyA64.gpio often requires root access
    if os.geteuid() != 0:
        print("Warning: Not running as root. pyA64.gpio might require root access.")
        print("Consider running with sudo or configuring udev rules.")
        # Optionally sys.exit(1) if root is strictly required

    main()