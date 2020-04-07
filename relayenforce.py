#!/usr/bin/env python3
#
# relayenforce.py
#
# Copyright (c) 2020 Infoblox, Inc.
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


import re
from ciscoconfparse import CiscoConfParse
from infoblox_netmri.easy import NetMRIEasy

#------------------------------------------------------------------------------

# These are to just keep pylint happy.
# Comment or remove for production
api_url = "http://netmri"
http_username = "austin"
http_password = "ensminger"
job_id = 7
device_id = 31
batch_id = 8
relay_list_key = "list_row_1"

#------------------------------------------------------------------------------

# BEGIN-SCRIPT-BLOCK
#
#   Script-Filter:
#       $Vendor eq "Cisco"
#
#   Script-Login:
#       true
#
#   Script-Variables:
#       $relay_list_key string "Row ID Key from DHCP Relay List"
#
# END-SCRIPT-BLOCK

easyparams = {
    "api_url": api_url,
    "http_username": http_username,
    "http_password": http_password,
    "job_id": job_id,
    "device_id": device_id,
    "batch_id": batch_id
}

#------------------------------------------------------------------------------


class TargetDevice:
    def __init__(self, easy_class, device_class):
        self.dis = easy_class               # NetMRI Easy instance
        self.device = device_class          # Device instance
        self.name = device_class.DeviceName # Target name
        self.os_type = None                 # Target OS type
        self.relay_intf = {}                # Configured relays

        # Figure out what OS type the device is.
        # This will determine what CLI syntax to use.
        if re.search(r'ASA', self.device.DeviceSysDescr):
            self.os_type = "ASA"
        elif re.search(r'NX-OS', self.device.DeviceSysDescr):
            self.os_type = "NXOS"
        else:
            # Default is IOS
            self.os_type = "IOS"


    def enter_global_config(self):
        """
        Enter global configuration mode on the Cisco device.
        """
        self.dis.send_command("enable")
        self.dis.send_command("configure terminal")


    def exit_global_config(self, commit_config):
        """
        Exit global configuration.
        """
        self.dis.send_command("end")
        if commit_config is True:
            self.dis.send_command("copy running-config startup-config")


    def get_relay_interface_list(self):
        """
        Get interfaces that are configured with DHCP relays.
        Returns: list
        """
        # Set up 'show' command to send to device
        # Command always starts with 'show'
        cmd = "show "
        if self.os_type == "ASA":
            cmd = cmd + "dhcprelay state | in RELAY"
        elif self.os_type == "NXOS":
            pass #TODO
        else:
            cmd = cmd + "ip helper-address | in ^[a-zA-Z0-9]"

        # Send the show command
        raw_output = self.dis.send_command(cmd)

        # Regex the CLI output.
        if self.os_type == "ASA":
            pass #TODO
        elif self.os_type == "NXOS":
            pass #TODO
        else:  # os_type == "IOS"
            cfgd_interfaces = re.findall(r'(\w+\/\d+\/\d+\:\d+\.\d+|\w+\/\d+\/\
            \d+\/\d+|\w+\/\d+\/\d+\.\d+|\w+\/\d+\.\d+|\w+\/\d+\/\d+|\w+\/\
            \d+)', raw_output)

        # Return interface ID list.
        return cfgd_interfaces


    def process_relay_interfaces(self, interface):
        # Prepare show command to get interface configlet.
        cmd = "show "
        if self.os_type == "ASA":
            pass #TODO
        elif self.os_type == "NXOS":
            pass #TODO
        else:  # os_type == "IOS"
            cmd = cmd + "run interface "

        if isinstance(interface, list):
            for intf_id in interface:
                # Get the raw 'show run' output
                # show run interface {intf_id}
                raw_output = self.dis.send_command(cmd + " " + intf_id)

                # Send the raw output to ciscoconfparse
                ccp_input = raw_output.splitlines()
                ccp_parse = CiscoConfParse(ccp_input, syntax='ios')

                # Iterate through child objects of the interface
                for intf_cfg_sect in ccp_parse.find_objects(r'^interface'):

                    # Empty list to hold the configured DHCP relays
                    relaylist = []

                    # Loop through the interface config and find
                    # configured DHCP relays.
                    for intf_cfg_obj in intf_cfg_sect.children:

                        # Regex out the relay IP address
                        dhcp_relay_addr = re.search(
                            (r'ip helper-address (([0-9]{1,3})\.([0-9]{1,3})\.'
                             r'([0-9]{1,3})\.([0-9]{1,3}))'
                             ), intf_cfg_obj.text)

                        if dhcp_relay_addr is not None:
                            # Found a relay, so put it in the list.
                            relaylist.append(dhcp_relay_addr.group(1))

                    # Capture the interface name the relays were detected on.
                    intf_name = re.search(r"^interface\s(.*)",
                                          intf_cfg_sect.text)

                    # Now that we have the interface name and the list of
                    # configured DHCP relays, we will store that in to the
                    # relay_intf dictionary.
                    ri_key = len(self.relay_intf)
                    self.relay_intf[ri_key] = \
                    {
                        'name': intf_name.group(1),
                        'relays': relaylist
                    }
        else:
            return None




