#!/usr/bin/env python3

import pygame
import os
import sys
import argparse
import time

# --- Configuration ---
FLASH_DURATION = 1.5  # Total time for one flash cycle in seconds (e.g., 1.0)
FLASH_DUTY_CYCLE = 0.8  # Proportion of FLASH_DURATION for which image is visible (e.g., 0.75)
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp'] # Common image extensions

def find_image_files(directory):
    """Recursively finds image files in a directory."""
    image_files = []
    if not os.path.isdir(directory):
        print(f"Error: Directory '{directory}' not found.", file=sys.stderr)
        return image_files # Return empty list

    for root, _, files in os.walk(directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                image_files.append(os.path.join(root, file))
    return image_files

def load_and_scale_image(file_path, screen_size):
    """Loads an image, scales it to fit the screen while maintaining aspect ratio, and returns the scaled image and its centered position."""
    try:
        img = pygame.image.load(file_path) # Keep original format for GIFs
    except pygame.error as e:
        print(f"Error loading image {file_path}: {e}", file=sys.stderr)
        return None, None

    img_rect = img.get_rect()
    screen_width, screen_height = screen_size

    # Calculate scaling factor preserving aspect ratio
    scale_w = screen_width / img_rect.width
    scale_h = screen_height / img_rect.height
    scale_factor = min(scale_w, scale_h)

    new_width = int(img_rect.width * scale_factor)
    new_height = int(img_rect.height * scale_factor)

    try:
        img_scaled = pygame.transform.smoothscale(img, (new_width, new_height))
    except ValueError: # Fallback for formats not supporting smoothscale well initially
        img_scaled = pygame.transform.scale(img, (new_width, new_height))


    # Calculate centered position
    pos_x = (screen_width - new_width) // 2
    pos_y = (screen_height - new_height) // 2

    return img_scaled, (pos_x, pos_y)

def main():
    """Main function to parse arguments and display images with Pygame."""
    parser = argparse.ArgumentParser(description="Display images in a flashing slideshow using Pygame.")
    parser.add_argument("image_directory", help="Path to the folder containing images.")
    parser.add_argument("--duration", type=float, default=FLASH_DURATION,
                        help=f"Total time for one flash cycle in seconds (default: {FLASH_DURATION}).")
    parser.add_argument("--duty_cycle", type=float, default=FLASH_DUTY_CYCLE,
                        help=f"Proportion of flash duration image is visible (0.0-1.0, default: {FLASH_DUTY_CYCLE}).")

    args = parser.parse_args()

    if not (0.0 < args.duty_cycle <= 1.0):
        print("Error: Duty cycle must be between 0.0 (exclusive) and 1.0 (inclusive).", file=sys.stderr)
        sys.exit(1)

    flash_duration_actual = args.duration
    flash_duty_cycle_actual = args.duty_cycle

    print(f"Searching for images in: {args.image_directory}")
    image_files = find_image_files(args.image_directory)
    image_files.sort()

    if not image_files:
        if os.path.isdir(args.image_directory): # Directory exists but no images
            print(f"No image files found in '{args.image_directory}'.", file=sys.stderr)
        # If find_image_files already printed "directory not found", no need to repeat
        sys.exit(1)

    print(f"Found {len(image_files)} images.")

    pygame.init()

    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    screen_info = pygame.display.Info()
    screen_size = (screen_info.current_w, screen_info.current_h)
    pygame.mouse.set_visible(False)
    pygame.display.set_caption("Flashing Slideshow")

    print("Loading and scaling images...")
    loaded_images_data = []
    for img_file in image_files:
        img_data, pos = load_and_scale_image(img_file, screen_size)
        if img_data:
            loaded_images_data.append({'surface': img_data, 'pos': pos, 'path': img_file})
        else:
            print(f"Warning: Could not load or scale image '{img_file}'. Skipping.")

    if not loaded_images_data:
        print("No images could be loaded successfully. Exiting.", file=sys.stderr)
        pygame.quit()
        sys.exit(1)

    print(f"Successfully loaded {len(loaded_images_data)} images.")
    print(f"Starting slideshow. Flash Duration: {flash_duration_actual}s, Duty Cycle: {flash_duty_cycle_actual*100}%.")
    print("Press ESC to quit.")

    current_image_index = 0
    running = True
    on_time = flash_duration_actual * flash_duty_cycle_actual
    off_time = flash_duration_actual * (1 - flash_duty_cycle_actual)

    image_display_start_time = time.time() # Time when the current image started its flash cycle

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

        current_time = time.time()
        time_since_flash_cycle_start = current_time - image_display_start_time

        current_image_info = loaded_images_data[current_image_index]

        if time_since_flash_cycle_start < on_time:
            # Display image phase
            screen.fill((0, 0, 0)) # Black background
            screen.blit(current_image_info['surface'], current_image_info['pos'])
        elif time_since_flash_cycle_start < (on_time + off_time):
            # Black screen phase
            screen.fill((0, 0, 0))
        else:
            # End of flash cycle for current image, move to next
            current_image_index = (current_image_index + 1) % len(loaded_images_data)
            image_display_start_time = time.time() # Reset timer for the new image
            # Immediately display the new image (or start its "on" phase)
            screen.fill((0, 0, 0))
            current_image_info = loaded_images_data[current_image_index] # update info
            screen.blit(current_image_info['surface'], current_image_info['pos'])


        pygame.display.flip()
        pygame.time.wait(10) # Small delay to prevent high CPU usage, adjust as needed

    print("Exiting slideshow.")
    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()