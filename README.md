# relayenforce.py

This script will remove unauthorized/invalid DHCP relay helpers that are
configured on Cisco devices and then replace them using a delimeted
key value list defined in NetMRI.

The script assumes that the relays are configured on a per-interface basis
and that the relay is in the global VRF. It additionally will only run on
IOS, IOS-XE, NX-OS, and ASA/ASAv devices.

## Prerequisites:
1. NetMRI version 7.5+
2. NetMRI Sandbox version 7.5+
3. CiscoDevice.py imported in to NetMRI
4. List in NetMRI with name that matches `RELAY_LIST_NAME`.
5. List must have the following columns: `Key`, `Relays`, `Exclusions`
   - The `Key` column contains the key for which row you want to use.
   - The `Relays` column must contain the IP addresses of the relays. Seperate multiple entries with commas.
   - The `Exclusions` column is for relay addresses that you want to remain on the interface (e.g: Cisco ISE). Seperate multiple entries with commas.

### Example List (importable)
```
# Name: DHCP Relays
# Description: List of DHCP relays and exclusions. Used by the Cisco Change DHCP Helper Addresses script.
"Key","Relays","Exclusions"
"Site-001","10.1.240.1,10.1.240.2","10.100.1.1,10.200.1.1"
"Site-002","10.2.240.1,10.2.240.2","10.100.1.1,10.200.1.1"
```
