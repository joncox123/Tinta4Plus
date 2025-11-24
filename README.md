# Tinta4Plus
Now you can use the eInk display with Linux on the Lenovo ThinkBook Gen 4 Plus laptop!

[![Buy Me A Coffee](https://img.buymeacoffee.com/button-api/?text=Buy%20me%20a%20coffee&slug=joncox&button_colour=FFDD00&font_colour=000000&font_family=Inter&outline_colour=000000&coffee_colour=ffffff)](https://www.buymeacoffee.com/joncox)

<img src="eink-disable.jpg" alt="Diagram" width="60%"/>

## BRIEF WARNING AND DISCLAIMER
This software was independently developed without any input, support or documentation from either eInk or Lenovo. It has only been tested on one system, my own. While it has never damaged my hardware, either temporarily or permanently, it is possible for it to do so if it malfunctions. Temporary impairment can occur should corrupted or invalid commands be written to the Embedded Controller or the T-CON, and permanent damage is theoretically possible. If this occurs, you may need to hard reboot your system or even hard reset the EC (see instructions below). This software is currently a proof-of-concept demonstration, alpha-quality and has known bugs. Do not use this software if you are not willing to accept the risks of temporary or permanent hardware damage or data loss and lost productivity.

## System Requirements and Installation
At the present time, Tinta4Plus only works on exactly the following system configuration. You will need to install the following Linux distribution and configuration:
- Xubuntu 25.04 (Plucky Puffin) https://cdimage.ubuntu.com/xubuntu/releases/plucky/release/
  - Xorg X11 Window System (not tested yet on Wayland). Xorg is the default system for Xubuntu.
- Required Python 3 packages: `sudo apt install python3.13 python3-pip python3-portio python3-tk python3-usb`
- Required additional packages: `sudo apt install feh imv mokutil x11-xserver-utils xfconf`
- Disable Secure Boot so to control the eInk frontlight and other hardware features
  - Reboot your laptop and press ENTER repeatedly immediately after power on until you get the boot menu.
  - Hit the approprite F key to enter BIOS settings.
  - Navigate to Security and scroll down (near the bottom) to find Secure Boot. Change to Disabled.
  - Saving BIOS settings and reboot.
- Root permissions are required to write to the Embedded Controller (e.g. for frontlight control) and for the eInk controller (T-CON)

To run the app, simply cd into the extracted directory and execute: ./Tinta4Plus.py

## Missing Features and Known Bugs
- Display scaling is not being handeled correctly during switch, which also causes the eInk touch mapping to be off.
- Haven't figured out how to change the eInk contrast yet.
- Sometimes enabling the frontlight will return with an error, even though it is enabled. This is because the resulting EC register value can differ.
- No screen folding or swivel detection yet. eInk activation is purely a manual process.
- No screen rotation features.
- Does not disable keyboard or touchpad when activating eInk (e.g. when folding screen down).
- Eliminate need to request root permissions through signed kernel driver, system daemon, etc.
- Haven't figured out how to get the default THINKBOOK privacy image to persist on the eInk display when the display is disabled. I can flash it briefly, but it gets overwritten by a refresh. Regardless, I think the Tinta4Plus logo/image is cooler, so I don't plan on "fixing" this.

# END USER LICENSE AGREEMENT
Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

IMPORTANT - READ CAREFULLY BEFORE USING THIS SOFTWARE

This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects that result in data loss, corruption, hardware damage, lost productivity or other issues. Use at your own risk.

WARNING: This software may temporarily or permanently render your hardware inoperable. It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop. This software is a prototype, pre-production, alpha quality. It is only known to work, albeit with some bugs, on the author's specific hardware and Linux configuration.

### REQUIREMENTS AND RISKS:
1. Ubuntu / Xubuntu 25.04 "Plucky" with XFCE4 desktop environment is required (Xubuntu / XFCE4 only)
2. Xorg (X11) windowing system, not Wayland. The software has not been tested to work with Wayland.
3. Frontlight control requires access to the embedded controller (EC) which requires disabling Secure Boot in the BIOS. Disabling Secure Boot may reduce system security and expose you to certain types of attacks, including viruses, ransomware, rootkits and bootkits.
4. Root access is required to write to the EC
5. This software writes to low-level hardware, including the EC and the eInk display's T-CON
6. The software can potentially cause temporary or permanent damage to your hardware or data loss.
7. Should issues occur, usually a reboot is sufficient, but in some cases a full EC reset may be required. Hardware damage is theoretically possible.
8. This software was created without any input, endorcement or documentation from eInk or Lenovo and has been tested only on a single laptop. It is currently unknown whether it works correctly on different hardware revisions of the same laptop series.
9. If the privacy image fails to properly display when switching from eInk to OLED screens, or if the software crashes or powers off before the privacy image sequence can complete, the eInk display will show a persistent image of the last screen until a full reboot. This could potentially expose personal information such as passwords, financial information, proprietary information like intellectual property or information that is embrassing to the user. Therefore, always ensure that the eInk display has been cleared of such information after use, and if not, perform a full reboot.

### DO NOT MODIFY THE CODE IN ECController.py or EInkUSBController.py, as doing so may cause hardware damage.

### LIABILITY:
The author is not responsible for any damage, data loss, lost productivity, or other issues caused by use of this software.

### IN THE EVENT OF HARDWARE PROBLEMS
Should unexpected behvior occur, usually a full reboot will resolve the issue. In rare cases, a full reset of the Embedded Controller (EC) may be required. The procedure for resetting the EC is as follows:

1. Power off the laptop and disconnect the AC power adapter.
2. Use a pin, small paperclick or SIM card ejector tool to press and HOLD the small reset button for AT LEAST 60 seconds (time with a clock!). The reset button is located on the bottom of the laptop just to one side of the fan vent grille and looks like an extra, out of place hole. It has a tiny symbol that looks like an arch with an arrow on one end.
3. After holding the reset for 60 seconds, press and HOLD the power button continusouly for 60 seconds.
4. Lastly, press the power button normally (may require a few presses or waiting some seconds) to power up the laptop. Typically, the screen will stay blank for some time, often up to 60 seconds, before the laptop powers up normally.
5. Check your BIOS settings by pressing ENTER at boot to ensure Secure Boot is disabled again.
