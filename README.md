# relayenforce.py

This script will remove unauthorized/invalid DHCP relay helpers that are
configured on Cisco devices and then replace them using a delimeted
key value list defined in NetMRI.

The script assumes that the relays are configured on a per-interface basis
and that the relay is in the global VRF. It additionally will only run on
IOS, IOS-XE, NX-OS, and ASA/ASAv devices.

Sandbox must have CiscoConfParse module installed.
