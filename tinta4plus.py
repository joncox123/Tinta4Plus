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
import sys
import os
import time
import threading
import logging
import webbrowser
from datetime import datetime

from HelperClient import HelperClient
from DisplayManager import DisplayManager
from WacomManager import WacomManager


class EInkControlGUI:
    # Version
    VERSION = "0.1.0 alpha"

    # Configuration
    SOCKET_PATH = '/tmp/tinta4plus.sock'
    KEEPALIVE_INTERVAL = 2.4  # seconds (send keepalive every 2.4s, watchdog is 20s)
    SOCKET_TIMEOUT = 10.0  # seconds

    # Display names (ThinkBook Plus Gen 4 has eDP-1=OLED, eDP-2=E-Ink)
    DISPLAY_OLED = "eDP-1"
    DISPLAY_EINK = "eDP-2"

    # E-Ink privacy image (displayed when disabling E-Ink to clear private data)
    # NOTE: must install feh and imv for this to work!
    EINK_DISABLED_IMAGE = "eink-disable.jpg"

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

        # Image viewer process for E-Ink privacy screen
        self.eink_image_process = None

        # Display scaling (1.75x default for comfortable viewing on high-DPI displays)
        self.display_scale = 1.75

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

        # Store frontlight control widgets for enabling/disabling
        self.frontlight_widgets = []
        
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
        status_label.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        row += 1

        # Secure Boot status indicator
        self.secureboot_frame = tk.Frame(main_frame, bg='gray', relief=tk.RIDGE, bd=2)
        self.secureboot_frame.grid(row=row, column=0, sticky=tk.W, pady=(0, 10))

        self.secureboot_label = tk.Label(self.secureboot_frame, text="Secure Boot: Unknown",
                                         bg='gray', fg='white', font=('TkDefaultFont', 9, 'bold'),
                                         padx=10, pady=3)
        self.secureboot_label.pack()
        row += 1
        
        # === Display Control Section ===
        display_frame = ttk.LabelFrame(main_frame, text="Display Control", padding="10")
        display_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=5)
        display_frame.columnconfigure(0, weight=1)
        display_frame.columnconfigure(1, weight=1)
        row += 1
        
        # E-Ink toggle control
        eink_toggle_frame = ttk.Frame(display_frame)
        eink_toggle_frame.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

        self.eink_enabled_var = tk.BooleanVar(value=False)
        self.eink_toggle_btn = tk.Button(eink_toggle_frame, text="eInk Disabled",
                                         bg="yellow", fg="black",
                                         font=('TkDefaultFont', 10, 'bold'),
                                         relief=tk.RAISED, bd=3,
                                         command=self.on_eink_toggled,
                                         activebackground="#b8aa00",  # Darker yellow
                                         activeforeground="black",
                                         padx=20, pady=10)
        self.eink_toggle_btn.pack(expand=True, fill=tk.X)

        # Bind hover effects for eInk toggle button
        self.eink_toggle_btn.bind("<Enter>", lambda e: self._on_eink_btn_hover(e, True))
        self.eink_toggle_btn.bind("<Leave>", lambda e: self._on_eink_btn_hover(e, False))

        # Refresh button
        self.btn_refresh = ttk.Button(display_frame, text="Full Refresh (Clear Ghost)",
                                      command=self.on_refresh_full)
        self.btn_refresh.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky=(tk.W, tk.E))

        # Display scale slider
        scale_label = ttk.Label(display_frame, text="Display Scale:")
        scale_label.grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)

        scale_container = ttk.Frame(display_frame)
        scale_container.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        scale_container.columnconfigure(0, weight=1)

        self.scale_var = tk.DoubleVar(value=1.75)
        self.scale_slider = ttk.Scale(scale_container, from_=1.0, to=2.0,
                                     orient=tk.HORIZONTAL,
                                     variable=self.scale_var,
                                     command=self.on_scale_changed)
        self.scale_slider.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.scale_label = ttk.Label(scale_container, text="1.75")
        self.scale_label.grid(row=0, column=1, padx=(5, 0))

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
        self.frontlight_widgets.append(frontlight_check)

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
        self.frontlight_widgets.append(self.brightness_scale)

        self.brightness_label = ttk.Label(brightness_container, text="4")
        self.brightness_label.grid(row=0, column=1, padx=(5, 0))

        # Warning label for Secure Boot (initially hidden)
        self.secure_boot_warning = ttk.Label(frontlight_frame,
                                             text="⚠ Secure Boot is enabled. Frontlight controls disabled.\nPlease disable Secure Boot in BIOS (Press ENTER during boot).",
                                             foreground='red', font=('TkDefaultFont', 9, 'bold'))
        # Don't grid it yet - will be shown if needed

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

        # Version and Buy Me A Coffee button row
        version_coffee_frame = ttk.Frame(main_frame)
        version_coffee_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)
        version_coffee_frame.columnconfigure(0, weight=1)  # Allow space to expand between elements

        # Version label (left side)
        version_label = ttk.Label(version_coffee_frame, text=f"Version {self.VERSION}",
                                 font=('TkDefaultFont', 8))
        version_label.grid(row=0, column=0, sticky=tk.W)

        # Buy Me A Coffee button (right side)
        self.coffee_btn = tk.Button(version_coffee_frame, text="Buy Me A Coffee",
                                   bg="yellow", fg="black",
                                   font=('TkDefaultFont', 8),
                                   relief=tk.RAISED, bd=2,
                                   command=self.on_buy_coffee,
                                   activebackground="#b8aa00",  # Darker yellow
                                   activeforeground="black",
                                   padx=8, pady=4)
        self.coffee_btn.grid(row=0, column=1, sticky=tk.E)

        # Bind hover effects for coffee button
        self.coffee_btn.bind("<Enter>", lambda e: self.coffee_btn.config(bg="#b8aa00"))
        self.coffee_btn.bind("<Leave>", lambda e: self.coffee_btn.config(bg="yellow"))

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
                if self.helper.connect(self.SOCKET_PATH, timeout=self.SOCKET_TIMEOUT):
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
                    if self.helper.connect(self.SOCKET_PATH, timeout=self.SOCKET_TIMEOUT):
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

        # Check EC status
        self.root.after(500, self.check_ec_status)
    
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
                if self.helper.connect(self.SOCKET_PATH, timeout=self.SOCKET_TIMEOUT):
                    self.log_message("✓ Reconnected to existing helper")
                    self.update_status("Reconnected to helper daemon")
                    self.start_keepalive()
                    # Re-check EC status and sync frontlight state after reconnect
                    self.root.after(500, self.check_ec_status)
                    return
            except:
                pass
        
        # Need to launch new helper
        self.log_message("Launching new helper daemon (password may be required)...")
        self.update_status("Launching helper daemon...")
        threading.Thread(target=self._launch_helper_thread, daemon=True).start()
    
    def check_ec_status(self):
        """Check EC access status and disable frontlight controls if Secure Boot enabled"""
        try:
            response = self.helper.send_command('get-ec-status')

            if response and response.get('success'):
                ec_status = response.get('ec_status', {})

                # Update Secure Boot status indicator
                if ec_status.get('secure_boot_enabled'):
                    self.secureboot_label.config(text="Secure Boot: ON", bg='red')
                    self.secureboot_frame.config(bg='red')
                else:
                    self.secureboot_label.config(text="Secure Boot: OFF", bg='green')
                    self.secureboot_frame.config(bg='green')

                if ec_status.get('secure_boot_enabled') or not ec_status.get('available'):
                    # Secure Boot enabled or EC not available - disable frontlight controls
                    error_msg = ec_status.get('error_message', 'EC access not available')
                    self.log_message(f"⚠ {error_msg}", level='error')

                    # Show warning label
                    self.secure_boot_warning.grid(row=2, column=0, columnspan=2,
                                                 sticky=(tk.W, tk.E), padx=5, pady=10)

                    # Disable all frontlight controls
                    for widget in self.frontlight_widgets:
                        widget.config(state='disabled')

                    # Show dialog
                    if ec_status.get('secure_boot_enabled'):
                        messagebox.showwarning(
                            "Secure Boot Enabled",
                            "Secure Boot is currently enabled in your BIOS.\n\n"
                            "Frontlight controls require direct hardware access which is blocked by Secure Boot.\n\n"
                            "To enable frontlight controls:\n"
                            "1. Reboot your computer\n"
                            "2. Press ENTER (or F2) during boot to enter BIOS\n"
                            "3. Navigate to Security → Secure Boot\n"
                            "4. Set Secure Boot to 'Disabled'\n"
                            "5. Save and exit (F10)\n\n"
                            "Note: E-Ink display controls will continue to work normally."
                        )
                    else:
                        self.log_message(f"EC access not available: {error_msg}", level='error')
                else:
                    self.log_message("EC access verified - frontlight controls enabled")
                    # Sync GUI with actual EC state
                    self.sync_frontlight_state()

        except Exception as e:
            self.logger.error(f"Failed to check EC status: {e}")
            self.log_message(f"Warning: Could not verify EC status: {e}", level='error')

    def sync_frontlight_state(self):
        """Query EC and update GUI to match actual frontlight state"""
        try:
            response = self.helper.send_command('get-frontlight-state')

            if response and response.get('success'):
                enabled = response.get('frontlight_enabled')
                brightness = response.get('brightness_level')

                if enabled is not None:
                    # Temporarily disable the callback to avoid triggering commands
                    old_callback = self.frontlight_var.trace_info()
                    self.frontlight_var.set(enabled)
                    self.log_message(f"Synced frontlight power: {'ON' if enabled else 'OFF'}")

                if brightness is not None:
                    self.brightness_var.set(brightness)
                    self.brightness_label.config(text=str(brightness))
                    self.log_message(f"Synced brightness level: {brightness}")

        except Exception as e:
            self.logger.warning(f"Failed to sync frontlight state: {e}")
            self.log_message(f"Warning: Could not sync frontlight state from EC", level='error')


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
    
    def on_eink_toggled(self):
        """Handle E-Ink display toggle with automatic eDP switching"""
        enabled = self.eink_enabled_var.get()
        # Toggle the state
        enabled = not enabled

        if enabled:
            # Enabling E-Ink
            self.log_message("Enabling E-Ink display...")

            # Step 1: Enable E-Ink on eDP-2 first
            self.log_message(f"Enabling E-Ink display on {self.DISPLAY_EINK} with {self.display_scale}x scale...")
            if self.display_mgr.enable_display(self.DISPLAY_EINK, scale=self.display_scale):
                self.log_message(f"✓ E-Ink display ({self.DISPLAY_EINK}) enabled with {self.display_scale}x scale")
            else:
                self.log_message(f"⚠ Failed to enable E-Ink display on {self.DISPLAY_EINK}", level='error')

            # Small delay to ensure display is fully enabled
            time.sleep(1.0)

            # Step 2: Enable E-Ink via USB TCON controller
            response = self.execute_helper_command('enable-eink')

            if response:
                self.eink_enabled_var.set(True)
                self.eink_toggle_btn.config(text="eInk Enabled", bg="green", fg="white")
                self.update_status("E-Ink display enabled")

                # Small delay before disabling OLED
                time.sleep(0.5)

                # Step 4: Disable OLED display on eDP-1 as the last step
                self.log_message(f"Disabling OLED display on {self.DISPLAY_OLED}...")
                if self.display_mgr.disable_display(self.DISPLAY_OLED):
                    self.log_message(f"✓ OLED display ({self.DISPLAY_OLED}) disabled")
                else:
                    self.log_message(f"⚠ Failed to disable OLED display on {self.DISPLAY_OLED}", level='error')
        else:
            # Disabling E-Ink
            self.log_message("Preparing to disable E-Ink display...")

            # Step 3: Display privacy image on E-Ink screen
            image_path = self.EINK_DISABLED_IMAGE
            if not os.path.exists(image_path):
                # Try in script directory
                script_dir = os.path.dirname(os.path.abspath(__file__))
                image_path = os.path.join(script_dir, self.EINK_DISABLED_IMAGE)

            if os.path.exists(image_path):
                self.log_message(f"Displaying privacy image on {self.DISPLAY_EINK}...")
                self.eink_image_process = self.display_mgr.display_fullscreen_image(
                    self.DISPLAY_EINK,
                    image_path
                )

                if self.eink_image_process:
                    # Wait for image to fully render on E-Ink
                    self.log_message("Waiting for image to render...")
                    time.sleep(0.5)  # Give E-Ink time to display the image
                else:
                    self.log_message("Warning: Could not display privacy image", level='error')
            else:
                self.log_message(f"Warning: Privacy image not found: {self.EINK_DISABLED_IMAGE}", level='error')

            # Step 4: Disable E-Ink via USB controller
            self.log_message("Disabling E-Ink display via USB controller...")
            response = self.execute_helper_command('disable-eink')

            if response:
                self.eink_enabled_var.set(False)
                self.eink_toggle_btn.config(text="eInk Disabled", bg="yellow", fg="black")
                self.update_status("E-Ink display disabled")

                time.sleep(2.0)  # Give E-Ink time to display the image

                # Kill the image viewer process (image is now persisted on E-Ink)
                if self.eink_image_process:
                    try:
                        self.eink_image_process.terminate()
                        self.eink_image_process.wait(timeout=2)
                        self.log_message("Closed image viewer (image persisted on E-Ink)")
                    except:
                        try:
                            self.eink_image_process.kill()
                        except:
                            pass
                    self.eink_image_process = None

                # Step 1: Enable OLED display on eDP-1 first
                self.log_message(f"Enabling OLED display on {self.DISPLAY_OLED} with {self.display_scale}x scale...")
                if self.display_mgr.enable_display(self.DISPLAY_OLED, scale=self.display_scale):
                    self.log_message(f"✓ OLED display ({self.DISPLAY_OLED}) enabled with {self.display_scale}x scale")
                else:
                    self.log_message(f"⚠ Failed to enable OLED display on {self.DISPLAY_OLED}", level='error')

                # Small delay to ensure OLED is fully enabled
                time.sleep(1.0)

                # Step 5: Disable E-Ink on eDP-2 as the last step
                self.log_message(f"Disabling E-Ink display on {self.DISPLAY_EINK}...")
                if self.display_mgr.disable_display(self.DISPLAY_EINK):
                    self.log_message(f"✓ E-Ink display ({self.DISPLAY_EINK}) disabled")
                else:
                    self.log_message(f"⚠ Failed to disable E-Ink display on {self.DISPLAY_EINK}", level='error')
            else:
                # Failed to disable - kill image viewer
                if self.eink_image_process:
                    try:
                        self.eink_image_process.terminate()
                        self.eink_image_process.wait(timeout=2)
                    except:
                        try:
                            self.eink_image_process.kill()
                        except:
                            pass
                    self.eink_image_process = None
    
    def on_refresh_full(self):
        """Perform full E-Ink refresh"""
        self.log_message("Performing full E-Ink refresh (clearing ghosting)...")
        self.update_status("Refreshing E-Ink display...")
        response = self.execute_helper_command('refresh-eink')
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

    def on_scale_changed(self, value):
        """Handle display scale slider change"""
        # Round to nearest 0.05
        scale = round(float(value) / 0.05) * 0.05
        self.scale_var.set(scale)
        self.display_scale = scale
        self.scale_label.config(text=f"{scale:.2f}")
        self.log_message(f"Display scale set to {scale:.2f}x (will apply on next display switch)")

    def _on_eink_btn_hover(self, event, entering):
        """Handle hover effects for eInk toggle button"""
        if entering:
            # Mouse entering - darken the current color
            if self.eink_enabled_var.get():
                # Currently green (enabled) - use darker green
                self.eink_toggle_btn.config(bg="#006400")  # Dark green
            else:
                # Currently yellow (disabled) - use darker yellow
                self.eink_toggle_btn.config(bg="#b8aa00")  # Darker yellow
        else:
            # Mouse leaving - restore original color
            if self.eink_enabled_var.get():
                self.eink_toggle_btn.config(bg="green")
            else:
                self.eink_toggle_btn.config(bg="yellow")

    def on_buy_coffee(self):
        """Handle Buy Me A Coffee button click"""
        try:
            webbrowser.open('https://buymeacoffee.com/joncox')
            self.log_message("Opening Buy Me A Coffee page...")
        except Exception as e:
            self.logger.error(f"Failed to open browser: {e}")
            self.log_message(f"Failed to open browser: {e}", level='error')

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


