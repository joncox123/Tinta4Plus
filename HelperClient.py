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


class HelperClient:
    """Client for communicating with privileged helper daemon via Unix socket"""
    
    def __init__(self, logger):
        self.logger = logger
        self.socket = None
        self.connected = False
        self.lock = threading.Lock()
    
    def connect(self, socket_path, timeout=10.0):
        """Connect to helper daemon socket"""
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket.settimeout(timeout)
            self.socket.connect(socket_path)
            self.connected = True
            self.logger.info(f"Connected to helper daemon at {socket_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to helper: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from helper daemon"""
        if self.socket:
            try:
                # Send shutdown command
                self.send_command('shutdown')
            except:
                pass
            
            try:
                self.socket.close()
            except:
                pass
            
            self.connected = False
            self.logger.info("Disconnected from helper daemon")
    
    def send_command(self, command, **params):
        """
        Send command to helper and receive response
        Returns: response dict or None on error
        """
        if not self.connected or not self.socket:
            raise RuntimeError("Not connected to helper daemon")
        
        with self.lock:
            try:
                # Prepare command
                command_data = {
                    'command': command,
                    'params': params
                }
                
                # Serialize to JSON
                message = json.dumps(command_data).encode('utf-8')
                
                # Send with length prefix
                length_prefix = struct.pack('!I', len(message))
                self.socket.sendall(length_prefix + message)
                
                # Receive response length
                length_data = self._recv_exact(4)
                if not length_data:
                    raise RuntimeError("Connection closed by helper")
                
                response_length = struct.unpack('!I', length_data)[0]
                
                # Receive response data
                response_data = self._recv_exact(response_length)
                if not response_data:
                    raise RuntimeError("Connection closed by helper")
                
                # Parse JSON response
                response = json.loads(response_data.decode('utf-8'))
                
                return response
                
            except Exception as e:
                self.logger.error(f"Command error: {e}")
                self.connected = False
                raise
    
    def _recv_exact(self, num_bytes):
        """Receive exactly num_bytes from socket"""
        data = b''
        while len(data) < num_bytes:
            chunk = self.socket.recv(num_bytes - len(data))
            if not chunk:
                return None
            data += chunk
        return data
    
    def is_connected(self):
        """Check if connected to helper"""
        return self.connected
