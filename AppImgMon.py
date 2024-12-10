#!/usr/bin/env python3

import os
import sys
import time
import logging
from pathlib import Path
import subprocess
import shutil
import hashlib

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
    # Clean up both desktop dir and desktop shortcuts
    for location in [DESKTOP_DIR, DESKTOP_SHORTCUTS_DIR]:
        for desktop_file in location.glob("*.desktop"):
            try:
                with open(desktop_file) as f:
                    content = f.read()
                    if "X-AppImage-Path=" in content:
                        # Extract the AppImage path
                        for line in content.splitlines():
                            if line.startswith("X-AppImage-Path="):
                                appimage_path = Path(line.split("=", 1)[1].strip())
                                if not appimage_path.exists() or WATCH_DIR.as_posix() in content:
                                    desktop_file.unlink()
                                    logging.info(f"Removed obsolete .desktop file: {desktop_file}")
                                break
            except (IOError, OSError) as e:
                logging.error(f"Error cleaning up desktop file {desktop_file}: {e}")

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

def monitor_appimages():
    """Continuously monitor the directory for AppImage changes."""
    previous_files = set()
    processed_files = {}  # Keep track of processed files and their metadata
    
    while True:
        try:
            WATCH_DIR.mkdir(parents=True, exist_ok=True)
            DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
            ICON_DIR.mkdir(parents=True, exist_ok=True)

            current_files = {f for f in WATCH_DIR.iterdir() if f.suffix == ".AppImage"}
            new_files = current_files - previous_files
            removed_files = previous_files - current_files

            # Handle new AppImages
            for new_file in new_files:
                create_desktop_file(new_file)
                processed_files[new_file] = get_appimage_metadata(new_file)

            # Check for updates in existing files
            for existing_file in current_files & previous_files:
                desktop_file = DESKTOP_DIR / f"{existing_file.stem}.desktop"
                if needs_update(existing_file, desktop_file):
                    logging.info(f"Updating desktop entry for modified AppImage: {existing_file}")
                    create_desktop_file(existing_file)
                    processed_files[existing_file] = get_appimage_metadata(existing_file)

            # Handle removed AppImages
            if removed_files:
                clean_desktop_files()
                for removed_file in removed_files:
                    processed_files.pop(removed_file, None)

            previous_files = current_files
            
            # Verify script location periodically
            current_script = Path(sys.argv[0]).resolve()
            if current_script.parent != WATCH_DIR:
                logging.warning("Script not in watch directory, attempting to fix...")
                ensure_script_in_watch_dir()
                
        except Exception as e:
            logging.error(f"Error in monitor loop: {e}")
            
        time.sleep(5)

def install_user_service():
    """Install and enable the systemd user service."""
    # Ensure script is in watch directory
    script_path = ensure_script_in_watch_dir()
    
    service_content = f"""[Unit]
Description=AppImgMon - Monitor AppImage directory and generate .desktop files
After=default.target

[Service]
Environment="APPIMAGE_WATCH_DIR={WATCH_DIR}"
Environment="DESKTOP_ENTRY_DIR={DESKTOP_DIR}"
Environment="ICON_DIR={ICON_DIR}"
ExecStart={script_path}
Restart=always

[Install]
WantedBy=default.target
"""

    # Ensure ~/.config/systemd/user exists
    SERVICE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Write service file
    with open(SERVICE_FILE_PATH, "w") as f:
        f.write(service_content)
    logging.info(f"User service file created at {SERVICE_FILE_PATH}")

    # Enable and start the service
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", SERVICE_NAME])
    subprocess.run(["systemctl", "--user", "start", SERVICE_NAME])
    
    logging.info(f"User service installed and started successfully!")
    logging.info(f"The script is now monitoring: {WATCH_DIR}")
    logging.info(f"Desktop entries will be created in: {DESKTOP_DIR}")
    logging.info(f"Icons will be stored in: {ICON_DIR}")

if __name__ == "__main__":
    if "--install" in sys.argv:
        install_user_service()
    else:
        # If not in watch directory and not installing, exit
        current_script = Path(sys.argv[0]).resolve()
        if current_script.parent != WATCH_DIR and "--install" not in sys.argv:
            logging.error(f"Please run this script with --install first")
            sys.exit(1)
        monitor_appimages()