def show_disclaimer_dialog(parent=None):
    """Show disclaimer dialog on first launch. Returns True if user agrees, False otherwise."""
    # Load EULA text from external file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    eula_file = os.path.join(script_dir, "README_EULA_INSTRUCTIONS_WARNINGS.txt")

    try:
        with open(eula_file, 'r') as f:
            DISCLAIMER_TEXT = f.read()
    except FileNotFoundError:
        # Show error message and terminate
        if parent:
            messagebox.showerror("EULA Not Found",
                               "EULA file not found:\n" + eula_file +
                               "\n\nThe application will now exit.")
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("EULA Not Found",
                               "EULA file not found:\n" + eula_file +
                               "\n\nThe application will now exit.")
            root.destroy()
        sys.exit(1)
    except Exception as e:
        # Show error message for other read errors and terminate
        error_msg = f"Failed to read EULA file:\n{eula_file}\n\nError: {str(e)}\n\nThe application will now exit."
        if parent:
            messagebox.showerror("EULA Not Found", error_msg)
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("EULA Not Found", error_msg)
            root.destroy()
        sys.exit(1)

    # Check if agreement file exists
    config_dir = os.path.expanduser("~/.config/Tinta4Plus")
    agree_file = os.path.join(config_dir, "agree")

    if os.path.exists(agree_file):
        return True  # User has already agreed

    # Create a custom EULA dialog
    dialog = tk.Toplevel(parent)
    dialog.title("End User License Agreement")
    dialog.geometry("900x750")
    dialog.resizable(False, False)

    # Disable the close button (X) - user must click Agree or Disagree
    dialog.protocol("WM_DELETE_WINDOW", lambda: None)

    # Make it modal
    dialog.grab_set()
    dialog.focus_set()

    # Center the dialog on screen
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth() // 2) - (650 // 2)
    y = (dialog.winfo_screenheight() // 2) - (600 // 2)
    dialog.geometry(f'900x750+{x}+{y}')

    # Result variable
    result = {'agreed': False}

    def on_agree():
        result['agreed'] = True
        dialog.destroy()

    def on_disagree():
        result['agreed'] = False
        dialog.destroy()

    # Top frame with warning icon and title
    top_frame = tk.Frame(dialog, bg='white', pady=10)
    top_frame.pack(fill=tk.X)

    # Warning icon (using text emoji)
    icon_label = tk.Label(top_frame, text="⚠", font=('TkDefaultFont', 48),
                         bg='white', fg='orange')
    icon_label.pack(side=tk.LEFT, padx=20)

    # Title
    title_label = tk.Label(top_frame, text="End User License Agreement\n\nPlease read carefully",
                          font=('TkDefaultFont', 12, 'bold'), bg='white', justify=tk.LEFT)
    title_label.pack(side=tk.LEFT, padx=10)

    # Separator
    separator = ttk.Separator(dialog, orient=tk.HORIZONTAL)
    separator.pack(fill=tk.X, padx=5, pady=5)

    # Button frame (pack this BEFORE the text so it stays at bottom)
    button_frame = tk.Frame(dialog)
    button_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=10)

    # Bottom separator (pack before text frame)
    separator2 = ttk.Separator(dialog, orient=tk.HORIZONTAL)
    separator2.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=5)

    # Scrolled text widget for EULA (pack last so it fills remaining space)
    text_frame = tk.Frame(dialog)
    text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Create ScrolledText with vertical scrollbar
    eula_text = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD,
                                         font=('TkDefaultFont', 11),
                                         relief=tk.SUNKEN, bd=2,
                                         width=1, height=1)  # Dummy size, will expand
    eula_text.pack(fill=tk.BOTH, expand=True)
    eula_text.insert('1.0', DISCLAIMER_TEXT)
    eula_text.config(state=tk.DISABLED)  # Make read-only

    # Agree button (left side, initially disabled)
    agree_btn = ttk.Button(button_frame, text="Agree",
                          command=on_agree,
                          state='disabled')
    agree_btn.pack(side=tk.LEFT, padx=5)

    # Disagree button (right side, default)
    disagree_btn = ttk.Button(button_frame, text="Disagree",
                             command=on_disagree)
    disagree_btn.pack(side=tk.RIGHT, padx=5)

    # Make Disagree the default button (focused)
    disagree_btn.focus_set()

    # Function to check if user has scrolled to the bottom
    def on_scroll(*args):
        # Get the current position of the scrollbar
        # yview() returns (top, bottom) as fractions of the total content
        pos = eula_text.yview()
        # If bottom is at or near 1.0 (end of document), enable Agree button
        if pos[1] >= 0.99:  # Allow small margin for rounding
            agree_btn.config(state='normal')

    # Bind scroll event to check position
    eula_text.bind('<Configure>', on_scroll)
    eula_text.bind('<MouseWheel>', on_scroll)
    eula_text.bind('<Button-4>', on_scroll)  # Linux scroll up
    eula_text.bind('<Button-5>', on_scroll)  # Linux scroll down
    eula_text.bind('<Key>', on_scroll)  # Arrow keys, Page Down, etc.

    # Also monitor the scrollbar directly - get the vbar widget
    vbar = eula_text.vbar  # ScrolledText has a vbar attribute for the scrollbar
    if vbar:
        original_set = vbar.set
        def scrollbar_set(*args):
            original_set(*args)
            on_scroll()
        vbar.set = scrollbar_set

    # Handle Enter key on buttons
    disagree_btn.bind('<Return>', lambda e: on_disagree())
    agree_btn.bind('<Return>', lambda e: on_agree())

    # Wait for dialog to close
    dialog.wait_window()

    if result['agreed']:
        # User agreed - create agreement file
        try:
            os.makedirs(config_dir, exist_ok=True)
            with open(agree_file, 'w') as f:
                f.write('')  # Empty file
            return True
        except Exception as e:
            print(f"Error creating agreement file: {e}")
            return False
    else:
        # User declined
        return False


