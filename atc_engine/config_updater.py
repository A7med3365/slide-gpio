import threading
import time
import os
import shutil
import json
from typing import TYPE_CHECKING, Optional, Dict, Any

from .usb_handler import USBHandler
from .config_manager import ConfigManager # For validation

if TYPE_CHECKING:
    from .action_handler import ActionHandler

class ConfigUpdater:
    """
    Manages the process of updating application configuration and assets from a USB drive.
    """
    _STAGING_DIR_NAME = ".update_staging"
    _BACKUP_DIR_NAME = ".update_backup"
    _USB_PACKAGE_DIR_NAME = "atc_update_package" # As per USBHandler
    _USB_ASSETS_DIR_NAME = "assets"

    def __init__(self, action_handler_ref: 'ActionHandler', app_config_path: str):
        """
        Initializes the ConfigUpdater.

        Args:
            action_handler_ref: A reference to the ActionHandler for display feedback.
            app_config_path: Path to the application's current config.json.
        """
        self._action_handler_ref = action_handler_ref
        self._current_config_file_path = os.path.abspath(app_config_path)
        # Determine app_root_dir: parent of the directory containing config.json
        # e.g., if app_config_path is /path/to/project_root/atc_engine/config.json
        # then config_dir is /path/to/project_root/atc_engine
        # and app_root_dir is /path/to/project_root
        config_dir = os.path.dirname(self._current_config_file_path)
        self._app_root_dir = os.path.dirname(config_dir) # This assumes config.json is one level down from project root in a dir like 'atc_engine'

        # Determine assets_dir_name and current_assets_base_dir
        # Assets are in 'atc_engine/image_sets/' relative to project root.
        # self._app_root_dir is project_root
        self._assets_dir_name = os.path.join(os.path.basename(config_dir), "image_sets") # e.g., "atc_engine/image_sets"
        self._current_assets_base_dir = os.path.join(self._app_root_dir, self._assets_dir_name)

        self.usb_handler = USBHandler(package_name=self._USB_PACKAGE_DIR_NAME)
        self._update_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._config_manager = ConfigManager(self._current_config_file_path) # For validation logic

        print(f"[ConfigUpdater Init] App Root: {self._app_root_dir}")
        print(f"[ConfigUpdater Init] App Config Path: {self._current_config_file_path}")
        print(f"[ConfigUpdater Init] Assets Dir Name (relative to root): {self._assets_dir_name}")
        print(f"[ConfigUpdater Init] Current Assets Base Dir: {self._current_assets_base_dir}")


    def _display_message(self, message: str):
        """Helper to display messages via console and ActionHandler's ImageDisplay service."""
        print(f"[ConfigUpdater] {message}")
        if self._action_handler_ref and hasattr(self._action_handler_ref, 'image_display_service') and self._action_handler_ref.image_display_service:
            try:
                self._action_handler_ref.image_display_service.display_text(text=message)
            except Exception as e:
                print(f"[ConfigUpdater] Error displaying message on screen: {e}")
        else:
            print("[ConfigUpdater] ImageDisplay service not available for on-screen messages.")

    def _validate_usb_config(self, usb_config_path: str) -> Optional[dict]:
        """
        Uses ConfigManager to load and validate the config.json from the USB.
        Returns the loaded config data if valid, else None and displays an error.
        """
        try:
            # Use a temporary ConfigManager instance for validation to not interfere with main one
            temp_config_manager = ConfigManager(usb_config_path)
            config_data = temp_config_manager.load_config() # load_config also validates schema
            if config_data:
                # ConfigManager.validate_config_schema is called internally by load_config
                # We might add more specific content validation here if needed,
                # e.g., checking if asset paths look plausible before rewriting.
                # For now, schema validation is the primary check.
                self._display_message(f"USB config at '{usb_config_path}' seems valid.")
                return config_data
            else:
                self._display_message(f"Failed to load or validate USB config schema at '{usb_config_path}'.")
                return None
        except ValueError as ve: # ConfigManager raises ValueError for schema issues
            self._display_message(f"USB config validation error for '{usb_config_path}': {ve}")
            return None
        except Exception as e:
            self._display_message(f"Error validating USB config '{usb_config_path}': {e}")
            return None

    def _rewrite_config_paths(self, usb_config_data: dict, new_assets_prefix: str) -> dict:
        """
        Iterates through media items in usb_config_data.
        If a path exists and starts with self._USB_ASSETS_DIR_NAME + '/',
        it rewrites it to new_assets_prefix + path[len(self._USB_ASSETS_DIR_NAME + '/'):].
        Returns the modified config data (deep copy).
        """
        modified_config_data = json.loads(json.dumps(usb_config_data)) # Deep copy
        usb_assets_prefix_to_strip = self._USB_ASSETS_DIR_NAME + "/"

        for screen_config in modified_config_data.get("screens", []):
            for media_item in screen_config.get("media", []):
                if "path" in media_item and isinstance(media_item["path"], str):
                    if media_item["path"].startswith(usb_assets_prefix_to_strip):
                        relative_path = media_item["path"][len(usb_assets_prefix_to_strip):]
                        media_item["path"] = os.path.join(new_assets_prefix, relative_path)
                        # Ensure OS-agnostic paths in JSON, so use forward slashes
                        media_item["path"] = media_item["path"].replace(os.sep, '/')
        return modified_config_data

    def _gather_assets_from_config(self, config_data: dict) -> Dict[str, str]:
        """
        Parses config_data (from USB, before path rewriting).
        Identifies all unique asset file paths mentioned in media items
        (those starting with _USB_ASSETS_DIR_NAME).
        Returns a dictionary mapping relative_asset_path_in_package (e.g., set0/image.jpg)
        to its original path in the USB config (e.g., assets/set0/image.jpg).
        This helps in copying from the correct source later.
        """
        assets_map: Dict[str, str] = {} # relative_in_package -> original_usb_path
        usb_assets_prefix_to_check = self._USB_ASSETS_DIR_NAME + "/"

        for screen_config in config_data.get("screens", []):
            for media_item in screen_config.get("media", []):
                if "path" in media_item and isinstance(media_item["path"], str):
                    original_path = media_item["path"]
                    if original_path.startswith(usb_assets_prefix_to_check):
                        relative_path_in_package = original_path[len(usb_assets_prefix_to_check):]
                        if relative_path_in_package not in assets_map:
                            assets_map[relative_path_in_package] = original_path
        return assets_map

    def _perform_atomic_update(self, usb_package_path: str) -> bool:
        """
        Performs the atomic update of config.json and its assets.
        Manages staging, backup, copy, and commit/rollback.
        """
        # a. Setup Paths
        usb_config_file = os.path.join(usb_package_path, "config.json")
        usb_assets_dir = os.path.join(usb_package_path, self._USB_ASSETS_DIR_NAME)

        staging_dir = os.path.join(self._app_root_dir, self._STAGING_DIR_NAME)
        # Staged config will have the same name as the original app config file
        staging_config_file_basename = os.path.basename(self._current_config_file_path)
        staging_config_file = os.path.join(staging_dir, staging_config_file_basename)
        staging_config_file_temp = staging_config_file + ".tmp" # Work with a temp file first

        # Staging assets dir will mirror the structure of current assets dir relative to app root
        # e.g., if _assets_dir_name is "atc_engine/image_sets", staging_assets_dir will be ".update_staging/atc_engine/image_sets"
        staging_assets_dir = os.path.join(staging_dir, self._assets_dir_name)

        backup_dir = os.path.join(self._app_root_dir, self._BACKUP_DIR_NAME)
        backup_config_file = os.path.join(backup_dir, staging_config_file_basename + ".bak")
        backup_assets_dir = os.path.join(backup_dir, self._assets_dir_name + ".bak")

        self._display_message(f"Staging directory: {staging_dir}")
        self._display_message(f"Backup directory: {backup_dir}")

        try:
            # b. Cleanup and Create Staging
            self._display_message("Cleaning up and creating staging directory...")
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir)
            os.makedirs(staging_dir, exist_ok=True)
            # Also create the nested assets directory structure within staging
            os.makedirs(staging_assets_dir, exist_ok=True)


            # c. Validate USB Config
            self._display_message(f"Validating USB config: {usb_config_file}")
            if not os.path.exists(usb_config_file):
                self._display_message(f"USB config file '{usb_config_file}' not found.")
                shutil.rmtree(staging_dir, ignore_errors=True)
                return False
            
            usb_config_data = self._validate_usb_config(usb_config_file)
            if not usb_config_data:
                self._display_message("USB configuration validation failed.")
                shutil.rmtree(staging_dir, ignore_errors=True)
                return False

            # d. Gather Assets from USB Config
            self._display_message("Gathering asset list from USB config...")
            # assets_to_copy maps: relative_path_in_package (e.g. "set0/image.jpg") -> original_usb_path ("assets/set0/image.jpg")
            assets_to_copy = self._gather_assets_from_config(usb_config_data)
            if not assets_to_copy:
                self._display_message("No assets found or specified in the USB config starting with 'assets/'. Assuming config-only update or assets are not prefixed correctly.")
            else:
                self._display_message(f"Found {len(assets_to_copy)} assets to process.")


            # e. Copy to Staging (Config and Assets)
            self._display_message(f"Copying USB config to staging: {staging_config_file_temp}")
            shutil.copy2(usb_config_file, staging_config_file_temp)

            self._display_message(f"Copying assets to staging assets directory: {staging_assets_dir}")
            for rel_asset_path_in_pkg, _ in assets_to_copy.items():
                # Source path is relative to usb_assets_dir
                source_asset_on_usb = os.path.join(usb_assets_dir, rel_asset_path_in_pkg)
                # Destination path is relative to staging_assets_dir
                dest_asset_in_staging = os.path.join(staging_assets_dir, rel_asset_path_in_pkg)

                if not os.path.exists(source_asset_on_usb):
                    self._display_message(f"ERROR: Asset '{source_asset_on_usb}' specified in USB config not found in USB package.")
                    shutil.rmtree(staging_dir, ignore_errors=True)
                    return False

                self._display_message(f"Copying asset: {source_asset_on_usb} -> {dest_asset_in_staging}")
                os.makedirs(os.path.dirname(dest_asset_in_staging), exist_ok=True)
                shutil.copy2(source_asset_on_usb, dest_asset_in_staging)


            # f. Rewrite Paths in Staged Config
            self._display_message(f"Rewriting asset paths in staged config: {staging_config_file_temp}")
            with open(staging_config_file_temp, 'r') as f:
                staged_config_data = json.load(f)
            
            # The new prefix for assets will be self._assets_dir_name (e.g., "atc_engine/image_sets")
            rewritten_staged_config_data = self._rewrite_config_paths(staged_config_data, self._assets_dir_name)
            
            with open(staging_config_file_temp, 'w') as f:
                json.dump(rewritten_staged_config_data, f, indent=4)
            self._display_message("Asset paths rewritten in staged config.")


            # g. Final Validation of Staged Rewritten Config
            self._display_message(f"Validating rewritten staged config: {staging_config_file_temp}")
            # We use _validate_usb_config here as it uses a temporary ConfigManager
            # and checks the schema. Path existence is not checked by ConfigManager's validation.
            validated_staged_config = self._validate_usb_config(staging_config_file_temp)
            if not validated_staged_config:
                self._display_message("Rewritten staged configuration validation failed.")
                shutil.rmtree(staging_dir, ignore_errors=True)
                return False
            self._display_message("Rewritten staged config is valid.")


            # h. Backup Current Application Config and Assets
            self._display_message("Backing up current application config and assets...")
            if os.path.exists(backup_dir):
                shutil.rmtree(backup_dir)
            os.makedirs(backup_dir, exist_ok=True)
            
            # Backup config file
            if os.path.exists(self._current_config_file_path):
                self._display_message(f"Backing up {self._current_config_file_path} to {backup_config_file}")
                shutil.copy2(self._current_config_file_path, backup_config_file)
            else:
                self._display_message(f"Current config file {self._current_config_file_path} not found. Skipping backup of config file.")

            # Backup assets directory
            if os.path.exists(self._current_assets_base_dir):
                self._display_message(f"Backing up {self._current_assets_base_dir} to {backup_assets_dir}")
                shutil.copytree(self._current_assets_base_dir, backup_assets_dir, dirs_exist_ok=True) # dirs_exist_ok for robustness
            else:
                self._display_message(f"Current assets directory {self._current_assets_base_dir} not found. Skipping backup of assets.")
            self._display_message("Backup completed.")


            # i. Commit (Replace Current with Staged)
            self._display_message("Committing update: Replacing current files with staged files...")
            # This is the critical section. We aim for atomicity as much as possible.
            # Renaming/moving is generally atomic on the same filesystem.
            
            # 1. Replace assets directory
            #    Remove old assets, then move staged assets into place.
            if os.path.exists(self._current_assets_base_dir):
                self._display_message(f"Removing current assets directory: {self._current_assets_base_dir}")
                shutil.rmtree(self._current_assets_base_dir)
            
            self._display_message(f"Moving staged assets {staging_assets_dir} to {self._current_assets_base_dir}")
            # Ensure parent directory for _current_assets_base_dir exists before moving
            os.makedirs(os.path.dirname(self._current_assets_base_dir), exist_ok=True)
            shutil.move(staging_assets_dir, self._current_assets_base_dir)

            # 2. Replace config file
            #    Move staged config file (which was .tmp) to the final destination.
            self._display_message(f"Moving staged config {staging_config_file_temp} to {self._current_config_file_path}")
            shutil.move(staging_config_file_temp, self._current_config_file_path)
            
            self._display_message("Commit successful.")
            
            # j. Cleanup Staging Directory
            self._display_message(f"Cleaning up staging directory: {staging_dir}")
            shutil.rmtree(staging_dir, ignore_errors=True)
            
            return True

        except Exception as e:
            self._display_message(f"CRITICAL ERROR during update: {e}. Attempting rollback...")
            # Attempt to restore from backup
            try:
                # Restore config file
                if os.path.exists(backup_config_file):
                    self._display_message(f"Restoring config from backup: {backup_config_file} to {self._current_config_file_path}")
                    # Ensure target directory exists
                    os.makedirs(os.path.dirname(self._current_config_file_path), exist_ok=True)
                    shutil.copy2(backup_config_file, self._current_config_file_path) # copy2 to preserve metadata
                
                # Restore assets directory
                if os.path.exists(backup_assets_dir):
                    self._display_message(f"Restoring assets from backup: {backup_assets_dir} to {self._current_assets_base_dir}")
                    if os.path.exists(self._current_assets_base_dir):
                        shutil.rmtree(self._current_assets_base_dir) # Remove potentially corrupted current assets
                    # Ensure parent directory for _current_assets_base_dir exists
                    os.makedirs(os.path.dirname(self._current_assets_base_dir), exist_ok=True)
                    shutil.copytree(backup_assets_dir, self._current_assets_base_dir, dirs_exist_ok=True)
                
                self._display_message("Rollback from backup attempted.")
            except Exception as rb_e:
                self._display_message(f"CRITICAL ERROR during rollback: {rb_e}. System might be in an inconsistent state.")
            
            # Cleanup staging if it still exists
            if os.path.exists(staging_dir):
                shutil.rmtree(staging_dir, ignore_errors=True)
            return False


    def _update_thread_target(self): # Renamed from _run_update_process
        """
        The actual USB update logic that runs in a separate thread.
        Orchestrates mounting, validation, atomic update, and unmounting.
        """
        self._display_message("Checking for USB drive...")
        mount_point = None
        update_successful = False
        try:
            mount_point = self.usb_handler.mount_first_available_usb()

            if mount_point:
                self._display_message(f"USB drive mounted at: {mount_point}. Searching for update package '{self._USB_PACKAGE_DIR_NAME}'...")
                # find_config_package_on_usb now uses the package_name from USBHandler's init
                package_path = self.usb_handler.find_config_package_on_usb(mount_point)

                if package_path:
                    self._display_message(f"Update package found at: {package_path}. Starting update process...")
                    update_successful = self._perform_atomic_update(package_path)
                    
                    if update_successful:
                        self._display_message("Update successful! Please restart the application.")
                    else:
                        # _perform_atomic_update should have displayed detailed errors and handled rollback
                        self._display_message("Update failed. System should have rolled back to previous state.")
                else:
                    self._display_message(f"No valid '{self._USB_PACKAGE_DIR_NAME}/' found on the USB drive or it's not a directory.")
            else:
                self._display_message("No USB drive found or it could not be mounted.")

        except Exception as e:
            self._display_message(f"An error occurred during the USB update process: {e}")
            # Ensure a general failure message if not already set by _perform_atomic_update
            if not update_successful: # Check if it wasn't a failure within _perform_atomic_update
                 self._display_message("Update failed due to an unexpected error.")
        finally:
            if mount_point:
                self._display_message(f"Unmounting USB drive from {mount_point}...")
                if self.usb_handler.unmount_usb(mount_point):
                    self._display_message("USB drive unmounted. You can safely remove the drive.")
                else:
                    self._display_message(f"Failed to unmount USB drive from {mount_point}. Please check manually.")
            
            self._update_thread = None # Clear thread object
            self._display_message("USB update process finished.")


    def start_usb_update_process(self):
        """
        Starts the USB update process in a new thread to avoid blocking the main application.
        """
        if self._update_thread and self._update_thread.is_alive():
            self._display_message("Update process is already running.")
            return

        self._display_message("Initializing USB update sequence...")
        self._stop_event.clear()
        self._update_thread = threading.Thread(target=self._update_thread_target, daemon=True)
        self._update_thread.start()

    def stop_update_process(self):
        """Signals the update process to stop (currently mostly for preventing new starts)."""
        if self._update_thread and self._update_thread.is_alive():
            self._display_message("Attempting to signal the update process to stop...")
            self._stop_event.set()
            # Note: _update_thread_target and _perform_atomic_update would need
            # to periodically check self._stop_event for graceful premature termination.
            # This is not fully implemented for ongoing operations yet.

