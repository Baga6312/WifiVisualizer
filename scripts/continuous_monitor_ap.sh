#!/bin/bash

INTERFACE="wlan0"
OUTPUT_PREFIX="live_aps"

sudo airmon-ng check kill
sudo airmon-ng start $INTERFACE

MON_INTERFACE=$(iwconfig 2>&1 | grep -i "mode:monitor" | awk '{print $1}')

if [ -z "$MON_INTERFACE" ]; then
    echo "[!] No monitor interface found!"
    exit 1
fi

echo "[+] Starting capture on $MON_INTERFACE"
echo "[+] AP-only CSV will be saved to: ${OUTPUT_PREFIX}_aps_only.csv"

# Run airodump in background
sudo airodump-ng -w $OUTPUT_PREFIX --output-format csv $MON_INTERFACE &
AIRODUMP_PID=$!

# Continuously clean the CSV to remove client data
while kill -0 $AIRODUMP_PID 2>/dev/null; do
    sleep 3
    if [ -f "${OUTPUT_PREFIX}-01.csv" ]; then
        # Create AP-only version by removing everything from "Station MAC" onwards
        sed '/Station MAC/Q' "${OUTPUT_PREFIX}-01.csv" > "${OUTPUT_PREFIX}_aps_only.csv"
    fi
done

# Cleanup on exit
trap "kill $AIRODUMP_PID 2>/dev/null; sed '/Station MAC/Q' ${OUTPUT_PREFIX}-01.csv > ${OUTPUT_PREFIX}_aps_only.csv; exit" SIGINT SIGTERM

wait
