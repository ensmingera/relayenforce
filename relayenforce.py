# BEGIN-INTERNAL-SCRIPT-BLOCK
# Script:
# 	Cisco Change DHCP Helper Addresses
#
# Script-Description:
# 	This script will remove unauthorized/invalid DHCP relay helpers that are 
#   configured on Cisco IOS, IOS-XE, NX-OS, or ASA devices and then replace
#   them using a delimited key value list defined in NetMRI.
# 	
# 	The script assumes that the relays are configured on a per-interface basis
#   and that the relay is in the global VRF. It additionally will only run on
#   IOS, IOS-XE, NX-OS, and ASA/ASAv devices.
#
# END-INTERNAL-SCRIPT-BLOCK
# These are to just keep Pylance happy.
# Uncomment to make your Pylance happy too.
#api_url = "http://netmri"
#http_username = "austin"
#http_password = "ensminger"
#job_id = 7
#device_id = 31
#batch_id = 8
#relay_list_key = "list_row_1"
#dry_run = "on"
#------------------------------------------------------------------------------
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
#   configured on Cisco devices and then replace them using a delimited
#   key value list defined in NetMRI.
#
#   The script assumes that the relays are configured on a per-interface basis
#   and that the relay is in the global VRF. It additionally will only run on
#   IOS, IOS-XE, NX-OS, and ASA/ASAv devices.
#
# PREQUISITES:
#   1. NetMRI version 7.5+
#   2. NetMRI Sandbox version 7.5+
#   3. CiscoDevice.py imported in to NetMRI
#   4. List in NetMRI with name that matches RELAY_LIST_NAME.
#   5. List must have the following columns: Key, Relays, Exclusions
#       a. The Key column contains the key for which row you want to use.
#       b. The Relays column must contain the IP addresses of the relays.
#          If there are multiple entries, seperate them with commas.
#       c. The Exclusions column is for relay addresses that you want to remain
#          on the interface (e.g: Cisco ISE). Seperate multiple entries with
#          commas.
#       An example CSV to import would look like:
#       # Name: DHCP Relays
#       # Description: Used by the Cisco Change DHCP Helper Addresses script
#       "Key","Relays","Exclusions"
#       "Site-001","192.168.255.67,192.168.255.68","10.100.1.1,10.200.1.1"
#
from infoblox_netmri.easy import NetMRIEasy
from CiscoDevice import CiscoDevice
#------------------------------------------------------------------------------
# BEGIN-SCRIPT-BLOCK
#
#   Script-Filter:
#       $Vendor eq "Cisco"
#       and $sysDescr like /IOS|NX-OS|Adaptive Security Appliance/
#
#   Script-Timeout: 1800
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
# Change the below global variables to match the list name, key name, and key
# value column name that is used in your NetMRI environment.
RELAY_LIST_NAME = "DHCP Relays"
RELAY_LIST_KEY = "Key"
RELAY_LIST_KEYVAL = "Relays"
RELAY_LIST_EXCLUSIONS = "Exclusions"


