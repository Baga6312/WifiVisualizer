# continuous_monitor.sh
#!/bin/bash

INTERFACE="wlan1"
OUTPUT_PREFIX="live_clients"

# Set monitor mode
airmon-ng start "wlan1mon"  
# Run airodump-ng continuously
airodump-ng -w $OUTPUT_PREFIX --output-format csv "wlan1mon"
