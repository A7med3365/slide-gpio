import subprocess
import json
import os

def check_usb_mounted():
    """
    Checks if a removable block device (like a USB drive) is plugged in
    and currently mounted.

    Returns:
        list: A list of mount points for detected USB drives, or an empty list.
    """
    usb_mount_points = []
    lsblk_path = "/usr/bin/lsblk" # Use the determined path

    try:
        # Run lsblk command to list block devices in JSON format
        # -o NAME,MOUNTPOINT,RM: Output device name, mount point, and removable status
        # -p: Use full device path
        # -J: Output in JSON format
        print(f"Running command: {lsblk_path} -o NAME,MOUNTPOINT,RM -p -J")
        result = subprocess.run(
            [lsblk_path, '-o', 'NAME,MOUNTPOINT,RM', '-p', '-J'],
            capture_output=True,
            text=True,
            check=True # Raise an exception if the command fails
        )

        print("\n--- Raw lsblk Output (stdout) ---")
        print(result.stdout)
        print("---------------------------------\n")

        data = json.loads(result.stdout)

        print("--- Parsed JSON Data ---")
        print(json.dumps(data, indent=2)) # Print with indentation for readability
        print("------------------------\n")


        # Iterate through the block devices
        for device in data.get('blockdevices', []):
            # Check if the device is removable ('RM' is '1')
            is_removable = device.get('rm') == True
            mount_point = device.get('mountpoint')

            print(f"Checking device: {device.get('name')}, Removable: {is_removable}, Mountpoint: {mount_point}")

            # We are primarily interested in mounted partitions of removable devices
            # Check children (partitions) if the parent device is removable
            if is_removable and 'children' in device:
                print(f"Checking children of removable device: {device.get('name')}")
                for child in device['children']:
                    child_mount_point = child.get('mountpoint')
                    print(f"  Checking child: {child.get('name')}, Mountpoint: {child_mount_point}")
                    # If the child (partition) has a mount point, add it
                    if child_mount_point:
                         print(f"  Found mounted partition: {child.get('name')} at {child_mount_point}")
                         usb_mount_points.append(child_mount_point)
            # Also check if the device itself is removable and mounted (less common for partitions, but possible)
            elif is_removable and mount_point:
                 print(f"Found mounted removable device (no children): {device.get('name')} at {mount_point}")
                 usb_mount_points.append(mount_point)


    except FileNotFoundError:
        print(f"Error: '{lsblk_path}' command not found. Is it installed?")
    except subprocess.CalledProcessError as e:
        print(f"Error running lsblk command: {e}")
        print(f"Command output (stderr):\n{e.stderr}")
    except json.JSONDecodeError:
        print("Error: Could not parse lsblk output as JSON.")
        print(f"Raw output was:\n{result.stdout}") # Print raw output if JSON decoding fails
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    # Return unique mount points
    return list(set(usb_mount_points))

if __name__ == "__main__":
    print("Checking for plugged USB drives...")
    mounted_usbs = check_usb_mounted()

    if mounted_usbs:
        print("\nUSB drive(s) detected and mounted at:")
        for mount_point in mounted_usbs:
            print(f"- {mount_point}")
            # Optional: List files in the first detected USB mount point for verification
            # if os.path.isdir(mount_point):
            #     print(f"  Files in {mount_point}: {os.listdir(mount_point)}")
    else:
        print("\nNo mounted USB drive detected.")

