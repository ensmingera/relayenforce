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
#
# DESCRIPTION:
#   This script will remove unauthorized/invalid DHCP relay helpers that are
#   configured on Cisco devices and then replace them using a delimeted
#   key value list defined in NetMRI.
#
#   The script assumes that the relays are configured on a per-interface basis
#   and that the relay is in the global VRF. It additionally will only run on
#   IOS, IOS-XE, NX-OS, and ASA/ASAv devices.
#
# PREQUISITES:
#   Sandbox must have CiscoConfParse module installed.
from infoblox_netmri.easy import NetMRIEasy
from ciscoconfparse import CiscoConfParse
import re

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

# Change the below global variables to match the list name, key name, and key
# value column name that is used in your NetMRI environment.
RELAY_LIST_NAME = "DHCP Relays"
RELAY_LIST_KEY = "Key"
RELAY_LIST_KEYVAL = "Hosts"


easyparams = {
    "api_url": api_url,
    "http_username": http_username,
    "http_password": http_password,
    "job_id": job_id,
    "device_id": device_id,
    "batch_id": batch_id
}

# BEGIN-SCRIPT-BLOCK
#
#   Script-Filter:
#       $Vendor eq "Cisco"
#       and $sysDescr like /IOS|NX-OS|Adaptive Security Appliance/
#
#   Script-Timeout: 1200
#
#   Script-Login:
#       true
#
#   Script-Variables:
#       $relay_list_key string "Row ID Key from DHCP Relay List"
#       $dry_run boolean
#
# END-SCRIPT-BLOCK

#------------------------------------------------------------------------------


class TargetDevice:
    def __init__(self, easy_class, device_class):
        self.dis = easy_class               # NetMRI Easy instance
        self.device = device_class          # Device instance
        self.name = device_class.DeviceName # Target name
        self.os_type = None                 # Target OS type
        self.active_intfs = []              # Active interfaces on device
        self.relay_intfs = {}               # Configured relays (per interface)

        # Figure out what OS type the device is.
        # This will determine what CLI syntax to use.
        if re.search(r'Adaptive Security', self.device.DeviceSysDescr):
            self.os_type = "ASA"
        elif re.search(r'NX-OS', self.device.DeviceSysDescr):
            self.os_type = "NXOS"
        else:
            # CiscoConfParse defaults to IOS
            self.os_type = "IOS"

        print("[~] Target: {}".format(self.name))
        print("[~] Syntax: {}".format(self.os_type))
        print("-" * 72)

        # Get operational up/up interfaces
        print("[~] Getting active UP/UP interfaces ...")
        self.get_active_interfaces()

        # Get configured DHCP relays
        print("[~] Searching for DHCP relays on interfaces ...")
        self.process_relay_interfaces()


    def enter_global_config(self):
        """
        Enter global configuration mode on the Cisco device.
        """
        self.dis.send_command("configure terminal")


    def exit_global_config(self, commit_config):
        """
        Exit global configuration.
        """
        self.dis.send_command("end")
        if commit_config is True:
            self.dis.send_command("copy running-config startup-config\r\r")


    def get_active_interfaces(self):
        """
        Get interfaces that are up/up with an IP address assigned.
        """
        # Set up 'show' command to send to device
        # Command always starts with 'show'
        cmd = "show "
        if self.os_type == "ASA":
            cmd = cmd + "int ip br | ex ^Interface|Internal"
        elif self.os_type == "NXOS":
            cmd = cmd + "ip int br | ex \"(^$|Interface|down)\""
        else:  # self.os_type == "IOS"
            cmd = cmd + "ip int br | ex (Proto|unassign|down|Any|NVI)"

        # Send the show command
        raw_output = self.dis.send_command(cmd)

        # Regex the CLI output to get the interface list.
        self.active_intfs = re.findall(r'^([^\s]+)', raw_output, re.MULTILINE)


    def process_relay_interfaces(self):
        """
        Finds interfaces with DHCP relays configured and stores them
        in a dictionary.
        """
        if isinstance(self.active_intfs, list):
            for intf_id in self.active_intfs:
                # Get the raw 'show run' output
                cmd = "show run interface " + intf_id
                raw_output = self.dis.send_command(cmd)

                # Send the raw output to CiscoConfParse
                ccp_input = raw_output.splitlines()
                ccp_parse = CiscoConfParse(
                    ccp_input,
                    syntax=self.os_type.lower()
                )

                # Relay command differs between OS types
                if self.os_type == "ASA":
                    re_cmd_prefix = r"dhcprelay server "
                elif self.os_type == "NXOS":
                    re_cmd_prefix = r"ip dhcp relay address "
                else:  # self.os_type == "IOS"
                    re_cmd_prefix = r"ip helper-address "

                # Iterate through child objects of the interface
                for intf_cfg_sect in ccp_parse.find_objects(r'^interface'):

                    # Empty list to hold the configured DHCP relays
                    relaylist = []

                    # Loop through the interface config and find
                    # configured DHCP relays.
                    for intf_cfg_obj in intf_cfg_sect.children:

                        # Regex out the relay IP address
                        dhcp_relay_addr = re.search((r'\s+' + re_cmd_prefix + '(([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3}))'), intf_cfg_obj.text)

                        if dhcp_relay_addr is not None:
                            # Found a relay, so put it in the list.
                            relaylist.append(dhcp_relay_addr.group(1))


                    if len(relaylist) > 0:
                        # Capture the interface name the relays were detected on.
                        intf_name = re.search(r"^interface\s(.*)",
                                            intf_cfg_sect.text)

                        # Now that we have the interface name and the list of
                        # configured DHCP relays, we will store that in to the
                        # relay_intf dictionary.
                        ri_key = len(self.relay_intfs)
                        self.relay_intfs[ri_key] = \
                            {
                            'name': intf_name.group(1),
                            'relays': relaylist
                        }


