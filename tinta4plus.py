#!/usr/bin/env python3
"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

WARNING: This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects
that result in data loss, corruption, hardware damage or other issues. Use at your own risk.
It may temporarily or permanently render your hardware inoperable.
It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop.
The author is not responsible for any damage, data loss or lost productivity caused by use of this software. 
By downloading and using this software you agree to these terms and acknowledge the risks involved.
"""

"""
ThinkBook Plus Gen 4 IRU E-Ink Control GUI (tkinter version)
Unprivileged GUI that communicates with privileged helper daemon

No root/sudo required for this GUI
Communicates via Unix socket with helper daemon
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import os
import time
import threading
import logging
from datetime import datetime

from HelperClient import HelperClient
from DisplayManager import DisplayManager
from WacomManager import WacomManager


class EInkControlGUI:
    # Configuration
    SOCKET_PATH = '/tmp/tinta4plus.sock'
    KEEPALIVE_INTERVAL = 2.4  # seconds (send keepalive every 2.4s, watchdog is 20s)
    SOCKET_TIMEOUT = 5.0  # seconds

    # Display names (ThinkBook Plus Gen 4 has eDP-1=OLED, eDP-2=E-Ink)
    DISPLAY_OLED = "eDP-1"
    DISPLAY_EINK = "eDP-2"

    """Main GUI application using tkinter"""
    
    def __init__(self, root, HELPER_SCRIPT, logger):
        self.HELPER_SCRIPT = HELPER_SCRIPT
        self.logger = logger
        self.root = root
        self.root.title("ThinkBook E-Ink Control")
        self.root.geometry("600x700")
        
        # Helper client
        self.helper = HelperClient(logger)
        self.keepalive_after_id = None
        self.helper_process = None
        
        # Managers
        self.display_mgr = DisplayManager(logger)
        self.wacom_mgr = WacomManager(logger)
        
        # Brightness timer for debouncing
        self.brightness_timer = None
        
        # Build UI
        self.build_ui()
        
        # Set up window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Initialize helper after short delay
        self.root.after(500, self.initialize_helper)
    
    def build_ui(self):
        """Build the tkinter user interface"""
        
        # Configure style
        style = ttk.Style()
        style.theme_use('clam')  # Modern look
        
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        row = 0
        
        # Status bar
        self.status_var = tk.StringVar(value="Status: Initializing...")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_label.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        row += 1
        
        # === Display Control Section ===
        display_frame = ttk.LabelFrame(main_frame, text="Display Control", padding="10")
        display_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        display_frame.columnconfigure(0, weight=1)
        display_frame.columnconfigure(1, weight=1)
        row += 1
        
        # E-Ink / OLED buttons
        self.btn_enable_eink = ttk.Button(display_frame, text="Switch to E-Ink", 
                                          command=self.on_enable_eink)
        self.btn_enable_eink.grid(row=0, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        self.btn_enable_oled = ttk.Button(display_frame, text="Switch to OLED", 
                                          command=self.on_enable_oled)
        self.btn_enable_oled.grid(row=0, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        # Refresh buttons
        self.btn_refresh = ttk.Button(display_frame, text="Full Refresh (Clear Ghost)", 
                                      command=self.on_refresh_full)
        self.btn_refresh.grid(row=1, column=0, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        self.btn_refresh_quick = ttk.Button(display_frame, text="Quick Refresh", 
                                            command=self.on_refresh_quick)
        self.btn_refresh_quick.grid(row=1, column=1, padx=5, pady=5, sticky=(tk.W, tk.E))
        
        # Display enable/disable controls
        display_control_frame = ttk.Frame(display_frame)
        display_control_frame.grid(row=2, column=0, columnspan=2, padx=5, pady=(10, 5), sticky=(tk.W, tk.E))
        display_control_frame.columnconfigure(0, weight=1)
        display_control_frame.columnconfigure(1, weight=1)
        
        # OLED display control
        oled_control = ttk.Frame(display_control_frame)
        oled_control.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        
        ttk.Label(oled_control, text="OLED (eDP-1):").pack(side=tk.LEFT, padx=(0, 5))
        self.oled_enabled_var = tk.BooleanVar(value=True)
        oled_check = ttk.Checkbutton(oled_control, text="Enable", 
                                    variable=self.oled_enabled_var,
                                    command=self.on_oled_toggled)
        oled_check.pack(side=tk.LEFT)
        
        # E-Ink display control
        eink_control = ttk.Frame(display_control_frame)
        eink_control.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 0))
        
        ttk.Label(eink_control, text="E-Ink (eDP-2):").pack(side=tk.LEFT, padx=(0, 5))
        self.eink_display_var = tk.BooleanVar(value=True)
        eink_check = ttk.Checkbutton(eink_control, text="Enable", 
                                    variable=self.eink_display_var,
                                    command=self.on_eink_display_toggled)
        eink_check.pack(side=tk.LEFT)
        
        # === Frontlight Control Section ===
        frontlight_frame = ttk.LabelFrame(main_frame, text="Frontlight Control", padding="10")
        frontlight_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        frontlight_frame.columnconfigure(1, weight=1)
        row += 1
        
        # Power toggle
        ttk.Label(frontlight_frame, text="Power:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.frontlight_var = tk.BooleanVar(value=False)
        frontlight_check = ttk.Checkbutton(frontlight_frame, text="Enable", 
                                          variable=self.frontlight_var,
                                          command=self.on_frontlight_toggled)
        frontlight_check.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Brightness slider
        ttk.Label(frontlight_frame, text="Brightness (0-8):").grid(row=1, column=0, 
                                                                    sticky=tk.W, padx=5, pady=5)
        
        brightness_container = ttk.Frame(frontlight_frame)
        brightness_container.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        brightness_container.columnconfigure(0, weight=1)
        
        self.brightness_var = tk.IntVar(value=4)
        self.brightness_scale = ttk.Scale(brightness_container, from_=0, to=8, 
                                         orient=tk.HORIZONTAL,
                                         variable=self.brightness_var,
                                         command=self.on_brightness_changed)
        self.brightness_scale.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        self.brightness_label = ttk.Label(brightness_container, text="4")
        self.brightness_label.grid(row=0, column=1, padx=(5, 0))
        
        # === Touch Control Section ===
        touch_frame = ttk.LabelFrame(main_frame, text="Touch Input Control", padding="10")
        touch_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        touch_frame.columnconfigure(1, weight=1)
        row += 1
        
        # E-Ink touch control
        ttk.Label(touch_frame, text="E-Ink Touch (Goodix):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.eink_touch_var = tk.BooleanVar(value=True)
        eink_touch_check = ttk.Checkbutton(touch_frame, text="Enable", 
                                          variable=self.eink_touch_var,
                                          command=self.on_eink_touch_toggled)
        eink_touch_check.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # OLED touch control
        ttk.Label(touch_frame, text="OLED Touch (Wacom):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.oled_touch_var = tk.BooleanVar(value=True)
        oled_touch_check = ttk.Checkbutton(touch_frame, text="Enable", 
                                          variable=self.oled_touch_var,
                                          command=self.on_oled_touch_toggled)
        oled_touch_check.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        info_label = ttk.Label(touch_frame, text="Separate control for touch input on each display",
                              font=('TkDefaultFont', 8))
        info_label.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(5, 0))
        
        # === Activity Log Section ===
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=row, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(row, weight=1)
        row += 1
        
        # Scrolled text widget
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, wrap=tk.WORD,
                                                   state=tk.DISABLED, font=('Courier', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure text tags for colored output
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('error', foreground='red')
        self.log_text.tag_config('info', foreground='blue')
        
        # Initial log message
        self.log_message("Application started")
    
    def log_message(self, message, level='info'):
        """Add a message to the log view"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Determine tag based on message content or level
        if '✓' in message or 'success' in message.lower():
            tag = 'success'
        elif '✗' in message or 'error' in message.lower() or 'failed' in message.lower():
            tag = 'error'
        else:
            tag = level
        
        log_line = f"[{timestamp}] {message}\n"
        
        # Insert into text widget
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, log_line, tag)
        self.log_text.see(tk.END)  # Auto-scroll
        self.log_text.config(state=tk.DISABLED)
    
    def update_status(self, message, error=False):
        """Update status bar"""
        self.status_var.set(f"Status: {message}")
    
    def show_error_dialog(self, message):
        """Show error dialog"""
        messagebox.showerror("Error", message)
    
    def show_info_dialog(self, message):
        """Show info dialog"""
        messagebox.showinfo("Information", message)
    
    def initialize_helper(self):
        """Initialize connection to helper daemon"""
        # First try to connect to existing helper
        if os.path.exists(self.SOCKET_PATH):
            try:
                if self.helper.connect(self.SOCKET_PATH, timeout=2.0):
                    self.update_status("Connected to helper daemon")
                    self.log_message("Connected to existing helper daemon")
                    self.start_keepalive()
                    return
            except Exception as e:
                self.log_message(f"Failed to connect to existing socket: {e}")
                # Remove stale socket
                try:
                    os.remove(self.SOCKET_PATH)
                except:
                    pass
        
        # No existing helper, launch it
        self.log_message("Helper daemon not found, launching...")
        self.update_status("Launching helper daemon (password required)...")
        
        # Launch helper via pkexec in background
        threading.Thread(target=self._launch_helper_thread, daemon=True).start()
    
    def _launch_helper_thread(self):
        """Launch helper daemon in background thread"""
        try:
            # Determine helper script path
            helper_path = self.HELPER_SCRIPT
            
            # If not installed, try relative to this script
            if not os.path.exists(helper_path):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                helper_path = os.path.join(script_dir, 'thinkbook-eink-helper.py')
            
            if not os.path.exists(helper_path):
                self.root.after(0, self._helper_launch_failed, "Helper script not found")
                return
            
            # Launch via pkexec (will show password prompt)
            self.helper_process = subprocess.Popen(
                ['pkexec', 'python3', helper_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Wait a moment for helper to start
            time.sleep(1.5)
            
            # Try to connect
            max_attempts = 10
            for attempt in range(max_attempts):
                if os.path.exists(self.SOCKET_PATH):
                    if self.helper.connect(self.SOCKET_PATH, timeout=2.0):
                        self.root.after(0, self._helper_launch_success)
                        return
                time.sleep(0.5)
            
            self.root.after(0, self._helper_launch_failed, 
                          "Helper started but socket not available")
            
        except Exception as e:
            self.root.after(0, self._helper_launch_failed, str(e))
    
    def _helper_launch_success(self):
        """Called when helper successfully launched"""
        self.update_status("Connected to helper daemon")
        self.log_message("Helper daemon launched successfully")
        self.start_keepalive()
    
    def _helper_launch_failed(self, error):
        """Called when helper launch failed"""
        self.update_status(f"Failed to launch helper: {error}", error=True)
        self.log_message(f"ERROR: Failed to launch helper - {error}", level='error')
        self.show_error_dialog(
            f"Failed to launch helper daemon:\n\n{error}\n\n"
            "Make sure you entered the correct password."
        )
    
    def start_keepalive(self):
        """Start periodic keepalive messages"""
        if self.keepalive_after_id:
            self.root.after_cancel(self.keepalive_after_id)
        
        self.keepalive_after_id = self.root.after(
            int(self.KEEPALIVE_INTERVAL * 1000),
            self.send_keepalive
        )
        self.logger.info(f"Started keepalive timer ({self.KEEPALIVE_INTERVAL}s interval)")
    
    def send_keepalive(self):
        """Send keepalive message to helper"""
        if not self.helper.is_connected():
            self.update_status("Helper disconnected - attempting restart...", error=True)
            self.log_message("Helper disconnected, attempting to restart...", level='error')
            self.attempt_helper_restart()
            return  # Don't schedule next keepalive
        
        try:
            response = self.helper.send_command('keepalive')
            if not response or not response.get('success'):
                self.logger.warning("Keepalive failed")
                self.log_message("Keepalive failed, restarting helper...", level='error')
                self.attempt_helper_restart()
                return
            
            # Schedule next keepalive
            self.keepalive_after_id = self.root.after(
                int(self.KEEPALIVE_INTERVAL * 1000),
                self.send_keepalive
            )
            
        except Exception as e:
            self.logger.error(f"Keepalive error: {e}")
            self.update_status("Helper connection lost - restarting...", error=True)
            self.log_message(f"ERROR: Lost connection to helper - {e}", level='error')
            self.attempt_helper_restart()
    
    def attempt_helper_restart(self):
        """Attempt to restart the helper daemon"""
        # Cancel any existing keepalive
        if self.keepalive_after_id:
            self.root.after_cancel(self.keepalive_after_id)
            self.keepalive_after_id = None
        
        self.log_message("Attempting to restart helper daemon...")
        
        # Try to connect to existing socket first
        if os.path.exists(self.SOCKET_PATH):
            try:
                if self.helper.connect(self.SOCKET_PATH, timeout=2.0):
                    self.log_message("✓ Reconnected to existing helper")
                    self.update_status("Reconnected to helper daemon")
                    self.start_keepalive()
                    return
            except:
                pass
        
        # Need to launch new helper
        self.log_message("Launching new helper daemon (password may be required)...")
        self.update_status("Launching helper daemon...")
        threading.Thread(target=self._launch_helper_thread, daemon=True).start()
    
    def execute_helper_command(self, command, **params):
        """Execute a command via helper and handle response"""
        if not self.helper.is_connected():
            self.show_error_dialog("Not connected to helper daemon")
            return None
        
        try:
            response = self.helper.send_command(command, **params)
            
            if response and response.get('success'):
                message = response.get('message', 'Command completed')
                self.log_message(f"✓ {message}")
                
                # Log readback value if present
                if 'readback' in response:
                    self.log_message(f"  Readback value: {response['readback']}")
                
                return response
            else:
                error = response.get('error', 'Unknown error') if response else 'No response'
                self.log_message(f"✗ Command failed: {error}", level='error')
                self.show_error_dialog(f"Command failed:\n\n{error}")
                return None
                
        except Exception as e:
            self.log_message(f"✗ Command error: {e}", level='error')
            self.show_error_dialog(f"Command error:\n\n{e}")
            return None
    
    # === Event Handlers ===
    
    def on_enable_eink(self):
        """Switch to E-Ink display"""
        self.log_message("Switching to E-Ink display...")
        response = self.execute_helper_command('enable-eink')
        if response:
            self.update_status("E-Ink display active")
    
    def on_enable_oled(self):
        """Switch to OLED display"""
        self.log_message("Switching to OLED display...")
        response = self.execute_helper_command('enable-oled')
        if response:
            self.update_status("OLED display active")
    
    def on_refresh_full(self):
        """Perform full E-Ink refresh"""
        self.log_message("Performing full E-Ink refresh (clearing ghosting)...")
        self.update_status("Refreshing E-Ink display...")
        response = self.execute_helper_command('refresh-eink')
        if response:
            self.update_status("E-Ink refresh complete")
    
    def on_refresh_quick(self):
        """Perform quick E-Ink refresh"""
        self.log_message("Performing quick E-Ink refresh...")
        self.update_status("Refreshing E-Ink display...")
        response = self.execute_helper_command('refresh-eink-quick')
        if response:
            self.update_status("E-Ink refresh complete")
    
    def on_frontlight_toggled(self):
        """Handle frontlight power toggle"""
        enabled = self.frontlight_var.get()
        command = 'enable-frontlight' if enabled else 'disable-frontlight'
        
        self.log_message(f"{'Enabling' if enabled else 'Disabling'} frontlight...")
        response = self.execute_helper_command(command)
        
        if response:
            self.update_status(f"Frontlight {'enabled' if enabled else 'disabled'}")
        else:
            # Revert checkbox on failure
            self.frontlight_var.set(not enabled)
    
    def on_brightness_changed(self, value):
        """Handle brightness slider change"""
        level = int(float(value))
        self.brightness_label.config(text=str(level))
        
        # Debounce: use timer to avoid too many commands while dragging
        if self.brightness_timer:
            self.root.after_cancel(self.brightness_timer)
        
        self.brightness_timer = self.root.after(300, self._set_brightness, level)
    
    def _set_brightness(self, level):
        """Actually set the brightness after debounce"""
        self.log_message(f"Setting brightness to level {level}...")
        response = self.execute_helper_command('set-brightness', level=level)
        
        if response:
            self.update_status(f"Brightness set to {level}")
        
        self.brightness_timer = None
    
    def on_eink_touch_toggled(self):
        """Handle E-Ink touch toggle (Goodix touchscreen)"""
        enabled = self.eink_touch_var.get()
        
        # Get touch devices
        devices = self.wacom_mgr.get_touch_devices()
        eink_devices = devices.get('eink', [])
        
        if not eink_devices:
            self.log_message("No E-Ink touch devices found", level='error')
            self.show_info_dialog(
                "No E-Ink touch devices detected.\n\n"
                "Expected: Goodix touchscreen\n"
                "This may be normal if the device is already disabled."
            )
            return
        
        # Toggle E-Ink touch devices
        self.log_message(f"{'Enabling' if enabled else 'Disabling'} E-Ink touch on {len(eink_devices)} device(s)...")
        
        success_count = 0
        for device in eink_devices:
            if self.wacom_mgr.set_touch_enabled(device['id'], enabled):
                success_count += 1
                self.log_message(f"  ✓ {'Enabled' if enabled else 'Disabled'}: {device['name']}")
            else:
                self.log_message(f"  ✗ Failed: {device['name']}", level='error')
        
        if success_count > 0:
            self.update_status(f"E-Ink touch {'enabled' if enabled else 'disabled'} on {success_count} device(s)")
        else:
            self.log_message("Failed to toggle E-Ink touch devices", level='error')
    
    def on_oled_touch_toggled(self):
        """Handle OLED touch toggle (Wacom pen/touch)"""
        enabled = self.oled_touch_var.get()
        
        # Get touch devices
        devices = self.wacom_mgr.get_touch_devices()
        oled_devices = devices.get('oled', [])
        
        if not oled_devices:
            self.log_message("No OLED touch devices found", level='error')
            self.show_info_dialog(
                "No OLED touch devices detected.\n\n"
                "Expected: Wacom pen/touch devices\n"
                "This may be normal if the device is already disabled."
            )
            return
        
        # Toggle OLED touch devices
        self.log_message(f"{'Enabling' if enabled else 'Disabling'} OLED touch on {len(oled_devices)} device(s)...")
        
        success_count = 0
        for device in oled_devices:
            if self.wacom_mgr.set_touch_enabled(device['id'], enabled):
                success_count += 1
                self.log_message(f"  ✓ {'Enabled' if enabled else 'Disabled'}: {device['name']}")
            else:
                self.log_message(f"  ✗ Failed: {device['name']}", level='error')
        
        if success_count > 0:
            self.update_status(f"OLED touch {'enabled' if enabled else 'disabled'} on {success_count} device(s)")
        else:
            self.log_message("Failed to toggle OLED touch devices", level='error')
    
    def on_oled_toggled(self):
        """Handle OLED display enable/disable"""
        enabled = self.oled_enabled_var.get()
        
        if enabled:
            self.log_message(f"Enabling OLED display ({self.DISPLAY_OLED})...")
            if self.display_mgr.enable_display(self.DISPLAY_OLED):
                self.update_status("OLED display enabled")
                self.log_message(f"✓ OLED display ({self.DISPLAY_OLED}) enabled")
            else:
                self.log_message(f"✗ Failed to enable OLED display", level='error')
                self.oled_enabled_var.set(False)  # Revert on failure
        else:
            self.log_message(f"Disabling OLED display ({self.DISPLAY_OLED})...")
            if self.display_mgr.disable_display(self.DISPLAY_OLED):
                self.update_status("OLED display disabled")
                self.log_message(f"✓ OLED display ({self.DISPLAY_OLED}) disabled")
            else:
                self.log_message(f"✗ Failed to disable OLED display", level='error')
                self.oled_enabled_var.set(True)  # Revert on failure
    
    def on_eink_display_toggled(self):
        """Handle E-Ink display enable/disable"""
        enabled = self.eink_display_var.get()
        
        if enabled:
            self.log_message(f"Enabling E-Ink display ({self.DISPLAY_EINK})...")
            if self.display_mgr.enable_display(self.DISPLAY_EINK):
                self.update_status("E-Ink display enabled")
                self.log_message(f"✓ E-Ink display ({self.DISPLAY_EINK}) enabled")
            else:
                self.log_message(f"✗ Failed to enable E-Ink display", level='error')
                self.eink_display_var.set(False)  # Revert on failure
        else:
            self.log_message(f"Disabling E-Ink display ({self.DISPLAY_EINK})...")
            if self.display_mgr.disable_display(self.DISPLAY_EINK):
                self.update_status("E-Ink display disabled")
                self.log_message(f"✓ E-Ink display ({self.DISPLAY_EINK}) disabled")
            else:
                self.log_message(f"✗ Failed to disable E-Ink display", level='error')
                self.eink_display_var.set(True)  # Revert on failure
    
    def on_closing(self):
        """Handle window close"""
        self.logger.info("Application closing")
        
        # Stop keepalive
        if self.keepalive_after_id:
            self.root.after_cancel(self.keepalive_after_id)
        
        # Disconnect from helper (sends shutdown command)
        if self.helper.is_connected():
            self.helper.disconnect()
        
        # Terminate helper process if we launched it
        if self.helper_process:
            try:
                self.helper_process.terminate()
                self.helper_process.wait(timeout=2)
            except:
                pass
        
        self.root.destroy()


def main():
    """Entry point"""
    HELPER_SCRIPT = '/usr/local/bin/HelperDaemon.py'  # Or use sys.argv[0] relative path

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger('tinta4plus-gui')

    # Check if helper script exists
    if not os.path.exists(HELPER_SCRIPT):
        # Try relative path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_helper = os.path.join(script_dir, 'HelperDaemon.py')
        if os.path.exists(alt_helper):
            HELPER_SCRIPT = alt_helper
            logger.info(f"Using helper at: {HELPER_SCRIPT}")
    
    root = tk.Tk()
    app = EInkControlGUI(root, HELPER_SCRIPT, logger)
    
    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        app.on_closing()


if __name__ == '__main__':
    main()
