#!/usr/bin/env python3

import os
import sys
import time
import logging
from pathlib import Path
import subprocess
import shutil
import hashlib
import pyinotify

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# Configuration
CREATE_DESKTOP_SHORTCUTS = True  # Set to True to create shortcuts on the desktop
WATCH_DIR = Path(os.getenv("APPIMAGE_WATCH_DIR", "~/appimages")).expanduser().resolve()
DESKTOP_DIR = Path(os.getenv("DESKTOP_ENTRY_DIR", "~/.local/share/applications")).expanduser().resolve()
ICON_DIR = Path(os.getenv("ICON_DIR", "~/.local/share/icons")).expanduser().resolve()
DESKTOP_SHORTCUTS_DIR = Path("~/Desktop").expanduser().resolve()

SERVICE_NAME = "appimgmon.service"
SERVICE_FILE_PATH = Path(f"~/.config/systemd/user/{SERVICE_NAME}").expanduser()

def ensure_script_in_watch_dir():
    """Ensure the script is in the watch directory and return its path."""
    current_script = Path(sys.argv[0]).resolve()
    target_script = WATCH_DIR / "AppImgMon.py"
    
    # Create watch directory if it doesn't exist
    WATCH_DIR.mkdir(parents=True, exist_ok=True)
    
    # If script is not in watch directory, copy it there
    if current_script != target_script:
        shutil.copy2(current_script, target_script)
        os.chmod(target_script, 0o755)  # Make executable
        logging.info(f"Copied script to {target_script}")
    
    return target_script

