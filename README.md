# AppImgMon

A Python utility to monitor directories for AppImages on Linux systems and automatically create desktop entries for seamless integration with desktop environments.

## Features

- **Automatic Desktop Entry Creation**: Integrates AppImages with the desktop environment
- **Icon Extraction**: Automatically extracts icons from AppImage files
- **Desktop Shortcut Support**: Generates shortcuts on the desktop
- **Systemd User Service**: Runs as a lightweight background service
- **Self-cleaning**: Removes obsolete desktop entries when AppImages are deleted

## Requirements

- Python 3.6 or higher
- Linux system with systemd
- Standard Linux desktop environment

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/AppImgMon.git
   cd AppImgMon
   ```

2. Make the script executable:
   ```bash
   chmod +x AppImgMon.py
   ```

3. Install the user service:
   ```bash
   ./AppImgMon.py --install
   ```

## Configuration

The following environment variables can be customized:

| Variable | Description | Default |
|----------|-------------|---------|
| `APPIMAGE_WATCH_DIR` | Directory to monitor for AppImages | `~/appimages` |
| `DESKTOP_ENTRY_DIR` | Directory to store .desktop entries | `~/.local/share/applications` |
| `ICON_DIR` | Directory to save extracted icons | `~/.local/share/icons` |

## Usage

1. Create the watch directory:
   ```bash
   mkdir -p ~/appimages
   ```

2. Place your `.AppImage` files in the watch directory.

3. Manage the service:
   ```bash
   # Check service status
   systemctl --user status appimgmon.service

   # Start the service
   systemctl --user start appimgmon.service

   # Stop the service
   systemctl --user stop appimgmon.service
   ```

## Uninstallation

1. Stop and disable the service:
   ```bash
   systemctl --user stop appimgmon.service
   systemctl --user disable appimgmon.service
   ```

2. Remove service and configuration files:
   ```bash
   rm ~/.config/systemd/user/appimgmon.service
   rm ~/appimages/AppImgMon.py
   rm ~/.local/share/applications/AppImg*.desktop
   rm ~/Desktop/AppImg*.desktop
   ```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request on our GitHub repository.

## License

This project is licensed under the MIT License.

## Support

For issues or feature requests, please file a ticket on the GitHub repository.