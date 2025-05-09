#!/usr/bin/env python3

import argparse
import subprocess
import os
import signal
import sys

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']

def check_mpv_installed():
    """Checks if mpv is installed and exits if not."""
    try:
        result = subprocess.run(['which', 'mpv'], capture_output=True, text=True, check=True)
        if result.returncode != 0 or not result.stdout.strip():
            print("Error: 'mpv' command not found. Please install it (e.g., sudo apt install mpv).", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError: # which command not found
        print("Error: 'which' command not found. Cannot verify mpv installation.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError: # mpv not found by which
        print("Error: 'mpv' command not found. Please install it (e.g., sudo apt install mpv).", file=sys.stderr)
        sys.exit(1)

def find_image_files(directory):
    """Recursively finds image files in a directory."""
    image_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in IMAGE_EXTENSIONS:
                image_files.append(os.path.join(root, file))
    return image_files

def handle_sigint(signum, frame):
    """Handles SIGINT (Ctrl+C) for graceful exit."""
    print("\nExiting viewer...")
    sys.exit(0)

def main():
    """Main function to parse arguments and display images with mpv."""
    signal.signal(signal.SIGINT, handle_sigint)
    check_mpv_installed()

    parser = argparse.ArgumentParser(description="Display images and animated GIFs using mpv.")
    parser.add_argument("path", help="Path to an image file or a folder containing images.")
    parser.add_argument("-d", "--delay", type=int, default=3, help="Delay in seconds between images in slideshow mode (default: 3).")

    args = parser.parse_args()

    mpv_base_cmd = ['mpv', '--fs', '--no-osc']
    mpv_process = None

    if not os.path.exists(args.path):
        print(f"Error: Path '{args.path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        if os.path.isfile(args.path):
            print(f"Displaying image with mpv: {args.path}")
            mpv_cmd = mpv_base_cmd + ['--loop-file=inf', args.path]
            mpv_process = subprocess.run(mpv_cmd, check=False) # check=False to handle mpv's own exit codes

        elif os.path.isdir(args.path):
            image_files = find_image_files(args.path)
            if not image_files:
                print(f"Error: No image files found in directory '{args.path}'.", file=sys.stderr)
                sys.exit(1)

            print(f"Starting mpv slideshow for directory: {args.path} with {args.delay}s delay (looping indefinitely).")
            mpv_cmd = mpv_base_cmd + [f'--image-display-duration={args.delay}', '--loop-playlist=inf'] + image_files
            mpv_process = subprocess.run(mpv_cmd, check=False)

        else:
            print(f"Error: Path '{args.path}' is not a valid file or directory.", file=sys.stderr)
            sys.exit(1)

        if mpv_process and mpv_process.returncode != 0:
            # mpv might exit with non-zero on user quit (e.g. 'q'), this is not necessarily an error from our script's perspective
            # print(f"mpv exited with code: {mpv_process.returncode}", file=sys.stderr)
            pass

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        print("Viewer finished.")


if __name__ == "__main__":
    main()