def main(easy):
    print("-" * 72)
    print("DHCP Relay Change and Enforce\n"
          "Austin Ensminger - Infoblox - 2020")
    print("-" * 72)

    # Instantiate the current device (TargetDevice class)
    target = TargetDevice(easy, easy.get_device())

    # If the dictionary length is zero then no configured DHCP relays were
    # found and we can exit early. Otherwise, DHCP relays were found and
    # there is more work to do.
    if len(target.relay_intfs) == 0:
        print("\n[+] SUCCESS: No configured DHCP relays were found on {}.\n".format(
            target.name
        ))
        exit(0)

    # The real work begins.
    # Dictionary contains interfaces with relays. So let's check and fix them.
    else:
        print("-" * 72)

        # If the relay_list_key wasn't supplied by the user, then it will be
        # assigned the default value of the Script-Variable.
        if relay_list_key == "Row ID Key from DHCP Relay List":  # <- Default
            print("[!] ERROR: A list key must be supplied.")
            # Exit with error.
            exit(1)
        else:
            # Get the authorized DHCP relay list from the user supplied key.
            relay_list = target.dis.get_list_value(
                RELAY_LIST_NAME,
                RELAY_LIST_KEY,
                str(relay_list_key),
                RELAY_LIST_KEYVAL,
                'NOTFOUND'
            )

            if relay_list == "NOTFOUND":
                print("[!] Key {} does not exist in DHCP relay list!".format
                      (relay_list_key))
                exit(1)
            else:
                # Split according to delimeter in list.
                auth_relays = relay_list.split(',')

        # Go through each interface and look at the configured relays.
        # If the relay does not exist in the NetMRI list, then it will
        # be saved for de-configuring later.
        if dry_run == "off":
            target.enter_global_config()

        # Cycle through all of the interfaces that had
        # DHCP relays configured.
        for intf_id in target.relay_intfs:

            bad_relays = []

            print("\n[+] Working in interface: {}".format
                  (target.relay_intfs[intf_id]['name']))
            # Check if the relay is in the list.
            for relay in target.relay_intfs[intf_id]['relays']:
                # Relay isn't in the list, so we keep it for removal.
                if relay not in auth_relays:
                    bad_relays.append(relay)


            # First, enter the interface sub-config to begin work.
            cmd = "interface " + str(target.relay_intfs[intf_id]['name'])
            if dry_run == "on":
                print("[-] DEBUG: target.dis.send_command({})".format(cmd))
            else:
                target.dis.send_command(cmd)


            # Now we'll configure the DHCP relays from the list.
            # First, prepare the command to deconfigure the relays.
            if target.os_type == "ASA":
                relay_cmd_prefix = "dhcprelay server "
            elif target.os_type == "NXOS":
                relay_cmd_prefix = "ip dhcp relay address "
            else:
                relay_cmd_prefix = "ip helper-address "


            # If there was relays found then we'll remove them.
            if len(bad_relays) > 0:
                # Remove the "bad" relays.
                for badrelay in bad_relays:
                    print("[-] ... Removing {} from {}".format
                          (badrelay, target.relay_intfs[intf_id]['name']))
                    cmd = "no " + relay_cmd_prefix + str(badrelay)

                    if dry_run == "on":
                        print("[-] DEBUG: target.dis.send_command({})".format(cmd))
                    else:
                        target.dis.send_command(cmd)


            # Now add the "good" relays in from the list.
            print("[+] ... Adding relays from list: {}".format(RELAY_LIST_NAME))
            for goodrelay in auth_relays:
                cmd = relay_cmd_prefix + " " + str(goodrelay)
                if dry_run == "on":
                    print("[-] DEBUG: target.dis.send_command({})".format(cmd))
                else:
                    print("[-]     ... Adding {} to {}".format(goodrelay, target.relay_intfs[intf_id]['name']))
                    target.dis.send_command(cmd)


        # Exit and commit config to memory..
        if dry_run == "off":
            target.exit_global_config(True)

    # All done!
    print("\n[+] SUCCESS: Job completed for {}\n".format(target.name))
    exit(0)


if __name__ == "__main__":
    with NetMRIEasy(**easyparams) as easy:
        main(easy)
