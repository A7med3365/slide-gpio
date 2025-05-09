import subprocess
import os
import sys
import argparse
import time
import signal
import glob

# Set up argument parser
parser = argparse.ArgumentParser(description="Display images from a folder as a slideshow using feh")
parser.add_argument("path", help="Path to the image file or folder containing images")
parser.add_argument("-d", "--delay", type=int, default=3, 
                    help="Delay between images in seconds (default: 3)")
args = parser.parse_args()

# Get the path from command-line argument
path = args.path
delay_seconds = args.delay

# Function to handle Ctrl+C gracefully
def signal_handler(sig, frame):
    print("\nSlideshow interrupted. Exiting...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Check if feh is installed (basic check)
try:
    subprocess.run(['which', 'feh'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
except (subprocess.CalledProcessError, FileNotFoundError):
    print("Error: 'feh' command not found.")
    print("Please install it using: sudo apt update && sudo apt install feh")
    sys.exit(1)

# Process path - could be a file or directory
if os.path.isfile(path):
    # Single file mode
    image_files = [path]
    print(f"Displaying single image: {path}")
elif os.path.isdir(path):
    # Directory mode - collect all image files
    image_extensions = ('*.jpg', '*.jpeg', '*.png', '*.gif', '*.bmp')
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(path, ext)))
        # Also search subdirectories
        image_files.extend(glob.glob(os.path.join(path, '**', ext), recursive=True))
    
    # Sort the files for consistent order
    image_files.sort()
    
    if not image_files:
        print(f"Error: No image files found in '{path}'")
        sys.exit(1)
    
    print(f"Found {len(image_files)} images in '{path}'")
else:
    print(f"Error: Path '{path}' does not exist or is not accessible")
    sys.exit(1)

# Function to run feh for slideshow
def show_slideshow(files):
    # Command to run feh in fullscreen mode with slideshow
    # --fullscreen: Display fullscreen
    # --auto-zoom: Zoom picture to fit screen geometry
    # --hide-pointer: Hide the mouse pointer
    # --borderless: Create a borderless window
    # --slideshow-delay: Delay between automatically changing slides in slideshow mode (conditional)
    # --quiet: Don't report non-fatal errors for specified files
    
    command_parts = [
        'feh',
        '--fullscreen',
        '--auto-zoom',
        '--hide-pointer',
        '--borderless',
    ]
    
    # Conditionally add slideshow delay.
    # For single GIFs, feh handles animation natively if --slideshow-delay is omitted.
    # For multiple files or non-GIF single files, the delay is applied.
    if not (len(files) == 1 and files[0].lower().endswith('.gif')):
        command_parts.extend(['--slideshow-delay', str(delay_seconds)])
    
    command_parts.append('--quiet')
    command = command_parts + files
    
    print("Starting slideshow...")
    print("Press 'q' or 'ESC' to exit, space to pause/unpause, arrow keys to navigate.")
    
    try:
        # Run feh. This will take over until feh is closed.
        subprocess.run(command, check=True)
        print("Slideshow finished.")
    except subprocess.CalledProcessError as e:
        print(f"Error running feh: {e}")
    except KeyboardInterrupt:
        print("\nExiting slideshow.")

# Start the slideshow
if image_files:
    show_slideshow(image_files)