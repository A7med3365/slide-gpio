import subprocess
import json
import os
import time # Import time for a small delay

def check_and_mount_usb():
    """
    Checks if a removable block device (like a USB drive) is plugged in.
    If found and not mounted, attempts to mount the first partition.

    Returns:
        list: A list of mount points for detected and/or newly mounted
              USB drives, or an empty list.
    """
    usb_mount_points = []
    lsblk_path = "/usr/bin/lsblk" # Use the determined path
    mount_path = "/usr/bin/mount" # Path to the mount command
    target_mount_point = "/mnt/usb" # Directory to mount the USB drive

    # Ensure the target mount point exists
    if not os.path.exists(target_mount_point):
        print(f"Mount point directory {target_mount_point} does not exist. Creating it...")
        try:
            # Need root privileges to create directory in /mnt
            subprocess.run(['sudo', 'mkdir', '-p', target_mount_point], check=True)
            # Give the system a moment to create the directory
            time.sleep(0.5)
        except subprocess.CalledProcessError as e:
            print(f"Error creating mount point directory {target_mount_point}: {e}")
            return [] # Cannot proceed without mount point

    try:
        # Run lsblk command to list block devices in JSON format
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

        found_unmounted_removable_partition = None

        # Iterate through the block devices to find removable ones
        for device in data.get('blockdevices', []):
            is_removable = device.get('rm') == True
            device_name = device.get('name')
            mount_point = device.get('mountpoint')

            print(f"Checking device: {device_name}, Removable: {is_removable}, Mountpoint: {mount_point}")

            if is_removable:
                # Check if the device itself is mounted (less common for bare devices)
                if mount_point:
                    print(f"Found mounted removable device: {device_name} at {mount_point}")
                    usb_mount_points.append(mount_point)

                # Check children (partitions) if the parent device is removable
                if 'children' in device:
                    print(f"Checking children of removable device: {device_name}")
                    for child in device['children']:
                        child_name = child.get('name')
                        child_mount_point = child.get('mountpoint')
                        print(f"  Checking child: {child_name}, Mountpoint: {child_mount_point}")

                        if child_mount_point:
                             # Found a mounted partition of a removable device
                             print(f"  Found mounted partition: {child_name} at {child_mount_point}")
                             usb_mount_points.append(child_mount_point)
                        elif found_unmounted_removable_partition is None:
                             # Found an unmounted partition of a removable device
                             # Store the first one found to attempt mounting later
                             print(f"  Found unmounted removable partition: {child_name}")
                             found_unmounted_removable_partition = child_name


        # If an unmounted removable partition was found, attempt to mount it
        if found_unmounted_removable_partition:
            print(f"\nAttempting to mount {found_unmounted_removable_partition} to {target_mount_point}...")
            try:
                # Need root privileges to mount
                mount_command = [mount_path, found_unmounted_removable_partition, target_mount_point]
                print(f"Running command: sudo {' '.join(mount_command)}")
                subprocess.run(['sudo'] + mount_command, check=True)
                print(f"Successfully mounted {found_unmounted_removable_partition} to {target_mount_point}.")
                # Add the newly mounted point to the list
                usb_mount_points.append(target_mount_point)

                # Optional: Re-run lsblk to confirm the mount point is now listed
                # print("\n--- Re-running lsblk after mount attempt ---")
                # result_after_mount = subprocess.run(
                #     [lsblk_path, '-o', 'NAME,MOUNTPOINT,RM', '-p', '-J'],
                #     capture_output=True, text=True, check=True
                # )
                # print(result_after_mount.stdout)
                # print("------------------------------------------\n")

            except FileNotFoundError:
                 print(f"Error: '{mount_path}' command not found. Is it installed?")
            except subprocess.CalledProcessError as e:
                 print(f"Error mounting {found_unmounted_removable_partition}: {e}")
                 print(f"Mount command output (stderr):\n{e.stderr}")
            except Exception as e:
                 print(f"An unexpected error occurred during mounting: {e}")


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

    # Return unique mount points found (including any newly mounted ones)
    return list(set(usb_mount_points))

if __name__ == "__main__":
    print("Checking for and attempting to mount plugged USB drives...")
    mounted_usbs = check_and_mount_usb()

    if mounted_usbs:
        print("\nUSB drive(s) detected and mounted at:")
        for mount_point in mounted_usbs:
            print(f"- {mount_point}")
            # Optional: List files in the first detected USB mount point for verification
            # if os.path.isdir(mount_point):
            #     print(f"  Files in {mount_point}: {os.listdir(mount_point)}")
    else:
        print("\nNo mounted USB drive detected or could not be mounted.")

