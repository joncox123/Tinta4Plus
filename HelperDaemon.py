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
ThinkBook Plus Gen 4 IRU E-Ink Control Helper
Privileged daemon for hardware control via Unix socket

Requires: sudo/pkexec to run
Dependencies: pyusb, portio (or python-periphery)
"""

import os
import sys
import json
import socket
import struct
import signal
import threading
import logging

from WatchdogTimer import WatchdogTimer
from ECController import ECController
from EInkUSBController import EInkUSBController 

# Configuration
SOCKET_PATH = '/tmp/tinta4plus.sock'
PID_FILE = '/tmp/tinta4plus.pid'
WATCHDOG_TIMEOUT = 20.0  # seconds
LOG_LEVEL = logging.INFO


class HelperDaemon:
    """Main helper daemon with socket server and hardware controllers"""
    
    def __init__(self, logger):
        self.logger = logger
        self.running = False
        self.socket_path = SOCKET_PATH
        self.pid_file = PID_FILE
        self.server_socket = None
        
        # Hardware controllers
        self.eink = None
        self.ec = None
        
        # Watchdog
        self.watchdog = WatchdogTimer(WATCHDOG_TIMEOUT, self.shutdown, self.logger)
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        self.logger.info(f"Received signal {signum}, shutting down")
        self.shutdown()
    
    def _create_pid_file(self):
        """Create PID file"""
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
            self.logger.info(f"Created PID file: {self.pid_file}")
        except Exception as e:
            self.logger.error(f"Failed to create PID file: {e}")
    
    def _remove_pid_file(self):
        """Remove PID file"""
        try:
            if os.path.exists(self.pid_file):
                os.remove(self.pid_file)
                self.logger.info("Removed PID file")
        except Exception as e:
            self.logger.warning(f"Failed to remove PID file: {e}")
    
    def _create_socket(self):
        """Create Unix domain socket"""
        # Remove old socket if exists
        if os.path.exists(self.socket_path):
            os.remove(self.socket_path)
        
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(1)
        
        # Set permissions (readable/writable by all for simplicity)
        os.chmod(self.socket_path, 0o666)
        
        self.logger.info(f"Listening on socket: {self.socket_path}")
    
    def _remove_socket(self):
        """Remove socket file"""
        try:
            if self.server_socket:
                self.server_socket.close()
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
            self.logger.info("Removed socket")
        except Exception as e:
            self.logger.warning(f"Failed to remove socket: {e}")
    
    def initialize_hardware(self):
        """Initialize hardware controllers"""
        try:
            # Initialize EC controller
            self.logger.info("Initializing EC controller")
            self.ec = ECController(self.logger)
            
            # Initialize E-Ink USB controller
            self.logger.info("Initializing E-Ink USB controller")
            self.eink = EInkUSBController(self.logger)
            self.eink.connect()
            
            self.logger.info("Hardware initialization complete")
            return True
            
        except Exception as e:
            self.logger.error(f"Hardware initialization failed: {e}")
            return False
    
    def cleanup_hardware(self):
        """Cleanup hardware connections"""
        if self.eink:
            self.eink.disconnect()
        self.logger.info("Hardware cleanup complete")
    
    def handle_command(self, command_data):
        """Process a command and return response"""
        try:
            cmd = command_data.get('command')
            params = command_data.get('params', {})
            
            self.logger.debug(f"Handling command: {cmd}")
            
            # Reset watchdog on any command
            self.watchdog.reset()
            
            response = {'success': False, 'error': None}
            
            if cmd == 'keepalive':
                # Simple keepalive/ping command
                response['success'] = True
                response['message'] = 'pong'
            
            elif cmd == 'enable-eink':
                self.eink.switch_to_eink()
                response['success'] = True
                response['message'] = 'Switched to E-Ink display'
            
            elif cmd == 'enable-oled':
                self.eink.switch_to_oled()
                response['success'] = True
                response['message'] = 'Switched to OLED display'
            
            elif cmd == 'refresh-eink':
                self.eink.refresh_full()
                response['success'] = True
                response['message'] = 'E-Ink full refresh completed'
            
            elif cmd == 'refresh-eink-quick':
                self.eink.refresh_quick()
                response['success'] = True
                response['message'] = 'E-Ink quick refresh completed'
            
            elif cmd == 'enable-frontlight':
                success, readback = self.ec.enable_frontlight()
                response['success'] = success
                response['readback'] = f"0x{readback:02x}"
                response['message'] = 'Frontlight enabled' if success else 'Frontlight enable failed (readback mismatch)'
            
            elif cmd == 'disable-frontlight':
                success, readback = self.ec.disable_frontlight()
                response['success'] = success
                response['readback'] = f"0x{readback:02x}"
                response['message'] = 'Frontlight disabled' if success else 'Frontlight disable failed (readback mismatch)'
            
            elif cmd == 'set-brightness':
                level = params.get('level')
                if level is None:
                    raise ValueError("Missing 'level' parameter")
                
                success, readback = self.ec.set_brightness(int(level))
                response['success'] = success
                response['readback'] = f"0x{readback:02x}"
                response['level'] = level
                response['message'] = f'Brightness set to {level}' if success else f'Brightness set failed (readback mismatch)'
            
            elif cmd == 'shutdown':
                response['success'] = True
                response['message'] = 'Shutting down'
                # Shutdown after sending response
                threading.Timer(0.1, self.shutdown).start()
            
            else:
                raise ValueError(f"Unknown command: {cmd}")
            
            return response
            
        except Exception as e:
            self.logger.error(f"Command error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def handle_client(self, client_socket):
        """Handle a client connection"""
        try:
            while self.running:
                # Receive data (with 4-byte length prefix)
                length_data = client_socket.recv(4)
                if not length_data:
                    break
                
                msg_length = struct.unpack('!I', length_data)[0]
                
                # Receive the message
                data = b''
                while len(data) < msg_length:
                    chunk = client_socket.recv(msg_length - len(data))
                    if not chunk:
                        break
                    data += chunk
                
                if len(data) != msg_length:
                    break
                
                # Parse JSON command
                command_data = json.loads(data.decode('utf-8'))
                
                # Process command
                response = self.handle_command(command_data)
                
                # Send response
                response_json = json.dumps(response).encode('utf-8')
                response_length = struct.pack('!I', len(response_json))
                client_socket.sendall(response_length + response_json)
                
        except Exception as e:
            self.logger.error(f"Client handler error: {e}")
        finally:
            client_socket.close()
    
    def run(self):
        """Main server loop"""
        try:
            # Check if already running
            if os.path.exists(self.pid_file):
                self.logger.warning(f"PID file exists: {self.pid_file}")
                try:
                    with open(self.pid_file, 'r') as f:
                        old_pid = int(f.read().strip())
                    # Check if process is still running
                    os.kill(old_pid, 0)
                    self.logger.error(f"Helper already running (PID {old_pid})")
                    return 1
                except (OSError, ValueError):
                    self.logger.info("Stale PID file, removing")
                    os.remove(self.pid_file)
            
            # Create PID file
            self._create_pid_file()
            
            # Initialize hardware
            if not self.initialize_hardware():
                self.logger.error("Failed to initialize hardware")
                return 1
            
            # Create socket
            self._create_socket()
            
            self.running = True
            self.logger.info("Helper daemon started, waiting for connections")
            
            # Accept connections
            while self.running:
                try:
                    # Set timeout so we can check self.running periodically
                    self.server_socket.settimeout(1.0)
                    try:
                        client_socket, _ = self.server_socket.accept()
                        self.logger.info("Client connected")
                        
                        # Handle in a thread (though we expect only one client)
                        client_thread = threading.Thread(
                            target=self.handle_client,
                            args=(client_socket,)
                        )
                        client_thread.daemon = True
                        client_thread.start()
                        
                    except socket.timeout:
                        continue
                        
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Accept error: {e}")
                        break
            
            return 0
            
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return 1
        
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Shutdown the daemon"""
        if not self.running:
            return
        
        self.logger.info("Shutting down...")
        self.running = False
        
        # Cancel watchdog
        self.watchdog.cancel()
        
        # Cleanup
        self.cleanup_hardware()
        self._remove_socket()
        self._remove_pid_file()
        
        self.logger.info("Shutdown complete")


def main():
    """Entry point"""
    # Check if running as root
    if os.geteuid() != 0:
        print("ERROR: This helper must be run as root (use pkexec or sudo)", file=sys.stderr)
        return 1
    
    # Setup logging
    logging.basicConfig(
        level=LOG_LEVEL,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stderr)]
    )
    logger = logging.getLogger('tinta4plus-helper')
    
    logger.info("ThinkBook E-Ink Helper starting")
    logger.info(f"Watchdog timeout: {WATCHDOG_TIMEOUT}s")
    
    daemon = HelperDaemon(logger)
    return daemon.run()


if __name__ == '__main__':
    sys.exit(main())
