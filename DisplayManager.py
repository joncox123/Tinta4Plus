"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

WARNING: This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects
that result in data loss, corruption, hardware damage or other issues. Use at your own risk.
It may temporarily or permanently render your hardware inoperable.
It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop.
The author is not responsible for any damage, data loss or lost productivity caused by use of this software. 
By downloading and using this software you agree to these terms and acknowledge the risks involved.
"""

import subprocess
import os
import time


class DisplayManager:
    """Manage display switching and configuration (no root required)"""

    # ThinkBook Plus Gen 4 IRU hardware specifications
    OLED_RESOLUTION_WH = [2880, 1800]
    EINK_RESOLUTION_WH = [2560, 1600]

    def __init__(self, logger):
        self.logger = logger
    
    def get_displays(self):
        """Get list of connected displays using xrandr"""
        try:
            result = subprocess.run(
                ['xrandr', '--query'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            displays = []
            for line in result.stdout.split('\n'):
                if ' connected' in line:
                    parts = line.split()
                    name = parts[0]
                    primary = 'primary' in line
                    displays.append({'name': name, 'primary': primary})
            
            return displays
            
        except Exception as e:
            self.logger.error(f"Failed to get displays: {e}")
            return []
    
    def is_display_active(self, display_name):
        """Check if a display is currently active (enabled and has geometry)"""
        try:
            result = subprocess.run(
                ['xrandr', '--query'],
                capture_output=True,
                text=True,
                timeout=5
            )

            for line in result.stdout.split('\n'):
                if display_name in line and ' connected' in line:
                    parts = line.split()
                    # Display is active if it has geometry info (e.g., 1920x1080+0+0)
                    # Look for pattern like "1920x1080+0+0" in the line
                    for part in parts:
                        if 'x' in part and '+' in part:
                            return True
                    return False

            return False

        except Exception as e:
            self.logger.error(f"Failed to check display status: {e}")
            return False

    def enable_display(self, display_name, scale=None):
        """Enable/turn on a display with optional scaling

        Args:
            display_name: Name of the display (e.g., 'eDP-1', 'eDP-2')
            scale: Optional scale factor (e.g., 1.60 means UI appears 1.6x larger, lower DPI)
                   Uses xrandr --scale with --panning to maintain full panel coverage.
                   This keeps touch input properly mapped.
        """
        try:
            # Determine native resolution based on display name
            # eDP-1 is OLED, eDP-2 is E-Ink on ThinkBook Plus Gen 4
            if display_name == "eDP-1":
                native_width, native_height = self.OLED_RESOLUTION_WH
            elif display_name == "eDP-2":
                native_width, native_height = self.EINK_RESOLUTION_WH
            else:
                self.logger.warning(f"Unknown display {display_name}, using auto mode")
                native_width, native_height = None, None

            # Build xrandr command
            cmd = ['xrandr', '--output', display_name]

            if native_width and native_height:
                # Always specify the exact mode for predictable behavior
                cmd.extend(['--mode', f'{native_width}x{native_height}'])

                if scale is not None and scale != 1.0:
                    # Our convention: scale=1.6 means "UI appears 1.6x larger" (lower effective DPI)
                    # xrandr convention: --scale 1.6 means "zoom out" (UI appears smaller)
                    # These are OPPOSITE, so we invert for xrandr
                    scale_inv = 1.0 / scale

                    # Calculate panning size (virtual desktop size)
                    # For our scale=1.6 (larger UI), we want SMALLER virtual desktop
                    # Virtual size = native / our_scale = native * scale_inv
                    panning_width = int(native_width * scale_inv)
                    panning_height = int(native_height * scale_inv)

                    # xrandr will scale UP this smaller virtual desktop to fill the physical panel
                    # We pass scale_inv to xrandr because it's inverted from our convention
                    cmd.extend(['--panning', f'{panning_width}x{panning_height}'])
                    cmd.extend(['--scale', f'{scale_inv}x{scale_inv}'])
                    self.logger.info(f"Scaling: virtual desktop {panning_width}x{panning_height}, "
                                   f"xrandr scale {scale_inv:.3f}x{scale_inv:.3f} (our scale={scale}), "
                                   f"physical {native_width}x{native_height}")
                else:
                    # No scaling - use native resolution with 1:1 scale
                    cmd.extend(['--panning', f'{native_width}x{native_height}'])
                    cmd.extend(['--scale', '1x1'])
            else:
                # Fallback to auto mode if we don't know the resolution
                cmd.append('--auto')

            # Run xrandr command (may produce spurious BadMatch errors on stderr)
            subprocess.run(
                cmd,
                capture_output=True,
                timeout=5
            )

            # Verify the display is actually enabled by checking its state
            # Give X11 a moment to apply the change
            time.sleep(0.2)

            if self.is_display_active(display_name):
                scale_info = f" with {scale}x scale" if scale and scale != 1.0 else ""
                self.logger.info(f"Enabled display: {display_name}{scale_info}")
                return True
            else:
                self.logger.error(f"Failed to enable display: {display_name} (display not active after command)")
                return False

        except Exception as e:
            self.logger.error(f"Failed to enable display: {e}")
            return False
    
    def disable_display(self, display_name):
        """Disable/turn off a display"""
        try:
            # Run xrandr command (may produce spurious BadMatch errors on stderr)
            subprocess.run(
                ['xrandr', '--output', display_name, '--off'],
                capture_output=True,
                timeout=5
            )

            # Verify the display is actually disabled by checking its state
            # Give X11 a moment to apply the change
            time.sleep(0.2)

            if not self.is_display_active(display_name):
                self.logger.info(f"Disabled display: {display_name}")
                return True
            else:
                self.logger.error(f"Failed to disable display: {display_name} (display still active after command)")
                return False

        except Exception as e:
            self.logger.error(f"Failed to disable display: {e}")
            return False

    def get_display_geometry(self, display_name):
        """Get the geometry (position and size) of a display using xrandr"""
        try:
            result = subprocess.run(
                ['xrandr', '--query'],
                capture_output=True,
                text=True,
                timeout=5
            )

            # Parse xrandr output to find the display geometry
            # Format: "eDP-2 connected 1200x1920+1920+0 ..."
            for line in result.stdout.split('\n'):
                if display_name in line and 'connected' in line:
                    # Look for the geometry pattern: WIDTHxHEIGHT+X+Y
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '+' in part:
                            # Parse geometry: 1200x1920+1920+0
                            geo = part.split('+')
                            size = geo[0].split('x')
                            width = int(size[0])
                            height = int(size[1])
                            x_offset = int(geo[1]) if len(geo) > 1 else 0
                            y_offset = int(geo[2]) if len(geo) > 2 else 0

                            return {
                                'width': width,
                                'height': height,
                                'x': x_offset,
                                'y': y_offset
                            }

            self.logger.warning(f"Could not find geometry for {display_name}")
            return None

        except Exception as e:
            self.logger.error(f"Failed to get display geometry: {e}")
            return None

    def display_fullscreen_image(self, display_name, image_path):
        """
        Display a fullscreen image on a specific display.
        Works on X11 using feh, or falls back to imv for Wayland support.

        Args:
            display_name: Name of the display (e.g., 'eDP-2')
            image_path: Path to the PNG image file

        Returns:
            subprocess.Popen object if successful, None otherwise
        """
        if not os.path.exists(image_path):
            self.logger.error(f"Image file not found: {image_path}")
            return None

        # Get display geometry
        geometry = self.get_display_geometry(display_name)
        if not geometry:
            self.logger.error(f"Could not determine geometry for {display_name}")
            return None

        self.logger.info(f"Display {display_name} geometry: {geometry['width']}x{geometry['height']}+{geometry['x']}+{geometry['y']}")

        # Try feh first (works great on X11)
        if self._command_exists('feh'):
            try:
                # feh command with fullscreen flag - simpler and more reliable
                # The --fullscreen flag should make feh a top-level window
                cmd = [
                    'feh',
                    '--fullscreen',           # Make it fullscreen
                    '--auto-zoom',            # Auto-zoom to fit
                    '--no-menus',             # No right-click menu
                    '--hide-pointer',         # Hide mouse cursor
                    image_path
                ]

                self.logger.info(f"Displaying fullscreen image on {display_name} using feh")
                process = subprocess.Popen(cmd)

                # Give it a moment to display
                time.sleep(0.5)

                return process

            except Exception as e:
                self.logger.error(f"Failed to display image with feh: {e}")

        # Try imv as fallback (works on both X11 and Wayland)
        elif self._command_exists('imv'):
            try:
                cmd = [
                    'imv',
                    '-f',  # fullscreen
                    image_path
                ]

                self.logger.info(f"Displaying image using imv (fullscreen mode)")
                self.logger.warning("imv may not position on correct display automatically")
                process = subprocess.Popen(cmd)

                time.sleep(0.5)
                return process

            except Exception as e:
                self.logger.error(f"Failed to display image with imv: {e}")

        else:
            self.logger.error("Neither feh nor imv is installed. Please install one:")
            self.logger.error("  For X11: sudo apt install feh")
            self.logger.error("  For Wayland: sudo apt install imv")
            return None

        return None

    def _command_exists(self, command):
        """Check if a command exists in PATH"""
        try:
            subprocess.run(
                ['which', command],
                capture_output=True,
                check=True,
                timeout=2
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False