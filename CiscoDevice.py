###########################################################################
## Export of Script Module: CiscoDevice
## Language: Python
## Category: Internal
## Description: Library to help when interacting with Cisco devices.
###########################################################################
#------------------------------------------------------------------------------
# NetMRI Python Library for Cisco Devices
# CiscoDevice.py
#
# Austin Ensminger
# Copyright (c) 2023 Infoblox, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# DESCRIPTION:
#   This is a NetMRI library to help when interacting with Cisco devices.
#   
#   Supported Cisco Platforms: 
#       - IOS
#       - IOS-XE
#       - NX-OS 5K/6K/7K [Version 4.0(1), or higher]
#       - NX-OS 3K/9K
#       - Adaptive Security Appliance (ASA) 5500-X Series [Ver. 9, or higher]
#------------------------------------------------------------------------------
import re

class CiscoDevice:
    def __init__(self, easy_class):
        self.dis = easy_class                   # NetMRI Easy instance
        self.device = easy_class.get_device()   # DeviceRemote broker
        self.model = self.device.DeviceModel    # Target model name
        self.hostname = self.device.DeviceName  # Target host name
        self.version = self.device.DeviceVersion# Target running version
        self.verinfo = {}                       # Running version (detailed)
        self.os = None                          # Target OS type. Used to determined CLI syntax
        self.platform = None                    # System platform (e.g: c3560cx)
        self.in_config_mode = False             # State for config terminal
        self.active_intfs = []                  # Interfaces that have an IP and are up/up.
        self.relay_intfs = {}                   # Interfaces /w relays, and the conf. relays.
        self.current_system_image = None        # Current running image
        self.current_system_image_fs = None     # FS where the current running image resides
        self.system_fs = None                   # The default file system on this device
        self.system_fs_info = {}                # Dict of system fs and their free space
        self.asa_multi_context = False          # Boolean flag for ASA multi-context
        self.asa_admin_context = False          # Boolean flag for admin context
        self.asa_admin_context_name = None      # Name of the ASA admin context
        self.asa_is_lfbff = False               # ASA is using Legacy Free Boot File Format.
        self.asa_is_smp = False                 # ASA is Multi-core
        self.iosxe_boot_mode = None             # IOS-XE boot mode (INSTALL/BUNDLE)
        self.iosxe_build = None                 # IOS-XE build, read from packages.conf
        self.iosxe_sdwan = {"mode": None}       # IOS-XE SD-WAN managed device
        self.nxos_kickstart_image = None        # Current NX-OS kickstart
        self.nxos_aci_mode = False              # Boolean flag for NX-OS in ACI mode
        self.nxos_vdc = False                   # Boolean flag for N7k/N77 VDC
        self.nxos_default_vdc_name = None       # Default VDC name
        self.nxos_default_vdc = False           # Boolean flag for NX-OS default VDC
        
        # Determine OS type.
        # This needs to be performed on init. All other methods rely on it.
        if "Adaptive Security" in self.device.DeviceSysDescr:
            self.os = "ASA"
            # asa933-7-lfbff-k8.SPA - 5506-X, 5508-X, 5516-X.
            if any(lfbffmodel in self.model for lfbffmodel in
                   ["5506", "5508", "5516"]):
                self.asa_is_lfbff = True
            # asa924-5-smp-K8.bin - 5512-X, 5515-X, 5525-X, 5545-X, 5555-X
            #                     - 5585-X, ASAv
            # TODO: ASAv?
            if any(smpmodel in self.model for smpmodel in
                   ["5512", "5515", "5525", "5545", "5555", "5585"]):
                self.asa_is_smp = True

            # NOTE: ASA prior to 9.10 uses format like this:
            #       asa{maj}{min}{maint}-{patch}-...
            #       After 9.10, the format changes to:
            #       asa{maj}-{min}-{maint}-{patch}-....
            self.verinfo = {
                'maj': None,    # (int) Major release
                'min': None,    # (int) Minor release
                'maint': None,  # (int) Maintenance release
                'rebld': None   # (int) Patch
            }
            match = re.search(r'(\d)-?(\d+)-?(\d)-(\d+)?', self.version)

            if match:
                self.verinfo['maj'] = int(match.group(1))
                self.verinfo['min'] = int(match.group(2))
                self.verinfo['maint'] = int(match.group(3))
                self.verinfo['rebld'] = (
                    int(match.group(4)) if match.group(4) else None
                )

            # Check if this is a context.
            # If it is, then set the flag.
            raw_output = self.dis.send_command(
                "show version | include Cisco Adaptive"
            )
            if "<context>" in raw_output:
                self.asa_multi_context = True
                # Then we need to check if we are in the admin context.
                # Admin contexts have astrisk (*) at the beginning
                # of the context name.
                raw_output = self.dis.send_command(
                    "show context | include ^\*"
                )
                # We matched the asterisk, so we are in an admin context.
                # Set the flag, and capture the context name.
                if raw_output:
                    self.asa_admin_context = True
                    self.asa_admin_context_name = re.search(
                        r"(?<=\*)(\w+)", raw_output
                    ).group(1)

            # TODO: DeviceRemote.DeviceContextName is broken.
            #       This would replace the code from above, 
            #       and we wouldn't need CLI interaction.
            # if self.device.VirtualInd:
            #     self.asa_multi_context = True
            #     # Then, check if this is an admin context.
            #     # Admin context have parent_device == None
            #     if self.device.parent_device is None:
            #         self.asa_admin_context = True
            #         self.asa_admin_context_name = self.device.DeviceContextName            

        elif "NX-OS" in self.device.DeviceSysDescr:
            self.os = "NX-OS"
            if "aci" in self.device.DeviceSysDescr:
                self.nxos_aci_mode = True
            # If this is a N7k, get the VDC info.
            if (self.device.DeviceModel.startswith("N7K") or
                    self.device.DeviceModel.startswith("N77")):
                self.nxos_vdc = True
                raw_output = self.dis.send_command("show vdc current-vdc")
                match = re.search(
                    r'Current\s+vdc\s+is\s+(\d+)\s+-\s+(\S+)', raw_output
                )
                if match:
                    self.vdc_id = int(match.group(1))
                    self.nxos_default_vdc_name = match.group(2)
                    if self.vdc_id == 1:
                        self.nxos_default_vdc = True

            # Set version info
            self.verinfo = {
                'maj': None,    # (int) Major release
                'min': None,    # (int) Minor release
                'maint': None,  # (int) Maintenance release
                'rebld': None   # (str) Rebuild
            }
            match = re.search(r'(\d+)\.(\d+)\((\d+)(\w+)?\)(.*)',
                                   self.version)
            if match:
                self.verinfo['maj'] = int(match.group(1))
                self.verinfo['min'] = int(match.group(2))
                self.verinfo['maint'] = int(match.group(3))
                self.verinfo['rebld'] = match.group(4)

        # IOS-XE has many different variations in the sysDescr.0 ...
        elif ("IOSXE" in self.device.DeviceSysDescr
              or "IOS-XE" in self.device.DeviceSysDescr
              or "IOS XE" in self.device.DeviceSysDescr
              or "LINUX_IOSD" in self.device.DeviceSysDescr
              or "CAT3K_" in self.device.DeviceSysDescr):
            self.os = "IOS-XE"

            # Set version info
            self.verinfo = {
                'maj': None,    # (int) Major release
                'rel': None,    # (int) Release version
                'rebld': None,  # (int) Rebuild
                'spcrel': None, # (str) Special release
                'train': None,  # (str) Train (IOS-XE 3X)
                'iosd': None    # (str) IOSd (IOS-XE 3X)
            }
            match = re.search(
                r'(\d+)\.(\d+)\.(\d+)\.?([a-zA-Z0-9]+)\.?(\S+)?', self.version
            )
            if match:
                self.verinfo['maj'] = int(match.group(1))
                self.verinfo['rel'] = int(match.group(2))
                self.verinfo['rebld'] = int(match.group(3))
                # IOS-XE "Peaks"
                if self.verinfo['maj'] >= 16:
                    self.verinfo['spcrel'] = match.group(4)
                # IOS-XE 3X
                elif self.verinfo['maj'] == 3:
                    self.verinfo['train'] = match.group(4)
                    self.verinfo['iosd'] = match.group(5)

        elif "IOS" in self.device.DeviceSysDescr:
            self.os = "IOS"

            # Set version info
            self.verinfo = {
                'maj': None,    # (int) Major version / Main release
                'min': None,    # (int) Release version / Major feature
                'feat': None,   # (str) Feature release number
                'type': None,   # (str) Type / Train
                'maint': None   # (str) Maintenance rebuild
            }
            match = re.search(
                r'(\d+)\.(\d+)\(([a-zA-Z0-9]+)\)([A-Z]+)([a-z0-9]+)?',
                self.version
            )
            if match:
                self.verinfo['maj'] = int(match.group(1))
                self.verinfo['min'] = int(match.group(2))
                self.verinfo['feat'] = match.group(3)
                self.verinfo['type'] = match.group(4)
                self.verinfo['maint'] = match.group(5)

        # If we got here, we got problems.
        else:
            raise ValueError("Unable to determine OS")


    def get_system_image_info(self):
        """Get the current system image name, the platform, and the fs it's
        stored on.

        Sets: Class attributes
            - platform (str): Platform of the device. Dervied from the running
                              image or from packages.conf.
                              (e.g: c3560cx-adventerprise... makes c3560cx)
            - current_system_image_fs (str): Fs the running image is on.
            - current_system_image (str): The current running image filename.
            - nxos_kickstart_image (str): NX-OS kickstart.
            - iosxe_boot_mode (str): "INSTALL" or "BUNDLE".
            - iosxe_build (str): IOS-XE build from packages.conf.
            - iosxe_sdwan (dict): SD-WAN operating mode.
                - 'mode' (str): Values are:
                    - 'unknown' if Undetermined
                    - 'autonomous' if Autonomous
                    - 'managed' if Controller-Managed
                    - None if not running SD-WAN
        """
        # If this is an ASA admin context, then we need to change context to
        # the system context.
        if self.os == "ASA" and self.asa_multi_context:
                if self.asa_admin_context:
                    self.dis.send_command("changeto system")
                else:
                    raise Exception(
                        "Cannot be called to a non-admin ASA context."
                    )

        if self.os == "NX-OS" and self.nxos_aci_mode == True:
            cmd = "show version | grep image"
        else:
            cmd = "show version | include image"

        raw_output = self.dis.send_command(cmd)

        # If ASA context, put us back in the admin context
        if self.asa_admin_context:
            self.dis.send_command(
                f"changeto context {self.asa_admin_context_name}"
            )

        # Replace spaces to make regex easier
        raw_output = raw_output.replace(" ","")

        if self.os == "NX-OS":
            if self.nxos_aci_mode:
                # NX-OS in ACI mode is always /bootflash/
                self.current_system_image_fs = re.search(
                    r'(?<=/)(.*?)(?=/)', raw_output
                ).group(1)

                if "kickstart" in raw_output:
                    self.nxos_kickstart_image = re.search(
                        r'kickstart.*/(?<=/)(.*)', raw_output
                    ).group(1)
            else:
            # NOTE: NX-OS prior to 7.0(3) has system and kickstart.
                self.current_system_image_fs = re.search(
                    r'(?<=\:)(.*?)(?=\:)', raw_output
                ).group(1)

                self.current_system_image = re.search(
                    r'(?:system|NXOS).*(?<=/)/+(.*)', raw_output
                ).group(1)
                
                if "kickstart" in raw_output:
                    self.nxos_kickstart_image = re.search(
                        r'kickstart.*/(?<=/)/+(.*)', raw_output).group(1)

        # This is an IOS, IOS-XE, or ASA device
        else: 
            # Regex the file system where the system image is stored.
            self.current_system_image_fs = re.search(
                r'(?<=\")(.*?)(?=\:)', raw_output
            ).group(1)

            # Regex the current system image
            # We don't specify the .bin extension, because in IOS-XE
            # INSTALL mode the file extension is '.conf', and ASA uses
            # different extensions as well.
            # Keep in mind: easy.send_command() will self-escape
            # quotes. So we positive lookahead on \, not a quote.
            self.current_system_image = re.search(
                r'(?<=\:)/?(.*?)(?=\\)', raw_output
            ).group(1)

            if self.current_system_image.endswith(".conf"):
                # We need to read the superpackage information.
                # Capture it to bldplat, so that we can match both the build
                # and platform later.
                self.iosxe_boot_mode = "INSTALL"
                bldplat = self.dis.send_command(
                    f"more {self.current_system_image_fs}:/"
                    f"{self.current_system_image} | include Platform:|Build:"
                )
                match = re.search(r'#\s+pkginfo:\s+Build:\s+(\S+)',
                                       bldplat)
                if match:
                    self.iosxe_build = match.group(1)
                # Some IOS-XE do not have the
                # superpackage info in the conf file. Try another method.
                # (This was observed on a Cat93k on 16.6.6)
                else:
                    # We try reading the version from rp_base
                    cmd = ("more flash:/packages.conf"
                                " | include rp_base.*\.pkg")
                    rp_base = self.dis.send_command(cmd)
                    # Lookbehind, then match maj.rel.rbld group.
                    match = re.search(
                        r'(?<=)\.(\d+\.\d+\.\d+[a-zA-Z]?)\..*', rp_base
                    )
                    if match:
                        self.iosxe_build = match.group(1)
                # Raise if we still didn't get anything.
                if not self.iosxe_build:
                    raise TypeError
            else:
                self.iosxe_boot_mode = "BUNDLE"

        # Get the platform from the running image.
        if self.os == "ASA":
            self.platform = self.os.lower()
        elif self.os == "NX-OS" and self.nxos_aci_mode == True:
            self.platform = re.search(
                r'(aci-[a-zA-Z0-9]+)(?:-|_|\.).*$', self.current_system_image
            ).group(1)
        else:
            if self.iosxe_boot_mode == "INSTALL":
                # We already grabbed this from before.
                # Now just match the platform
                match = re.search(
                    r'#\s+pkginfo:\s+Platform:\s+([a-zA-Z0-9_-]+)',
                    bldplat
                )
                # Regex the platform from the .conf file.
                # Platform is in uppercase. Convert to lowercase and save it.
                if match:
                    # 2023.05.31 - aensminger: IOS-XE 3X for cat3k shows
                    # platform as "ng3k". Convert it to cat3k_caa.
                    self.platform = (
                        "cat3k_caa" if match.group(1).lower() == "ng3k"
                        else match.group(1).lower()
                    )
                # Some IOS-XE do not have the
                # superpackage info in the conf file. Try another method.
                # (This was observed on a Cat93k on 16.6.6)
                else:
                    # We don't need to send command again. We already have
                    # what we want stored in rp_base.
                    match = re.search(r'(?<=\s)([a-zA-Z0-9_]+)(?=-)',
                                           rp_base)
                    if match:
                        # It's already in lowercase.
                        self.platform = match.group(1)
            else: # boot_mode == "BUNDLE"
                # CAT92k uses cat9k_lite. Other use cat9k_iosxe.
                # Updated regex pattern to match both cases.
                # NOTE: NX-OS higher than 7.0(3)I2(1) uses one image "nxos".
                self.platform = re.search(
                    r'([a-zA-Z0-9]+(_lite|_iosxe)?)(?:-|_|\.).*',
                    self.current_system_image
                ).group(1)
                # C8300 and C8500 used to be individual platforms.
                # Cisco has consolidated them to "c8000"
                if (self.platform.startswith("c8300")
                        or self.platform.startswith("c8500")):
                    self.platform = self.platform.replace("c8300", "c8000")
                    self.platform = self.platform.replace("c8500", "c8000")

        # Figure out if this is an SD-WAN device.
        if (self.os == "IOS-XE" and
            self.current_system_image.startswith(self.platform + "-ucmk9.")):
            # Running image is SD-WAN image. Set mode to "unknown" for now.
            self.iosxe_sdwan = {"mode": 'unknown'}
        # Get the SD-WAN operating mode.
        if (self.os == "IOS-XE"
            and any(self.platform.startswith(plat) for plat in (
            "ir1101", "isr1", "isr4", "isrv", "asr1", "c1000v", "c1100",
            "c8000", "c8200", "c8300", "c8500"
            ))):
            cmd = "show version | include operating"
            raw_output = self.dis.send_command(cmd)
            #If it's SD-WAN, we'll get output from the command:
            #Router operating mode: Controller-Managed
            #Router operating mode: Autonomous
            if raw_output:
                # Regex match 'operating.*', then do a
                # positive lookbehind for ':', then spaces,
                # then finally the capture group. Capture group is the mode.
                match = re.match(r'operating.*(?<=\:)\s+(.*)',
                                      raw_output)
                if match:
                    if "Autonomous" in match.group(1):
                        self.iosxe_sdwan = {"mode": 'autonomous'}
                    if "Controller-Managed" in match.group(1):
                        self.iosxe_sdwan = {"mode": 'managed'}


    def get_system_fs_info(self):
        """Get the default File System (fs) free space, as well as additional
        fs, and their respective free space. (e.g: switch stacks)

        Sets: Class attributes
            - system_fs_info (dict): Nested dictionary, with keys:
                - id (int): Fs index. (Default fs is always 0)
                    - 'fs' (str): The fs name (e.g: bootflash)
                    - 'free' (int): Bytes free in this file system

        Structure is: 
            {
                0: {
                    'fs': '<default fs name>',
                    'free': <bytes free>
                },
                <additional fs>: {
                    'fs': '<additional fs name>,
                    'free': <add. fs bytes free>
                },
                ...
            }
        """
        # Safety net
        if not self.current_system_image_fs:
            raise TypeError("current_system_image_fs is not initialized")

        # NX-OS does not have 'show file system'. So we just dir bootflash.
        if self.os == "NX-OS":
            cmd = f"dir {self.current_system_image_fs}: | include free"
            raw_output = self.dis.send_command(cmd)

            fs_bytes_free = re.search(r'(\d+)\s\bbytes free\b',
                                        raw_output).group(1)

            self.system_fs = self.current_system_image_fs

            self.system_fs_info = {
                0: {"fs": self.current_system_image_fs, "free": fs_bytes_free}
            }
            return

        # If ASA multi-context and we are admin context, then changeto system
        if self.asa_multi_context and self.asa_admin_context:
            self.dis.send_command("changeto system")

        raw_output = self.dis.send_command("show file system")

        # Change context back
        if self.asa_admin_context:
            self.dis.send_command(
                f"changeto context {self.asa_admin_context_name}"
            )

        # Capture default fs prefix (it's marked by an asterisk)
        # 2023.05.25 - aensminger - Update regex to not capture "#".
        # Some Cisco devices show "#" flag ater the fs name to indicate that
        # file system is bootable. (e.g: flash:#)
        match = re.search(
            r'(?:\*)(?:\s+)?(\-|\d+)(?:\s+)?(\-|\d+)(?:\s+)?(\w+)'
            r'(?:\s+)?(\w+)(?:\s+)?([^#\s]+)(?:\s+)?(.*)', raw_output
        )
        self.system_fs = match.group(5).replace(":","")

        # Now we build the system_fs_info dictionary
        # Thankfully, switch stacks and redundant sup modules also contain
        # the system_fs in the string.
        # (e.g: bootflash => slavebootflash
        #       slot0 => slaveslot0
        #       flash => flash-1, flash-2, flash-3, ... flash-9.
        # 2023.05.25 - aensminger - Change capture group 5 from \S+ 
        # to [^#\s]+, in order to account for "#" in the capture group.
        # "#" flag means 'bootable file system' on some Cisco devices.
        fs_index = 0
        for line in raw_output.splitlines():
            match = re.search(
                r'(?:\*)?(?:\s+)?(\-|\d+)(?:\s+)?(\-|\d+)(?:\s+)?(\w+)'
                r'(?:\s+)?(\w+)(?:\s+)?([^#\s]+)(.*)', line
            )
            if match and match.group(2) != "-":
                if (self.system_fs in match.group(5) or
                    self.current_system_image_fs in match.group(5)):
                    fs_index += 1
                    # Save the match to the dictionary.
                    self.system_fs_info[fs_index] = {
                        "fs": match.group(5).replace(":",""),
                        "free": match.group(2)
                    }


    def get_file_size_info(self, fs, name, path='/'):
        """Gets file size for file 'name' in file system 'fs'.

        Args:
            - fs: The file system.
            - name: The file name to find.
            - path: (Optional) Directory path. Default is "/"

        Returns:
            - tuple: (filename, size)
                - filename (str): Filename. None if not found
                - size (int): size in bytes.
        """
        # What regex are we going to use?
        if self.os == "NX-OS":
            # 2023.05.31 - aensminger: Change regex to have negative lookahead
            # for slash. We don't want directories matched.
            file_rexp = r'(?:\s?)+(\d+)\s+.*(?<=\s)(\S+)(?<!/)$'
        # IOS/IOS-XE/ASA
        else:
            # 2023.05.31 - aensminger: Change regex to only capture if dir
            # flag is not present (e.g: capture -rwx, but not drwx)
            file_rexp = r'(?:\s?)+(?:\d+)\s+(?:-...)\s+(\d+).*(?<=\s)(.*)'

        if self.os == "ASA":
            # ASA doesn't allow 'dir' output to be piped
            cmd = f"dir {fs}:{path}"
        else:
            # Everything else does
            cmd = f"dir {fs}:{path} | include {name}"
        # Send it
        raw_output = self.dis.send_command(cmd)

        # Did we get a return?
        if not raw_output:
            return (None, -1) # dir returned no output to parse.

        # Split for two reasons:
        # 1. ASA does not allow 'dir' to be piped. We get everything.
        # 2. Everything else may have more than one match returned
        #    (e.g: filename contains self.name)
        raw_output = raw_output.splitlines()
        # Now go through and find the exact file
        for line in raw_output:
            match = re.search(file_rexp, line)
            if match and (len(match.groups()) == 2 and
                               match.group(2) == name):
                # File found. Return the info.
                return (match.group(2), int(match.group(1)))
        # File was not found
        return (None, -1)


    def get_active_interfaces(self):
        """Get all interfaces that are up/up and have an IP address."""
        # TODO: Refactor this to use "Interface" broker instead.
        cmd = "show "
        if self.os == "ASA":
            cmd = cmd + "int ip br | ex ^Interface|Internal"
        elif self.os == "NX-OS":
            cmd = cmd + "ip int br | ex \"(^$|Interface|down)\""
        else:  # self.os_type == "IOS" or self.os_type == "IOS-XE"
            cmd = cmd + "ip int br | ex (Proto|unassig|down|Any|NVI)"

        raw_output = self.dis.send_command(cmd)

        # Regex the CLI output to get the interface list.
        self.active_intfs = re.findall(r'^([^\s]+)', raw_output,
                                       re.MULTILINE)


    def get_relay_interfaces(self):
        """Finds interfaces with DHCP relays configured, and stores them
        to a dictionary.
        
        Sets: Class attributes
            - relay_intfs (dict): Nested dictionary, with keys:
                - id (int): The key ID for this dictionary item.
                    - name (str): Interface name (e.g: Vlan11)
                    - relays (list): List of configured relays on this interface.
        
        Structure is: 
            {
                0: {
                    'name': '<interface name>',
                    'relays': ['<relay 1>', '<relay 2>', ...]
                },

                <additional interface>: {
                    'name': '<add. int name>',
                    'relays': ['<add. relay 1>', '<add. relay 2>', ...]
                },
                ...
            }
        """
        if not self.active_intfs:
            raise TypeError("active_intfs is not intialized")

        for intf_id in self.active_intfs:
            # Empty list to store the configured DHCP relays
            # on this interface.
            relaylist = []

            # Get the configuration for the interface
            cmd = f"show running-config interface {intf_id}"
            raw_output = self.dis.send_command(cmd)

            if self.os == "ASA":
                helper_re = r'dhcprelay\s+server\s+(\S+)'
            elif self.os == "NX-OS":
                helper_re = r'ip\s+dhcp\s+relay\s+address\s+(\S+)'
            elif self.os == "IOS" or self.os == "IOS-XE":
                helper_re = r'ip\s+helper-address\s+(\S+)'
            else:
                raise ValueError("Unknown OS type")

            for line in raw_output.splitlines():
                # Regex the relay out
                match = re.search(helper_re, line)
                if match:
                    # Found a relay, so put it in the list.
                    relaylist.append(match.group(1))

            # If there were relays, capture the interface
            # and the list of relays.
            if len(relaylist) > 0:
                ri_key = len(self.relay_intfs)
                self.relay_intfs[ri_key] = {
                    'name': intf_id,
                    'relays': relaylist
                }


    def enter_global_config(self):
        """Enter global configuration mode on the Cisco device."""
        self.dis.send_command("enable")
        self.dis.send_command("configure terminal")
        self.in_config_mode = True


    def exit_global_config(self, commit_config):
        """Exit global configuration.
        
        Args:
            commit_config (bool): Commit running config to nvram.
        """
        self.dis.send_command("end")
        self.in_config_mode = False
        if commit_config is True:
            if self.os == "ASA":
                self.dis.send_command("write memory")
            else:
                # Send 3x carriage returns.
                # This is because some IOS give additional confirmation prompts
                # (e.g: overwriting a nvram config from a different version)
                self.dis.send_command(
                    "copy running-config startup-config\r\r\r"
                )