def main(easy):
    print("-" * 73)
    print("DHCP Relay Change and Enforce\n"
          "Austin Ensminger - Infoblox - 2020")
    print("-" * 73)

    # If the relay_list_key wasn't supplied by the user, then it will be
    # assigned the default value of the Script-Variable.
    if relay_list_key == "Row ID Key from DHCP Relay List": # <- Default
        print("ERROR: A key from the DHCP relay list must be supplied.")
        # Exit with error.
        print("EXITING...")
        exit(1)


    # Instantiate the current device (TargetDevice class)
    target = TargetDevice(easy, easy.get_device())
    print("Target: {}".format(target.name))
    print("Syntax: {}".format(target.os_type))

    # Get interface IDs that have DHCP relays configured.
    dhcp_relay_interfaces = target.get_relay_interface_list()

    # Process these interfaces. Collect the currently configured
    # DHCP relays and store them in a dictionary.
    target.process_relay_interfaces(dhcp_relay_interfaces)

    # Look up the authorized DHCP relay list by key supplied from user.
    print("Getting relay list using key: \"{}\"".format(relay_list_key))
    relay_list = target.dis.get_list_value('Authorized DHCP Relays', 'Key', 
    str(relay_list_key),
    'IP Address',
    'NOTFOUND'
    )
    print("-" * 73)

    # Split according to delimeter in list.
    auth_relays = relay_list.split(',')

    # Go through each interface and look at the configured relays.
    # If the relay does not exist in the NetMRI list, then it will
    # be saved for de-configuring later.
    target.enter_global_config()

    for intf_id in target.relay_intf:

        bad_relays = []

        print("[+] Working in interface: {}".format\
            ( target.relay_intf[intf_id]['name'] ))        
        cmd = "interface " + str(target.relay_intf[intf_id]['name'])
        target.dis.send_command(cmd)

        for relay in target.relay_intf[intf_id]['relays']:
            # Relay isn't in the list, so we keep it for removal.
            if relay not in auth_relays:
                bad_relays.append(relay)

        print("[-] The following relays are not authorized "
              "and will be removed:")
        # Pretty print the list of bad relays. 4 items per line.
        for i in range(int(len(bad_relays)/4)+1):
            print(" " * 4, end="")
            print(", ".join(bad_relays[int(i)*4:(int(i)+1)*4]) + "\n", end="")

        # First, we'll configure the DHCP relays from the list.
        for goodrelay in auth_relays:
            cmd = "ip helper-address " + str(goodrelay)
            target.dis.send_command(cmd)

        # Then, let's remove the "bad" relays.
        for badrelay in bad_relays:
            print("[-] Removing {} from {}".format\
                ( relay, target.relay_intf[intf_id]['name'] ))
            cmd = "no ip helper-address " + str(badrelay)
            target.dis.send_command(cmd)

    # Exit and commit config to memory..
    target.exit_global_config(True)

    # All done!
    exit(0)




if __name__ == "__main__":
    with NetMRIEasy(**easyparams) as easy:
        main(easy)
