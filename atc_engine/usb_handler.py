import subprocess
import json
import os
import time
from typing import Optional, List

class USBHandler:
    """
    Handles detection, mounting, and unmounting of USB drives,
    and searching for specific update packages on them.
    """
    LSBLK_PATH = "/usr/bin/lsblk"
    MOUNT_PATH = "/usr/bin/mount"
    UMOUNT_PATH = "/usr/bin/umount"
    DEFAULT_MOUNT_BASE = "/mnt/atc_usb_update" # Changed to avoid conflict with generic /mnt/usb

    def __init__(self, mount_point_base: str = DEFAULT_MOUNT_BASE):
        self.mount_point_base = mount_point_base
        # Ensure the base mount directory exists
        if not os.path.exists(self.mount_point_base):
            try:
                # print(f"Base mount directory {self.mount_point_base} does not exist. Creating it...")
                subprocess.run(['sudo', 'mkdir', '-p', self.mount_point_base], check=True, capture_output=True)
                # print(f"Successfully created base mount directory: {self.mount_point_base}")
            except subprocess.CalledProcessError as e:
                print(f"Error creating base mount directory {self.mount_point_base}: {e.stderr.decode().strip() if e.stderr else e}")
                # This is a significant issue, but constructor can't return error.
                # Methods using it will fail.

    def _get_dynamic_mount_point(self, device_name: str) -> str:
        """Generates a unique mount point path based on the device name."""
        # Sanitize device_name to be used in a path
        sanitized_device_name = os.path.basename(device_name) # e.g., sdb1 from /dev/sdb1
        return os.path.join(self.mount_point_base, sanitized_device_name)

    def mount_first_available_usb(self) -> Optional[str]:
        """
        Checks for removable block devices.
        If a removable partition is already mounted, returns its mount point.
        Otherwise, attempts to mount the first unmounted removable partition found.

        Returns:
            Optional[str]: The mount point if a USB drive is successfully
                           identified and mounted (or already mounted), else None.
        """
        try:
            result = subprocess.run(
                [self.LSBLK_PATH, '-o', 'NAME,MOUNTPOINT,RM,TYPE', '-p', '-J'],
                capture_output=True, text=True, check=True
            )
            data = json.loads(result.stdout)

            unmounted_removable_partitions: List[str] = []
            mounted_removable_mountpoints: List[str] = []

            for device in data.get('blockdevices', []):
                is_removable = device.get('rm') == True
                device_name = device.get('name')

                if is_removable:
                    # Check device itself (less common for partitions)
                    if device.get('mountpoint') and device.get('type') == 'disk': # Check if disk itself is mounted
                         # This is unusual, usually partitions are mounted.
                         # We prefer partition mounts.
                         pass

                    if 'children' in device:
                        for child in device['children']:
                            # We are interested in partitions
                            if child.get('type') == 'part':
                                child_name = child.get('name')
                                child_mount_point = child.get('mountpoint')
                                if child_mount_point:
                                    mounted_removable_mountpoints.append(child_mount_point)
                                else:
                                    unmounted_removable_partitions.append(child_name)
            
            # Prioritize already mounted removable partitions
            if mounted_removable_mountpoints:
                # print(f"Found already mounted removable partition: {mounted_removable_mountpoints[0]}")
                return mounted_removable_mountpoints[0]

            # If no mounted ones, try to mount the first unmounted one
            if unmounted_removable_partitions:
                partition_to_mount = unmounted_removable_partitions[0]
                target_mount_point = self._get_dynamic_mount_point(partition_to_mount)

                if not os.path.exists(target_mount_point):
                    try:
                        subprocess.run(['sudo', 'mkdir', '-p', target_mount_point], check=True, capture_output=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error creating mount point {target_mount_point}: {e.stderr.decode().strip() if e.stderr else e}")
                        return None
                
                # print(f"Attempting to mount {partition_to_mount} to {target_mount_point}...")
                try:
                    mount_command = ['sudo', self.MOUNT_PATH, partition_to_mount, target_mount_point]
                    subprocess.run(mount_command, check=True, capture_output=True)
                    # print(f"Successfully mounted {partition_to_mount} to {target_mount_point}.")
                    return target_mount_point
                except subprocess.CalledProcessError as e:
                    print(f"Error mounting {partition_to_mount}: {e.stderr.decode().strip() if e.stderr else e}")
                    # Clean up mount point if creation succeeded but mount failed
                    if os.path.exists(target_mount_point):
                        try:
                            subprocess.run(['sudo', 'rmdir', target_mount_point], check=False) # Best effort
                        except Exception:
                            pass # Ignore cleanup error
                    return None
            
            # print("No suitable removable USB partition found or could be mounted.")
            return None

        except FileNotFoundError as e:
            print(f"Error: Command not found ({e.filename}). Is it installed and in PATH?")
            return None
        except subprocess.CalledProcessError as e:
            print(f"Error running lsblk: {e.stderr.decode().strip() if e.stderr else e}")
            return None
        except json.JSONDecodeError:
            print("Error: Could not parse lsblk output as JSON.")
            return None
        except Exception as e:
            print(f"An unexpected error occurred in mount_first_available_usb: {e}")
            return None

    def unmount_usb(self, mount_point: str) -> bool:
        """
        Unmounts the USB drive at the given mount point.

        Args:
            mount_point (str): The mount point to unmount.

        Returns:
            bool: True if unmount was successful or not mounted, False otherwise.
        """
        if not mount_point or not os.path.ismount(mount_point):
            # print(f"Mount point {mount_point} is not valid or not currently mounted.")
            return True # Considered success if not mounted

        # print(f"Attempting to unmount {mount_point}...")
        try:
            umount_command = ['sudo', self.UMOUNT_PATH, mount_point]
            subprocess.run(umount_command, check=True, capture_output=True)
            # print(f"Successfully unmounted {mount_point}.")
            
            # Attempt to remove the mount point directory if it's under our base and empty
            if mount_point.startswith(self.mount_point_base):
                try:
                    if not os.listdir(mount_point): # Check if empty
                        subprocess.run(['sudo', 'rmdir', mount_point], check=False, capture_output=True)
                        # print(f"Successfully removed mount point directory {mount_point}.")
                except Exception as e_rmdir:
                    # print(f"Could not remove mount point directory {mount_point}: {e_rmdir}")
                    pass # Non-critical
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error unmounting {mount_point}: {e.stderr.decode().strip() if e.stderr else e}")
            return False
        except FileNotFoundError as e_fnf:
            print(f"Error: umount command not found ({e_fnf.filename}). Is it installed?")
            return False
        except Exception as e_unx:
            print(f"An unexpected error occurred during unmount: {e_unx}")
            return False

    def find_config_package_on_usb(self, mount_point: str) -> Optional[str]:
        """
        Checks for 'atc_update_package/' directory with 'config.json'
        and 'assets/' subdirectory at the given USB mount point.

        Args:
            mount_point (str): The mount point of the USB drive.

        Returns:
            Optional[str]: Path to 'atc_update_package/' if found and valid, else None.
        """
        if not mount_point or not os.path.isdir(mount_point):
            # print(f"Mount point {mount_point} is not a valid directory.")
            return None

        package_dir_name = "atc_update_package"
        expected_config_file = "config.json"
        expected_assets_dir = "assets"

        package_path = os.path.join(mount_point, package_dir_name)
        config_file_path = os.path.join(package_path, expected_config_file)
        assets_dir_path = os.path.join(package_path, expected_assets_dir)

        # print(f"Checking for package at: {package_path}")
        if not os.path.isdir(package_path):
            # print(f"Directory not found: {package_path}")
            return None

        # print(f"Checking for config file: {config_file_path}")
        if not os.path.isfile(config_file_path):
            # print(f"Config file not found: {config_file_path}")
            return None

        # print(f"Checking for assets directory: {assets_dir_path}")
        if not os.path.isdir(assets_dir_path):
            # print(f"Assets directory not found: {assets_dir_path}")
            return None

        # print(f"Valid update package found at: {package_path}")
        return package_path

if __name__ == '__main__':
    print("Testing USBHandler...")
    handler = USBHandler()

    print("\nAttempting to mount USB...")
    active_mount_point = handler.mount_first_available_usb()

    if active_mount_point:
        print(f"USB mounted at: {active_mount_point}")

        print(f"\nSearching for update package on {active_mount_point}...")
        package = handler.find_config_package_on_usb(active_mount_point)
        if package:
            print(f"Update package found: {package}")
        else:
            print("No valid update package found.")

        # Test unmount
        # input("Press Enter to attempt unmount...") # For manual testing
        print(f"\nAttempting to unmount {active_mount_point}...")
        if handler.unmount_usb(active_mount_point):
            print(f"Unmount successful or was not mounted: {active_mount_point}")
        else:
            print(f"Unmount failed for {active_mount_point}")
    else:
        print("No USB drive could be mounted or found.")

    print("\nTest with a non-existent mount point for unmount:")
    handler.unmount_usb("/mnt/nonexistentfakepoint")
    
    print("\nUSBHandler test finished.")