

This should probably be a fork of:
 
https://github.com/suptronics/x120x
since x120x.py is a modification of merged-trixie.py
from that repository. I would have included a licence
with these files if I could find one. I must say I'm very pleased
with the hardware.


It has several modifications. Some are more widely applicable
but I doubt if people want my email mods:


* Don't shutdown if AC power is on, because restart will never occur
* loss of AC power removed as a fault condition.
* Queue messages if AC state changes , email when possible (I have
  a fallback wifi access point on a UPS so loss should be transient)
* Cut down frequency of regular updates to not swamp logs
* Remove upper bound in get_battery_status since it generated
  unknown for achievable voltages.
* Shutdown at 10% with a last minute check AC power is not available
* Improved commentary and progress messages
* Improved output on exceptions

This makes the system behave much more like the cyberpower ones 
I have which I handle with NUT.

I run the service as a system user, embed, which is in groups
gpio and i2c so I can avoid running as root. 


setup-virt 		generate virtual environment with smbus and gpio libraries
x120x.py		The driver
x120x.service   	Service file for the driver. Cleans up the PID file on exit 
disable_charging.sh	Manually disable charging
enable_charging.sh 	Manually enable charging

I'm assumming its better to only enable charging when attended.








