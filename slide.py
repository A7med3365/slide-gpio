import os
import argparse
import signal
import sys
from PIL import Image, ImageTk
import tkinter as tk

class SlideShowApp:
    def __init__(self, root, image_folder):
        self.root = root
        self.image_folder = image_folder
        self.images = []
        self.current_image_index = 0
        self.delay = 3000 

        # Set up the Tkinter window
        self.root.title("Image Slideshow")
        
        # Set a reasonable window size (not fullscreen)
        self.window_width = 800
        self.window_height = 600
        self.root.geometry(f"{self.window_width}x{self.window_height}")
        
        # Center the window on the screen
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_cordinate = int((screen_width - self.window_width) / 2)
        y_cordinate = int((screen_height - self.window_height) / 2)
        self.root.geometry(f"+{x_cordinate}+{y_cordinate}")

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self.signal_handler)

        # Create a canvas for image display
        self.canvas = tk.Canvas(root, bg="black", highlightthickness=0)
        self.canvas.pack(expand=True, fill=tk.BOTH)

        # Load images from the folder
        self.load_images()

        # Wait for the window to update before showing the first image
        self.root.update_idletasks()
        
        # Start the slideshow
        self.show_next_image()

    def load_images(self):
        # Get a list of all files in the folder
        for filename in os.listdir(self.image_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                image_path = os.path.join(self.image_folder, filename)
                try:
                    image = Image.open(image_path)
                    self.images.append(image)
                except Exception as e:
                    print(f"Error loading image {filename}: {e}")

        if not self.images:
            print("No valid images found in the folder.")
            exit()

    def show_next_image(self):
        if self.images:
            # Update window size in case of resize
            updated_width = self.root.winfo_width()
            updated_height = self.root.winfo_height()
            
            # Use the configured dimensions if the window isn't properly sized yet
            if updated_width <= 1 or updated_height <= 1:
                updated_width = self.window_width
                updated_height = self.window_height
            
            # Get the next image
            image = self.images[self.current_image_index]

            # Resize the image to fit the window while preserving aspect ratio
            image_width, image_height = image.size
            width_ratio = updated_width / image_width
            height_ratio = updated_height / image_height
            scale_factor = min(width_ratio, height_ratio)
            
            # Calculate new dimensions preserving aspect ratio
            new_width = int(image_width * scale_factor)
            new_height = int(image_height * scale_factor)
            
            # Ensure dimensions are at least 1 pixel
            new_width = max(1, new_width)
            new_height = max(1, new_height)
            
            # Resize the image with preserved aspect ratio
            resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(resized_image)

            # Clear the canvas and draw the new image centered
            self.canvas.delete("all")
            
            # Calculate position to center the image in the window
            x_position = (updated_width - new_width) // 2
            y_position = (updated_height - new_height) // 2
            
            # Draw the image on the canvas
            self.canvas.create_image(x_position, y_position, anchor=tk.NW, image=self.photo)

            # Move to the next image
            self.current_image_index = (self.current_image_index + 1) % len(self.images)

            # Schedule the next image to be shown after 3 seconds
            self.root.after(self.delay, self.show_next_image)
        
    def signal_handler(self, sig, frame):
        # Handle Ctrl+C (SIGINT)
        print("\nExiting slideshow...")
        self.root.quit()
        self.root.destroy()
        sys.exit(0)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Image slideshow application")
    parser.add_argument("folder", help="Path to the folder containing images")
    args = parser.parse_args()

    # Validate if the folder exists
    if not os.path.isdir(args.folder):
        print(f"Error: The folder '{args.folder}' does not exist.")
        return

    # Create the Tkinter root window
    root = tk.Tk()

    # Start the slideshow app
    app = SlideShowApp(root, args.folder)

    # Start the Tkinter event loop
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\nExiting slideshow...")
        root.quit()
        root.destroy()

if __name__ == "__main__":
    main()
