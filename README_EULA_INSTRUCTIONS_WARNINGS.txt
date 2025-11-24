INSTRUCTIONS AND END USER LICENSE AGREEMENT

Copyright (c) 2025 Jon Cox (joncox123). All rights reserved.

IMPORTANT - READ CAREFULLY BEFORE USING THIS SOFTWARE

This software is provided "AS IS", without any warranty of any kind. It may contain bugs or other defects that result in data loss, corruption, hardware damage, lost productivity or other issues. Use at your own risk.

WARNING: This software may temporarily or permanently render your hardware inoperable. It may corrupt or damage the Embedded Controller or eInk T-CON controller in your laptop. This software is a prototype, pre-production, alpha quality. It is only known to work, albeit with some bugs, on the author's specific hardware and Linux configuration.


REQUIREMENTS AND RISKS:
1. Ubuntu / Xubuntu 25.04 "Plucky" with XFCE4 desktop environment is required (Xubuntu / XFCE4 only)

2. Xorg (X11) windowing system, not Wayland. The software has not been tested to work with Wayland.

3. Frontlight control requires access to the embedded controller (EC) which requires disabling Secure Boot in the BIOS. Disabling Secure Boot may reduce system security and expose you to certain types of attacks, including viruses, ransomware, rootkits and bootkits.

4. Root access is required to write to the EC

5. This software writes to low-level hardware, including the EC and the eInk display's T-CON

6. The software can potentially cause temporary or permanent damage to your hardware or data loss.

7. Should issues occur, usually a reboot is sufficient, but in some cases a full EC reset may be required. Hardware damage is theoretically possible.

8. This software was created without any input, endorcement or documentation from eInk or Lenovo and has been tested only on a single laptop. It is currently unknown whether it works correctly on different hardware revisions of the same laptop series.

9. If the privacy image fails to properly display when switching from eInk to OLED screens, or if the software crashes or powers off before the privacy image sequence can complete, the eInk display will show a persistent image of the last screen until a full reboot. This could potentially expose personal information such as passwords, financial information, proprietary information like intellectual property or information that is embrassing to the user. Therefore, always ensure that the eInk display has been cleared of such information after use, and if not, perform a full reboot.

DO NOT MODIFY THE CODE IN ECController.py or EInkUSBController.py, as doing so may cause hardware damage.


LIABILITY:
The author is not responsible for any damage, data loss, lost productivity, or other issues caused by use of this software.


INSTRUCTIONS FOR USE:
1. This software has been tested only on the Lenovo ThinkBook Plus Gen 4 IRU laptop. It will not work on any other.

2. The only supported Linux distribution is Ubuntu/Xubuntu 25.04 "Plucky" running XFCE4 desktop environment (Xubuntu) and Xorg (not Wayland). It will not work properly with GNOME and has not been tested with any other configuration. Therefore, you first need to install Xubuntu and make it the default dekstop prior to use.

3. To use frontlight controls, first disable Secure Boot in the BIOS settings by pressing ENTER immediately after powering on the laptop.

4. The current version probably won't work correctly if an external monitor is connected.


IN THE EVENT OF HARDWARE PROBLEMS
Should unexpected behvior occur, usually a full reboot will resolve the issue. In rare cases, a full reset of the Embedded Controller (EC) may be required. The procedure for resetting the EC is as follows:

1. Power off the laptop and disconnect the AC power adapter.

2. Use a pin, small paperclick or SIM card ejector tool to press and HOLD the small reset button for AT LEAST 60 seconds (time with a clock!). The reset button is located on the bottom of the laptop just to one side of the fan vent grille and looks like an extra, out of place hole. It has a tiny symbol that looks like an arch with an arrow on one end.

3. After holding the reset for 60 seconds, press and HOLD the power button continuously for 60 seconds.

4. Lastly, press the power button normally (may require a few presses or waiting some seconds) to power up the laptop. Typically, the screen will stay blank for some time, often up to 60 seconds, before the laptop powers up normally.

5. Check your BIOS settings by pressing ENTER at boot to ensure Secure Boot is disabled again.


AGREEMENT:
By clicking "Agree" below, you acknowledge that you have read and understood this agreement, and you agree to accept all risks associated with using this software. You acknowledge that you are using this software entirely at your own risk.

If you do not agree to these terms, click "Disagree" and do not use this software.
