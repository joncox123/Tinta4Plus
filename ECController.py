"""
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

WARNING: This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects
that result in data loss, corruption, hardware damage or other issues. Use at your own risk.
It may temporarily or permanently render your hardware inoperable.
It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop.
The author is not responsible for any damage, data loss or lost productivity caused by use of this software. 
By downloading and using this software you agree to these terms and acknowledge the risks involved.
"""

import time
import portio
import subprocess


class ECController:
    """Embedded Controller register access via I/O ports"""
    
    # EC I/O ports
    EC_SC_PORT = 0x66     # Status/Command port
    EC_DATA_PORT = 0x62    # Data port
    
    # Status bits
    EC_STAT_OBF = 0x01    # Output buffer full
    EC_STAT_IBF = 0x02    # Input buffer full
    
    # Commands
    EC_CMD_READ = 0x80
    EC_CMD_WRITE = 0x81
    
    # Timing
    TIMEOUT_US = 500000   # 500ms timeout
    POLL_DELAY_US = 50    # 50µs poll delay
    
    # EC registers (from frontlight-EC-reg-values.txt)
    REG_BRIGHTNESS = 0x35  # PWM duty cycle (0x00-0x20, steps of 4)
    REG_POWER = 0x25       # Frontlight power (0x0A=on, 0x05=off)
    
    def __init__(self, logger):
        self.logger = logger
        self.access_available = False
        self.secure_boot_enabled = False
        self.error_message = None
        self._check_secure_boot()
        self._init_ports()
    
    def _check_secure_boot(self):
        """Check if Secure Boot is enabled"""
        try:
            result = subprocess.run(['mokutil', '--sb-state'],
                                  capture_output=True, text=True, timeout=2)
            output = result.stdout.strip()

            if 'SecureBoot enabled' in output:
                self.secure_boot_enabled = True
                self.error_message = "Secure Boot is enabled. Please disable Secure Boot in BIOS settings."
                self.logger.warning("Secure Boot is enabled - EC access will be blocked")
            else:
                self.logger.info(f"Secure Boot status: {output}")
        except FileNotFoundError:
            self.logger.warning("mokutil not found, cannot check Secure Boot status")
        except Exception as e:
            self.logger.warning(f"Could not check Secure Boot status: {e}")

    def _init_ports(self):
        """Request I/O port access and verify it works (requires root)"""
        if self.secure_boot_enabled:
            self.logger.error("Cannot initialize ports: Secure Boot is enabled")
            self.access_available = False
            return

        try:
            # Request port access
            portio.ioperm(self.EC_DATA_PORT, 1, 1)
            portio.ioperm(self.EC_SC_PORT, 1, 1)
            self.logger.info("EC I/O port access granted")

            # Verify we can actually read from the ports (safe operation)
            self._verify_port_access()

            self.access_available = True
            self.logger.info("EC port access verified")

        except PermissionError as e:
            self.error_message = "Permission denied. Please run as root or disable Secure Boot in BIOS."
            self.logger.error(f"Failed to get I/O port access: {e}")
            self.access_available = False
        except Exception as e:
            self.error_message = f"Failed to initialize EC access: {str(e)}"
            self.logger.error(f"Failed to get I/O port access: {e}")
            self.access_available = False

    def _verify_port_access(self):
        """Verify port access by reading status register (safe, read-only operation)"""
        try:
            # Read the EC status register - this is a safe, read-only operation
            # that won't change EC state
            status = portio.inb(self.EC_SC_PORT)
            self.logger.debug(f"EC status register read successfully: 0x{status:02x}")

            # Try reading it a few more times to ensure consistent access
            for _ in range(3):
                portio.inb(self.EC_SC_PORT)
                time.sleep(0.001)  # 1ms delay

        except Exception as e:
            raise RuntimeError(f"Port access verification failed: {e}")

    def get_access_status(self):
        """
        Get the current EC access status.
        Returns: dict with keys:
            - 'available': bool, True if EC access is working
            - 'secure_boot_enabled': bool, True if Secure Boot is enabled
            - 'error_message': str or None, human-readable error message
        """
        return {
            'available': self.access_available,
            'secure_boot_enabled': self.secure_boot_enabled,
            'error_message': self.error_message
        }

    def read_brightness(self):
        """
        Read current brightness level from EC
        Returns: brightness level (0-8), or None if read fails
        """
        if not self.access_available:
            return None

        try:
            ec_value = self.read_byte(self.REG_BRIGHTNESS)
            # Convert EC value (0x00-0x20 in steps of 4) to level (0-8)
            level = ec_value // 4
            self.logger.debug(f"Read brightness: EC value=0x{ec_value:02x}, level={level}")
            return level
        except Exception as e:
            self.logger.error(f"Failed to read brightness: {e}")
            return None

    def get_frontlight_state(self):
        """
        Read current frontlight power state from EC
        Returns: True if enabled, False if disabled, None if read fails
        """
        if not self.access_available:
            return None

        try:
            power_value = self.read_byte(self.REG_POWER)
            self.logger.debug(f"Read frontlight power: 0x{power_value:02x}")
            # 0x06 = enabled, 0x05 = disabled (based on your readback values)
            return power_value == 0x06
        except Exception as e:
            self.logger.error(f"Failed to read frontlight state: {e}")
            return None

    def _wait_ibf_clear(self):
        """Wait for input buffer to be empty"""
        waited = 0
        self.logger.debug(f"_wait_ibf_clear: reading from port 0x{self.EC_SC_PORT:02x}")
        while waited < self.TIMEOUT_US:
            status = portio.inb(self.EC_SC_PORT)

            if not (status & self.EC_STAT_IBF):
                self.logger.debug(f"_wait_ibf_clear: IBF clear (status=0x{status:02x})")
                return True

            time.sleep(self.POLL_DELAY_US / 1_000_000)
            waited += self.POLL_DELAY_US

        raise TimeoutError("EC input buffer timeout (IBF)")
    
    def _wait_obf_set(self):
        """Wait for output buffer to be full"""
        waited = 0
        while waited < self.TIMEOUT_US:
            status = portio.inb(self.EC_SC_PORT)
            
            if status & self.EC_STAT_OBF:
                return True
            
            time.sleep(self.POLL_DELAY_US / 1_000_000)
            waited += self.POLL_DELAY_US
        
        raise TimeoutError("EC output buffer timeout (OBF)")
    
    def read_byte(self, address):
        """Read a byte from EC RAM"""
        self._wait_ibf_clear()
        
        portio.outb(self.EC_CMD_READ, self.EC_SC_PORT)
        
        self._wait_ibf_clear()
        
        portio.outb(address, self.EC_DATA_PORT)
        
        self._wait_obf_set()
        
        value = portio.inb(self.EC_DATA_PORT)
        
        return value
    
    def write_byte(self, address, value):
        """Write a byte to EC RAM"""
        self.logger.debug(f"write_byte: address=0x{address:02x}, value=0x{value:02x}")

        self.logger.debug("write_byte: waiting for IBF clear (1/4)")
        self._wait_ibf_clear()

        self.logger.debug(f"write_byte: sending WRITE command (0x{self.EC_CMD_WRITE:02x}) to port 0x{self.EC_SC_PORT:02x}")
        portio.outb(self.EC_CMD_WRITE, self.EC_SC_PORT)

        self.logger.debug("write_byte: waiting for IBF clear (2/4)")
        self._wait_ibf_clear()

        self.logger.debug(f"write_byte: sending address (0x{address:02x}) to port 0x{self.EC_DATA_PORT:02x}")
        portio.outb(address, self.EC_DATA_PORT)

        self.logger.debug("write_byte: waiting for IBF clear (3/4)")
        self._wait_ibf_clear()

        self.logger.debug(f"write_byte: sending value (0x{value:02x}) to port 0x{self.EC_DATA_PORT:02x}")
        portio.outb(value, self.EC_DATA_PORT)

        self.logger.debug("write_byte: waiting for IBF clear (4/4)")
        self._wait_ibf_clear()

        self.logger.debug("write_byte: complete")
        return True
    
    def write_and_verify(self, address, value):
        """Write byte to EC, wait 100ms, read back and return value"""
        # Write the value
        self.write_byte(address, value)
        
        # Wait 100ms as requested
        time.sleep(0.1)
        
        # Read back
        readback = self.read_byte(address)
        
        return readback
    
    def set_brightness(self, level):
        """
        Set frontlight brightness level (0-8)
        Maps to EC register values: 0x00, 0x04, 0x08, ..., 0x20
        Returns: (success, readback_value)
        """
        if not 0 <= level <= 8:
            raise ValueError("Brightness level must be 0-8")
        
        # Convert 0-8 to EC register value (steps of 4)
        ec_value = level * 4
        
        self.logger.info(f"Setting brightness to level {level} (EC value 0x{ec_value:02x})")
        readback = self.write_and_verify(self.REG_BRIGHTNESS, ec_value)
        
        success = (readback == ec_value)
        if not success:
            self.logger.warning(f"Brightness readback mismatch: wrote 0x{ec_value:02x}, read 0x{readback:02x}")
        
        return success, readback
    
    def enable_frontlight(self, brightness_level=None):
        """
        Enable frontlight power and optionally set brightness
        Args:
            brightness_level: Optional brightness level (0-8) to set after enabling
        Returns: (success, readback_value)
        """
        self.logger.info("Enabling frontlight")
        readback = self.write_and_verify(self.REG_POWER, 0x0A)
        success = (readback == 0x06 or readback == 0x0A)

        if not success:
            self.logger.warning(f"Frontlight enable readback mismatch: expected 0x06, read 0x{readback:02x}")
        else:
            # If frontlight was successfully enabled and brightness level was provided, set it
            if brightness_level is not None:
                self.logger.info(f"Setting brightness to {brightness_level} after enabling frontlight")
                brightness_success, brightness_readback = self.set_brightness(brightness_level)
                if not brightness_success:
                    self.logger.warning(f"Failed to set brightness after enabling frontlight")

        return success, readback
    
    def disable_frontlight(self):
        """
        Disable frontlight power
        Returns: (success, readback_value)
        """
        self.logger.info("Disabling frontlight")
        readback = self.write_and_verify(self.REG_POWER, 0x05)
        success = (readback == 0x05 or readback == 0x09)
        
        if not success:
            self.logger.warning(f"Frontlight disable readback mismatch: wrote 0x05, read 0x{readback:02x}")
        
        return success, readback