def main(easy):
    easy.log_message("info", "-" * 72)
    easy.log_message("info", "Cisco Change DHCP Helper Addresses")
    easy.log_message("info", "-" * 72)

    # Instantiate the current device (TargetDevice class)
    target = CiscoDevice(easy)

    easy.log_message("info", f"[~] Target: {target.hostname}")
    easy.log_message("info", f"[~] Syntax: {target.os}")
    easy.log_message("info", "-" * 72)

    easy.log_message("info", "[~] Getting active UP/UP interfaces ...")
    target.get_active_interfaces()

    # Get configured DHCP relays
    easy.log_message("info", "[~] Searching for DHCP relays on interfaces ...")
    target.get_relay_interfaces()

    # If the dictionary length is zero then no configured DHCP relays were
    # found and we can exit early. Otherwise, DHCP relays were found and
    # there is more work to do.
    if len(target.relay_intfs) == 0:
        easy.log_message("info", f"[+] SUCCESS: No DHCP relays were found on"
                         f" {target.hostname}.")
        return

    # The real work begins.
    # Dictionary contains interfaces with relays. So let's check and fix them.
    else:
        easy.log_message("info", "-" * 72)

        # If the relay_list_key wasn't supplied by the user, then it will be
        # assigned the default value of the Script-Variable.
        if relay_list_key == "Row ID Key from DHCP Relay List":  # <- Default
            easy.log_message("error",
                "[!] ERROR: A list key must be supplied."
            )
            # Exit with error.
            raise TypeError("Missing list key")
        else:
            # Get the authorized DHCP relay list from the user supplied key.
            relay_list = easy.get_list_value(
                RELAY_LIST_NAME,
                RELAY_LIST_KEY,
                str(relay_list_key),
                RELAY_LIST_KEYVAL,
                'NOTFOUND'
            )

            if relay_list == "NOTFOUND":
                easy.log_message("error",
                    f"[!] Key \"{relay_list_key}\" does not exist in "
                    f"{RELAY_LIST_NAME}."
                )
                raise TypeError("Key not found")
            else:
                # Split according to delimeter in list.
                auth_relays = relay_list.split(',')
            
            # Get any excluded relays from that same list, reuse relay_list
            relay_list = easy.get_list_value(
                RELAY_LIST_NAME,
                RELAY_LIST_KEY,
                str(relay_list_key),
                RELAY_LIST_EXCLUSIONS,
                'NOTFOUND'
            )
            if relay_list != "NOTFOUND":
                excluded_relays = relay_list.split(',')

        # Free relay_list
        relay_list = None

        # Go through each interface and look at the configured relays.
        # If the relay does not exist in the NetMRI list, then it will
        # be saved for de-configuring later.
        if dry_run == "off":
            target.enter_global_config()

        # Cycle through all of the interfaces that had
        # DHCP relays configured.
        for intf_id in target.relay_intfs:

            bad_relays = []

            easy.log_message("info", 
                "[+] Working in interface: "
                f"{target.relay_intfs[intf_id]['name']}"
            )
            # Check if the relay is in the list.
            for relay in target.relay_intfs[intf_id]['relays']:
                # Relay isn't in the list, so we keep it for removal.
                if relay not in auth_relays and relay not in excluded_relays:
                    bad_relays.append(relay)

            # First, enter the interface sub-config to begin work.
            cmd = "interface " + str(target.relay_intfs[intf_id]['name'])
            if dry_run == "on":
                easy.log_message("debug", 
                    f"[-] DEBUG: target.dis.send_command({cmd})"
                )
            else:
                target.dis.send_command(cmd)

            # Now we'll configure the DHCP relays from the list.
            # First, prepare the command to deconfigure the relays.
            if target.os == "ASA":
                relay_cmd_prefix = "dhcprelay server "
            elif target.os == "NX-OS":
                relay_cmd_prefix = "ip dhcp relay address "
            else:
                relay_cmd_prefix = "ip helper-address "

            # If there was relays found then we'll remove them.
            if len(bad_relays) > 0:
                # Remove the "bad" relays.
                for badrelay in bad_relays:
                    easy.log_message("info",
                        f"[-] ... Removing {badrelay} "
                        f"from {target.relay_intfs[intf_id]['name']}"
                    )
                    cmd = "no " + relay_cmd_prefix + str(badrelay)

                    if dry_run == "on":
                        easy.log_message("debug",
                            f"[-] DEBUG: target.dis.send_command({cmd})"
                        )
                    else:
                        target.dis.send_command(cmd)

            # Now add the "good" relays in from the list.
            for goodrelay in auth_relays:
                easy.log_message("info", 
                    f"[+] ... Adding {goodrelay} "
                    f"to {target.relay_intfs[intf_id]['name']}"
                )
                cmd = relay_cmd_prefix + str(goodrelay)
                if dry_run == "on":
                    easy.log_message("debug",
                        f"[-] DEBUG: target.dis.send_command({cmd})"
                    )
                else:
                    target.dis.send_command(cmd)

            easy.log_message("info", "-" * 72)

        # Exit and commit config to memory..
        if dry_run == "off":
            target.exit_global_config(True)

    # All done!
    easy.log_message("info",
                     f"[+] SUCCESS: Job completed for {target.hostname}")
    return


if __name__ == "__main__":

    easyparams = {
        "api_url": api_url,
        "http_username": http_username,
        "http_password": http_password,
        "job_id": job_id,
        "device_id": device_id,
        "batch_id": batch_id
    }

    with NetMRIEasy(**easyparams) as easy:
        main(easy)
