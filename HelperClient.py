"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

WARNING: This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects
that result in data loss, corruption, hardware damage or other issues. Use at your own risk.
It may temporarily or permanently render your hardware inoperable.
It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop.
The author is not responsible for any damage, data loss or lost productivity caused by use of this software. 
By downloading and using this software you agree to these terms and acknowledge the risks involved.
"""
import socket
import struct
import json
import threading
import time


class HelperClient:
    """Client for communicating with privileged helper daemon via Unix socket"""
    
    # Connection retry settings
    MAX_RETRIES = 3
    RETRY_DELAYS = [0.5, 1.0, 2.0]  # Exponential backoff
    
    def __init__(self, logger):
        self.logger = logger
        self.socket = None
        self.connected = False
        self.lock = threading.Lock()
        self.socket_path = None
        self.last_error = None
    
    def connect(self, socket_path, timeout=10.0):
        """Connect to helper daemon socket with retry logic"""
        self.socket_path = socket_path
        
        for attempt in range(self.MAX_RETRIES):
            try:
                # Clean up any existing socket
                self._close_socket()
                
                self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.socket.settimeout(timeout)
                self.socket.connect(socket_path)
                
                # Verify connection with a quick test
                self.socket.setblocking(False)
                self.socket.setblocking(True)
                
                self.connected = True
                self.last_error = None
                self.logger.info(f"Connected to helper daemon at {socket_path}")
                return True
                
            except socket.error as e:
                self.last_error = str(e)
                self.logger.warning(f"Connection attempt {attempt + 1}/{self.MAX_RETRIES} failed: {e}")
                self._close_socket()
                
                # Wait before retry (except on last attempt)
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAYS[attempt])
            
            except Exception as e:
                self.last_error = str(e)
                self.logger.error(f"Unexpected error connecting to helper: {e}")
                self._close_socket()
                break
        
        self.connected = False
        return False
    
    def disconnect(self):
        """Disconnect from helper daemon"""
        with self.lock:
            if self.socket:
                try:
                    # Send shutdown command with timeout
                    old_timeout = self.socket.gettimeout()
                    self.socket.settimeout(2.0)  # Short timeout for shutdown
                    self.send_command('shutdown')
                    self.socket.settimeout(old_timeout)
                except Exception as e:
                    self.logger.debug(f"Error sending shutdown command: {e}")
                
                self._close_socket()
            
            self.connected = False
            self.socket_path = None
            self.logger.info("Disconnected from helper daemon")
    
    def send_command(self, command, **params):
        """
        Send command to helper and receive response
        Returns: response dict or None on error
        """
        if not self.connected or not self.socket:
            raise RuntimeError(f"Not connected to helper daemon. Last error: {self.last_error}")
        
        with self.lock:
            try:
                # Prepare command
                command_data = {
                    'command': command,
                    'params': params
                }
                
                # Serialize to JSON
                message = json.dumps(command_data).encode('utf-8')
                
                # Validate message size (prevent overflow)
                if len(message) > 1024 * 1024:  # 1MB limit
                    raise ValueError(f"Message too large: {len(message)} bytes")
                
                # Send with length prefix
                length_prefix = struct.pack('!I', len(message))
                self._sendall_with_check(length_prefix + message)
                
                # Receive response length with timeout handling
                length_data = self._recv_exact(4)
                if not length_data:
                    raise RuntimeError("Connection closed by helper (no length header)")
                
                response_length = struct.unpack('!I', length_data)[0]
                
                # Validate response length
                if response_length > 1024 * 1024:  # 1MB limit
                    raise ValueError(f"Response too large: {response_length} bytes")
                
                # Receive response data
                response_data = self._recv_exact(response_length)
                if not response_data:
                    raise RuntimeError("Connection closed by helper (incomplete response)")
                
                # Parse JSON response
                try:
                    response = json.loads(response_data.decode('utf-8'))
                except json.JSONDecodeError as e:
                    raise RuntimeError(f"Invalid JSON response from helper: {e}")
                
                return response
                
            except socket.timeout as e:
                self.logger.error(f"Command '{command}' timed out: {e}")
                self.connected = False
                self.last_error = f"Timeout: {e}"
                raise RuntimeError(f"Command timed out: {e}")
            
            except socket.error as e:
                self.logger.error(f"Socket error during '{command}': {e}")
                self.connected = False
                self.last_error = f"Socket error: {e}"
                raise RuntimeError(f"Socket error: {e}")
            
            except Exception as e:
                self.logger.error(f"Command '{command}' error: {e}")
                self.connected = False
                self.last_error = str(e)
                raise
    
    def _recv_exact(self, num_bytes):
        """Receive exactly num_bytes from socket with timeout handling"""
        data = b''
        while len(data) < num_bytes:
            try:
                chunk = self.socket.recv(num_bytes - len(data))
                if not chunk:
                    self.logger.warning(f"Connection closed while receiving data (got {len(data)}/{num_bytes} bytes)")
                    return None
                data += chunk
            except socket.timeout:
                self.logger.error(f"Timeout while receiving data (got {len(data)}/{num_bytes} bytes)")
                raise
            except socket.error as e:
                self.logger.error(f"Socket error while receiving: {e}")
                return None
        return data
    
    def _sendall_with_check(self, data):
        """Send all data with error checking"""
        try:
            self.socket.sendall(data)
        except socket.timeout:
            self.logger.error("Timeout while sending data")
            raise
        except socket.error as e:
            self.logger.error(f"Socket error while sending: {e}")
            raise
    
    def _close_socket(self):
        """Close socket safely"""
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def is_connected(self):
        """Check if connected to helper"""
        if not self.connected:
            return False
        
        # Verify socket is still alive
        if not self.socket:
            self.connected = False
            return False
        
        return True
    
    def get_last_error(self):
        """Get the last connection error"""
        return self.last_error