def extract_icon(appimage_path, app_name):
    """Extract icon from AppImage using common locations and formats."""
    # Supported icon formats
    icon_formats = [".png", ".svg", ".xpm", ".jpg", ".jpeg", ".ico"]
    icon_resolutions = ["512x512", "256x256", "128x128", "64x64", "48x48", "32x32"]
    
    # Try to find an existing icon first
    for fmt in icon_formats:
        icon_path = ICON_DIR / f"{app_name}{fmt}"
        if icon_path.exists():
            return icon_path
    
    # Default to PNG for new icons
    icon_path = ICON_DIR / f"{app_name}.png"
    
    try:
        # Extract AppImage contents
        subprocess.run([str(appimage_path), "--appimage-extract"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        squashfs_root = Path("squashfs-root")
        
        if not squashfs_root.exists():
            logging.warning(f"Failed to extract {appimage_path}")
            return "application-x-executable"
        
        # Common icon locations to check
        base_locations = [
            ".",  # Root directory
            "usr/share/icons/hicolor/{resolution}/apps",
            "usr/share/icons/default/{resolution}/apps",
            "usr/share/icons",
            "usr/share/pixmaps",
            ".local/share/icons",
            f"opt/{app_name}/icons",
            "AppRun",
        ]
        
        icon_found = False
        
        # First, try to find icons with the app name
        for base_loc in base_locations:
            if icon_found:
                break
                
            # Handle resolution placeholder
            if "{resolution}" in base_loc:
                for res in icon_resolutions:
                    loc = Path(base_loc.format(resolution=res))
                    for fmt in icon_formats:
                        icon_file = squashfs_root / loc / f"{app_name}{fmt}"
                        if icon_file.exists():
                            shutil.copy2(icon_file, icon_path)
                            icon_found = True
                            logging.info(f"Found and copied icon from {icon_file} to {icon_path}")
                            break
            else:
                # Try without resolution
                loc = Path(base_loc)
                for fmt in icon_formats:
                    icon_file = squashfs_root / loc / f"{app_name}{fmt}"
                    if icon_file.exists():
                        shutil.copy2(icon_file, icon_path)
                        icon_found = True
                        logging.info(f"Found and copied icon from {icon_file} to {icon_path}")
                        break
        
        # If no app-named icon found, try common icon names
        if not icon_found:
            common_icon_names = [".DirIcon", "icon.png", "icon.svg", "app.png", "app.svg", "application.png", "logo.png"]
            for base_loc in base_locations:
                if icon_found:
                    break
                    
                # Skip resolution-based paths for common names
                if "{resolution}" in base_loc:
                    continue
                    
                loc = Path(base_loc)
                for icon_name in common_icon_names:
                    icon_file = squashfs_root / loc / icon_name
                    if icon_file.exists():
                        shutil.copy2(icon_file, icon_path)
                        icon_found = True
                        logging.info(f"Found and copied icon from {icon_file} to {icon_path}")
                        break
        
    except Exception as e:
        logging.error(f"Error extracting icon from {appimage_path}: {str(e)}")
        return "application-x-executable"
    finally:
        # Clean up extracted files
        if Path("squashfs-root").exists():
            try:
                shutil.rmtree("squashfs-root")
            except Exception as e:
                logging.error(f"Failed to clean up squashfs-root: {str(e)}")
    
    # Return the icon path or fallback
    if icon_found:
        return icon_path
    else:
        logging.warning(f"No icon found for {app_name}, using fallback")
        return "application-x-executable"

def validate_desktop_shortcut(desktop_file_path):
    """Validate and fix desktop shortcut permissions and content."""
    try:
        if not desktop_file_path.exists():
            return False
            
        # Check permissions
        current_perms = os.stat(desktop_file_path).st_mode & 0o777
        if current_perms != 0o755:
            os.chmod(desktop_file_path, 0o755)
            
        # Validate content
        with open(desktop_file_path, 'r') as f:
            content = f.read()
            if not all(key in content for key in ['[Desktop Entry]', 'Type=Application', 'Exec=', 'Icon=']):
                return False
                
        return True
    except Exception as e:
        logging.error(f"Error validating desktop shortcut {desktop_file_path}: {e}")
        return False

def create_desktop_file(appimage_path):
    """Generate a .desktop file for the given AppImage."""
    try:
        appimage_name = appimage_path.name
        app_name = appimage_path.stem
        desktop_file_path = DESKTOP_DIR / f"{app_name}.desktop"
        
        # Extract icon
        icon_path = extract_icon(appimage_path, app_name)
        
        # Calculate unique identifier for the AppImage
        with open(appimage_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:8]
        
        # Generate the .desktop entry with additional metadata
        desktop_content = f"""[Desktop Entry]
Type=Application
Name={app_name}
Exec="{appimage_path}" %F
Icon={icon_path}
Terminal=false
Comment=AppImage application
Categories=Utility;
MimeType=application/x-executable;
X-AppImage-Version=1.0
X-AppImage-Path={appimage_path}
X-AppImage-Hash={file_hash}
X-AppImage-LastUpdate={int(time.time())}
"""
        # Write the .desktop file
        with open(desktop_file_path, "w") as f:
            f.write(desktop_content)
        os.chmod(desktop_file_path, 0o755)  # Make the .desktop file executable
        logging.info(f"Created .desktop file for {app_name} at {desktop_file_path}")
        
        # Create desktop shortcut if enabled
        if CREATE_DESKTOP_SHORTCUTS:
            desktop_shortcut = DESKTOP_SHORTCUTS_DIR / f"{app_name}.desktop"
            try:
                shutil.copy2(desktop_file_path, desktop_shortcut)
                os.chmod(desktop_shortcut, 0o755)  # Make the desktop shortcut executable
                
                if validate_desktop_shortcut(desktop_shortcut):
                    logging.info(f"Created and validated desktop shortcut at {desktop_shortcut}")
                else:
                    logging.warning(f"Desktop shortcut created but validation failed: {desktop_shortcut}")
                    
            except (IOError, OSError) as e:
                logging.error(f"Failed to create desktop shortcut for {app_name}: {e}")
                
    except Exception as e:
        logging.error(f"Failed to create desktop entry for {appimage_path}: {e}")

def clean_desktop_files():
    """Remove .desktop files for AppImages that no longer exist."""
    logging.info("Starting cleanup of desktop files...")
    removed_count = 0
    
    # Clean up both desktop dir and desktop shortcuts
    for location in [DESKTOP_DIR, DESKTOP_SHORTCUTS_DIR]:
        logging.info(f"Checking directory: {location}")
        for desktop_file in location.glob("*.desktop"):
            try:
                with open(desktop_file) as f:
                    content = f.read()
                    if "X-AppImage-Path=" in content:
                        # Extract the AppImage path
                        for line in content.splitlines():
                            if line.startswith("X-AppImage-Path="):
                                appimage_path = Path(line.split("=", 1)[1].strip())
                                if not appimage_path.exists():
                                    logging.info(f"Removing desktop file for missing AppImage: {appimage_path}")
                                    logging.info(f"Deleting: {desktop_file}")
                                    desktop_file.unlink()
                                    removed_count += 1
                                    break
            except (IOError, OSError) as e:
                logging.error(f"Error cleaning up desktop file {desktop_file}: {e}")
    
    logging.info(f"Cleanup complete. Removed {removed_count} desktop files.")

def monitor_appimages():
    """Monitor the directory for AppImage changes using inotify."""
    class EventHandler(pyinotify.ProcessEvent):
        def process_default(self, event):
            """Only log specific events we care about"""
            if any(x in event.maskname for x in ['IN_CREATE', 'IN_DELETE', 'IN_MODIFY', 'IN_MOVED']):
                logging.debug(f"Received event: {event.maskname} for {event.pathname}")

        def process_IN_CREATE(self, event):
            if event.pathname.endswith('.AppImage'):
                path = Path(event.pathname)
                logging.debug(f"CREATE event detected: {event.pathname}")
                logging.info(f"New AppImage detected: {path}")
                create_desktop_file(path)

        def process_IN_DELETE(self, event):
            if event.pathname.endswith('.AppImage'):
                path = Path(event.pathname)
                logging.debug(f"DELETE event detected: {event.pathname}")
                logging.info(f"AppImage removed: {path}")
                logging.info("Initiating desktop file cleanup...")
                clean_desktop_files()
                logging.info("Desktop file cleanup completed")

        def process_IN_MODIFY(self, event):
            if event.pathname.endswith('.AppImage'):
                path = Path(event.pathname)
                desktop_file = DESKTOP_DIR / f"{path.stem}.desktop"
                if needs_update(path, desktop_file):
                    logging.debug(f"MODIFY event detected: {event.pathname}")
                    logging.info(f"AppImage modified: {path}")
                    create_desktop_file(path)

        def process_IN_MOVED_FROM(self, event):
            if event.pathname.endswith('.AppImage'):
                path = Path(event.pathname)
                logging.debug(f"MOVED_FROM event detected: {event.pathname}")
                logging.info(f"AppImage moved/renamed from: {path}")
                clean_desktop_files()

        def process_IN_MOVED_TO(self, event):
            if event.pathname.endswith('.AppImage'):
                path = Path(event.pathname)
                logging.debug(f"MOVED_TO event detected: {event.pathname}")
                logging.info(f"AppImage moved/renamed to: {path}")
                create_desktop_file(path)

    try:
        # Initialize inotify
        wm = pyinotify.WatchManager()
        handler = EventHandler()
        notifier = pyinotify.Notifier(wm, handler)

        # Add watch with necessary events
        mask = (pyinotify.IN_CREATE | 
                pyinotify.IN_DELETE | 
                pyinotify.IN_MODIFY | 
                pyinotify.IN_MOVED_FROM | 
                pyinotify.IN_MOVED_TO | 
                pyinotify.IN_DELETE_SELF |
                pyinotify.IN_MOVE_SELF)
        
        watch_path = str(WATCH_DIR)
        logging.info(f"Setting up watch on {watch_path}")
        
        # Add the watch and check the result
        watch_id = wm.add_watch(watch_path, mask)
        if watch_path not in watch_id or watch_id[watch_path] < 0:
            logging.error(f"Failed to add watch for {watch_path}: {watch_id}")
            sys.exit(1)

        # Process existing AppImages first
        logging.info("Processing existing AppImages...")
        for appimage in WATCH_DIR.glob("*.AppImage"):
            desktop_file = DESKTOP_DIR / f"{appimage.stem}.desktop"
            if needs_update(appimage, desktop_file):
                create_desktop_file(appimage)

        # Clean up any stale desktop files
        logging.info("Performing initial cleanup...")
        clean_desktop_files()

        logging.info(f"Starting inotify watch loop on {WATCH_DIR}")
        notifier.loop()

    except Exception as e:
        logging.error(f"Error in monitor loop: {str(e)}")
        logging.error(f"Error details:", exc_info=True)
        sys.exit(1)

def get_appimage_metadata(appimage_path):
    """Get metadata for an AppImage including modification time and hash."""
    try:
        mtime = os.path.getmtime(appimage_path)
        with open(appimage_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()[:8]
        return {'mtime': mtime, 'hash': file_hash}
    except Exception as e:
        logging.error(f"Error getting metadata for {appimage_path}: {e}")
        return None

def needs_update(appimage_path, desktop_file_path):
    """Check if the desktop file needs to be updated."""
    if not desktop_file_path.exists():
        return True
        
    try:
        # Get current AppImage metadata
        current_metadata = get_appimage_metadata(appimage_path)
        if not current_metadata:
            return True
            
        # Read existing desktop file
        with open(desktop_file_path, 'r') as f:
            content = f.read()
            
        # Extract stored hash and timestamp
        stored_hash = None
        stored_time = None
        for line in content.splitlines():
            if line.startswith('X-AppImage-Hash='):
                stored_hash = line.split('=')[1]
            elif line.startswith('X-AppImage-LastUpdate='):
                stored_time = float(line.split('=')[1])
                
        if not stored_hash or not stored_time:
            return True
            
        # Check if metadata matches
        return (stored_hash != current_metadata['hash'] or 
                abs(stored_time - current_metadata['mtime']) > 1)  # 1 second tolerance
                
    except Exception as e:
        logging.error(f"Error checking update status for {appimage_path}: {e}")
        return True

def debug_systemd_service():
    """Debug systemd service status and configuration."""
    try:
        # Check if systemd is running
        systemd_status = subprocess.run(
            ["systemctl", "--user", "status"],
            capture_output=True, text=True
        )
        logging.info("Systemd user service status:")
        logging.info(systemd_status.stdout)

        # Check service file existence and permissions
        if SERVICE_FILE_PATH.exists():
            perms = oct(SERVICE_FILE_PATH.stat().st_mode)[-3:]
            logging.info(f"Service file exists with permissions {perms}")
            with open(SERVICE_FILE_PATH, 'r') as f:
                logging.info("Service file contents:")
                logging.info(f.read())
        else:
            logging.error("Service file does not exist!")

        # Check service status
        service_status = subprocess.run(
            ["systemctl", "--user", "status", SERVICE_NAME],
            capture_output=True, text=True
        )
        logging.info("Service status output:")
        logging.info(service_status.stdout)
        if service_status.stderr:
            logging.error("Service status errors:")
            logging.error(service_status.stderr)

        # Check journal logs
        journal_logs = subprocess.run(
            ["journalctl", "--user", "-u", SERVICE_NAME, "-n", "50", "--no-pager"],
            capture_output=True, text=True
        )
        logging.info("Recent service logs:")
        logging.info(journal_logs.stdout)

        return True
    except Exception as e:
        logging.error(f"Debug error: {str(e)}")
        return False

def install_user_service():
    """Install and enable the systemd user service."""
    try:
        # Ensure script is in watch directory
        script_path = ensure_script_in_watch_dir()
        
        # Verify Python executable
        python_path = shutil.which('python3')
        if not python_path:
            logging.error("Could not find python3 executable!")
            return False

        logging.info(f"Using Python executable: {python_path}")
        logging.info(f"Script path: {script_path}")
        
        service_content = f"""[Unit]
Description=AppImgMon - Monitor AppImage directory and generate .desktop files
After=default.target

[Service]
Type=simple
Environment="APPIMAGE_WATCH_DIR={WATCH_DIR}"
Environment="DESKTOP_ENTRY_DIR={DESKTOP_DIR}"
Environment="ICON_DIR={ICON_DIR}"
Environment="PYTHONUNBUFFERED=1"
ExecStart={python_path} {script_path}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
# Set to info level for normal operation
LogLevelMax=info

[Install]
WantedBy=default.target
"""

        # Ensure ~/.config/systemd/user exists
        SERVICE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write service file
        with open(SERVICE_FILE_PATH, "w") as f:
            f.write(service_content)
        os.chmod(SERVICE_FILE_PATH, 0o644)  # Set correct permissions
        logging.info(f"Service file created at {SERVICE_FILE_PATH}")

        try:
            # Stop service if running
            subprocess.run(["systemctl", "--user", "stop", SERVICE_NAME], 
                         stderr=subprocess.DEVNULL)
        except Exception as e:
            logging.warning(f"Failed to stop existing service: {e}")

        try:
            # Enable and start the service
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            logging.info("Daemon reloaded successfully")
            
            subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME], check=True)
            logging.info("Service enabled successfully")
            
            subprocess.run(["systemctl", "--user", "start", SERVICE_NAME], check=True)
            logging.info("Service started successfully")

        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to configure service: {e}")
            debug_systemd_service()
            return False

        # Wait a moment for service to start
        time.sleep(2)

        # Verify service status
        result = subprocess.run(["systemctl", "--user", "is-active", SERVICE_NAME],
                              capture_output=True, text=True)
        
        if result.stdout.strip() == "active":
            logging.info("Service installed and running successfully!")
            logging.info(f"Monitoring directory: {WATCH_DIR}")
            logging.info(f"Desktop entries: {DESKTOP_DIR}")
            logging.info(f"Icons: {ICON_DIR}")
            return True
        else:
            logging.error("Service installation failed!")
            debug_systemd_service()
            return False

    except Exception as e:
        logging.error(f"Unexpected error during service installation: {e}")
        debug_systemd_service()
        return False

if __name__ == "__main__":
    if "--install" in sys.argv:
        success = install_user_service()
        if not success:
            logging.error("Service installation failed. Check the logs above for details.")
            sys.exit(1)
    elif "--debug" in sys.argv:
        debug_systemd_service()
    else:
        # Check if script is in watch directory
        current_script = Path(sys.argv[0]).resolve()
        if current_script.parent != WATCH_DIR:
            logging.warning(f"Script is not in the watch directory ({WATCH_DIR})")
            logging.info("Installing service automatically...")
            success = install_user_service()
            if not success:
                logging.error("Automatic service installation failed. Please run with --install flag.")
                sys.exit(1)
            sys.exit(0)
        monitor_appimages()