if __name__ == '__main__':
    # Mock ActionHandler and ImageDisplayService for testing
    class MockImageDisplayService:
        def display_text(self, text: str, **kwargs):
            print(f"[MockImageDisplayService] DISPLAY ON SCREEN: {text}")

    class MockActionHandler:
        def __init__(self):
            self.image_display_service = MockImageDisplayService()

        def display_text(self, text: str): # Fallback if service not directly called
            print(f"[MockActionHandler] ACTION_HANDLER_DISPLAY: {text}")

    print("Testing ConfigUpdater...")
    mock_action_handler = MockActionHandler()
    
    # Create a dummy project structure for testing
    test_project_root = "temp_test_project_root"
    test_atc_engine_dir = os.path.join(test_project_root, "atc_engine")
    test_app_config_path = os.path.join(test_atc_engine_dir, "config.json")
    test_assets_dir = os.path.join(test_atc_engine_dir, "image_sets")
    
    # Dummy current config.json
    dummy_current_config_content = {
        "screens": [
            {
                "name": "Screen 1",
                "media": [
                    {"type": "image", "path": "atc_engine/image_sets/set_current/current_img.jpg", "duration": 5}
                ]
            }
        ]
    }
    # Dummy USB update package
    dummy_usb_mount_point = "temp_usb_mount"
    dummy_usb_package_dir = os.path.join(dummy_usb_mount_point, ConfigUpdater._USB_PACKAGE_DIR_NAME)
    dummy_usb_config_path = os.path.join(dummy_usb_package_dir, "config.json")
    dummy_usb_assets_dir = os.path.join(dummy_usb_package_dir, ConfigUpdater._USB_ASSETS_DIR_NAME)
    dummy_usb_asset_rel_path = "set_new/new_img.jpg" # e.g. assets/set_new/new_img.jpg
    dummy_usb_asset_full_path_on_usb = os.path.join(dummy_usb_assets_dir, dummy_usb_asset_rel_path)

    dummy_usb_config_content = {
        "screens": [
            {
                "name": "Screen 1 Updated",
                "media": [
                    {"type": "image", "path": f"{ConfigUpdater._USB_ASSETS_DIR_NAME}/{dummy_usb_asset_rel_path}", "duration": 10}
                ]
            }
        ],
        "settings": {"version": "1.1"} # Ensure it passes schema validation if one exists
    }

    def setup_test_environment():
        print("Setting up test environment...")
        # Clean up previous test runs
        if os.path.exists(test_project_root): shutil.rmtree(test_project_root)
        if os.path.exists(dummy_usb_mount_point): shutil.rmtree(dummy_usb_mount_point)

        os.makedirs(test_atc_engine_dir, exist_ok=True)
        os.makedirs(test_assets_dir, exist_ok=True)
        os.makedirs(os.path.join(test_assets_dir, "set_current"), exist_ok=True) # for current_img.jpg
        
        with open(test_app_config_path, 'w') as f:
            json.dump(dummy_current_config_content, f, indent=4)
        with open(os.path.join(test_assets_dir, "set_current", "current_img.jpg"), 'w') as f:
            f.write("dummy current image data")

        os.makedirs(dummy_usb_package_dir, exist_ok=True)
        os.makedirs(os.path.dirname(dummy_usb_asset_full_path_on_usb), exist_ok=True)
        with open(dummy_usb_config_path, 'w') as f:
            json.dump(dummy_usb_config_content, f, indent=4)
        with open(dummy_usb_asset_full_path_on_usb, 'w') as f:
            f.write("dummy new image data")
        print(f"Test current config: {test_app_config_path}")
        print(f"Test USB package: {dummy_usb_package_dir}")

    def cleanup_test_environment():
        print("Cleaning up test environment...")
        if os.path.exists(test_project_root): shutil.rmtree(test_project_root)
        if os.path.exists(dummy_usb_mount_point): shutil.rmtree(dummy_usb_mount_point)


    # --- Test Scenario ---
    setup_test_environment()
    
    # Mock USBHandler methods for the test
    original_mount = USBHandler.mount_first_available_usb
    original_find_pkg = USBHandler.find_config_package_on_usb
    original_unmount = USBHandler.unmount_usb

    USBHandler.mount_first_available_usb = lambda self: dummy_usb_mount_point
    USBHandler.find_config_package_on_usb = lambda self, mount_point: dummy_usb_package_dir if mount_point == dummy_usb_mount_point else None
    USBHandler.unmount_usb = lambda self, mount_point: True

    updater = ConfigUpdater(action_handler_ref=mock_action_handler, app_config_path=test_app_config_path)
    
    # Mock ConfigManager's schema validation for simplicity in this test
    # In a real scenario, ConfigManager would have its own schema.
    # For this test, we'll assume any JSON is fine if it loads.
    def mock_load_config(self_cm):
        try:
            with open(self_cm.config_file_path, 'r') as f:
                data = json.load(f)
            # Basic check for "screens" key as a minimal validation for test
            if "screens" not in data:
                 raise ValueError("Mock schema validation: 'screens' key missing.")
            return data
        except json.JSONDecodeError:
            raise ValueError("Mock schema validation: Invalid JSON.")

    original_cm_load = ConfigManager.load_config
    ConfigManager.load_config = mock_load_config
    
    print("\nStarting USB update process (simulated with mocks)...")
    updater.start_usb_update_process()
    
    print("Main thread waiting for update thread to complete...")
    if updater._update_thread:
        updater._update_thread.join(timeout=60)

    if updater._update_thread and updater._update_thread.is_alive():
         print("Update thread is still alive after timeout.")
    else:
         print("Update thread has finished.")

    print("\nVerifying update results...")
    if os.path.exists(test_app_config_path):
        with open(test_app_config_path, 'r') as f:
            try:
                updated_config = json.load(f)
                print(f"Updated app config content: {json.dumps(updated_config, indent=2)}")
                expected_asset_path = f"{updater._assets_dir_name}/{dummy_usb_asset_rel_path}".replace(os.sep, '/')
                actual_asset_path = updated_config["screens"][0]["media"][0]["path"]
                if actual_asset_path == expected_asset_path:
                    print(f"SUCCESS: Asset path correctly rewritten to {expected_asset_path}")
                else:
                    print(f"FAILURE: Asset path is {actual_asset_path}, expected {expected_asset_path}")
            except Exception as e:
                print(f"Error reading updated config: {e}")
    else:
        print("FAILURE: Updated app config file not found.")

    expected_final_asset_path = os.path.join(updater._current_assets_base_dir, dummy_usb_asset_rel_path)
    if os.path.exists(expected_final_asset_path):
        print(f"SUCCESS: Updated asset found at {expected_final_asset_path}")
        with open(expected_final_asset_path, 'r') as f:
            if f.read() == "dummy new image data":
                 print("SUCCESS: Asset content is correct.")
            else:
                 print("FAILURE: Asset content is incorrect.")
    else:
        print(f"FAILURE: Updated asset not found at {expected_final_asset_path}")
        print(f"Current assets base dir: {updater._current_assets_base_dir}")
        print(f"App root dir: {updater._app_root_dir}")
        print(f"Assets dir name: {updater._assets_dir_name}")


    # Restore original mocked methods
    USBHandler.mount_first_available_usb = original_mount
    USBHandler.find_config_package_on_usb = original_find_pkg
    USBHandler.unmount_usb = original_unmount
    ConfigManager.load_config = original_cm_load

    cleanup_test_environment()
    print("\nConfigUpdater test finished.")