def main():
    """Entry point"""
    HELPER_SCRIPT = '/usr/local/bin/HelperDaemon.py'  # Or use sys.argv[0] relative path

    # Setup logging
    log_handlers = [
        logging.StreamHandler(),  # Console output
        logging.FileHandler('/tmp/tinta4plus.log')  # File output
    ]

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=log_handlers
    )
    logger = logging.getLogger('tinta4plus-gui')

    # Setup exception hook to log uncaught exceptions
    def handle_exception(exc_type, exc_value, exc_traceback):
        """Log uncaught exceptions"""
        if issubclass(exc_type, KeyboardInterrupt):
            # Allow keyboard interrupt to exit normally
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

    # Check if helper script exists
    if not os.path.exists(HELPER_SCRIPT):
        # Try relative path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_helper = os.path.join(script_dir, 'HelperDaemon.py')
        if os.path.exists(alt_helper):
            HELPER_SCRIPT = alt_helper
            logger.info(f"Using helper at: {HELPER_SCRIPT}")
    
    root = tk.Tk()
    root.withdraw()  # Hide the main window initially

    # Check disclaimer agreement BEFORE showing the main window
    if not show_disclaimer_dialog(root):
        print("User declined disclaimer. Exiting.")
        root.destroy()
        sys.exit(0)

    # User agreed, show the main window
    root.deiconify()
    app = EInkControlGUI(root, HELPER_SCRIPT, logger)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        app.on_closing()


if __name__ == '__main__':
    main()
