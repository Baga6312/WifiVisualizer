#!/bin/bash

AP_LIST_FILE="live_aps_aps_only.csv"
OUTPUT_DIR="ap_clients"
INTERFACE="wlan0"
UPDATE_INTERVAL=5   # Update CSV files every 5 seconds
RSSI_THRESHOLD=-70  # Only monitor APs with signal STRONGER than -70 dBm (closer APs)
MAX_PARALLEL=10     # Max number of parallel airodump processes

# Create output directory
mkdir -p $OUTPUT_DIR

# Check if AP list exists
if [ ! -f "$AP_LIST_FILE" ]; then
    echo "[!] AP list file not found: $AP_LIST_FILE"
    exit 1
fi

# Get monitor interface
MON_INTERFACE=$(iwconfig 2>&1 | grep -i "mode:monitor" | awk '{print $1}')

if [ -z "$MON_INTERFACE" ]; then
    echo "[!] No monitor interface found!"
    exit 1
fi

echo "[+] Monitor interface: $MON_INTERFACE"
echo "[+] Reading APs from: $AP_LIST_FILE"
echo "[+] Only monitoring APs with RSSI > $RSSI_THRESHOLD dBm (nearby only)"
echo "[+] Max $MAX_PARALLEL simultaneous captures"
echo ""

# Function to get nearby APs (strong signal only)
get_nearby_aps() {
    awk -F',' -v threshold="$RSSI_THRESHOLD" 'NR>2 && $1 ~ /^[0-9A-Fa-f:]+$/ {
        gsub(/^[ \t]+|[ \t]+$/, "", $1);
        gsub(/^[ \t]+|[ \t]+$/, "", $9);
        rssi = $9 + 0;
        if (rssi > threshold && rssi != 0) print rssi, $1
    }' "$AP_LIST_FILE" | sort -rn | head -n $MAX_PARALLEL | awk '{print $2}'
}

# Cleanup function
cleanup() {
    echo ""
    echo "[*] Stopping all monitors..."
    
    # Kill all airodump processes
    for PID in "${PIDS[@]}"; do
        kill $PID 2>/dev/null
    done
    
    # Clean up temp files
    rm -f "${OUTPUT_DIR}"/*_temp-01.csv 2>/dev/null
    rm -f "${OUTPUT_DIR}"/*_temp-01.kismet* 2>/dev/null
    rm -f "${OUTPUT_DIR}"/*_temp-01.cap 2>/dev/null
    
    echo "[✓] Cleanup complete!"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Get initial nearby APs and start monitoring
echo "[*] Scanning for nearby APs..."
CURRENT_APS=$(get_nearby_aps)

if [ -z "$CURRENT_APS" ]; then
    echo "[!] No nearby APs found (all weaker than $RSSI_THRESHOLD dBm)"
    echo "[!] Try adjusting RSSI_THRESHOLD in the script"
    exit 1
fi

declare -a PIDS
declare -A AP_MONITORING

# Start monitoring all nearby APs in parallel
for BSSID in $CURRENT_APS; do
    ESSID=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $14); print $14}' "$AP_LIST_FILE")
    RSSI=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $9); print $9}' "$AP_LIST_FILE")
    CLEAN_ESSID=$(echo "$ESSID" | tr -d '/' | tr ' ' '_')
    
    if [ -z "$CLEAN_ESSID" ]; then
        CLEAN_ESSID="hidden"
    fi
    
    TEMP_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_temp"
    
    echo "[+] Monitoring: $BSSID ($ESSID) @ ${RSSI}dBm"
    
    # Start airodump for this AP in background
    airodump-ng --bssid $BSSID -w "$TEMP_FILE" --output-format csv $MON_INTERFACE > /dev/null 2>&1 &
    PIDS+=($!)
    AP_MONITORING[$BSSID]=1
done

echo ""
echo "[✓] All nearby APs are being monitored in parallel!"
echo "[+] Updating client CSV files every ${UPDATE_INTERVAL}s..."
echo ""

# Continuous update loop
ITERATION=0
while true; do
    sleep $UPDATE_INTERVAL
    
    ((ITERATION++))
    echo "[$(date '+%H:%M:%S')] Update #$ITERATION"
    
    # Check for new nearby APs or APs that moved out of range
    NEW_APS=$(get_nearby_aps)
    
    # Stop monitoring APs that are now too far
    for BSSID in "${!AP_MONITORING[@]}"; do
        if ! echo "$NEW_APS" | grep -q "$BSSID"; then
            echo "  [-] AP moved out of range: $BSSID"
            # Find and kill the process for this AP
            for i in "${!PIDS[@]}"; do
                ps -p ${PIDS[$i]} | grep -q "$BSSID" && kill ${PIDS[$i]} 2>/dev/null
            done
            unset AP_MONITORING[$BSSID]
        fi
    done
    
    # Start monitoring new APs that came into range
    for BSSID in $NEW_APS; do
        if [ -z "${AP_MONITORING[$BSSID]}" ]; then
            ESSID=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $14); print $14}' "$AP_LIST_FILE")
            RSSI=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $9); print $9}' "$AP_LIST_FILE")
            CLEAN_ESSID=$(echo "$ESSID" | tr -d '/' | tr ' ' '_')
            
            if [ -z "$CLEAN_ESSID" ]; then
                CLEAN_ESSID="hidden"
            fi
            
            TEMP_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_temp"
            
            echo "  [+] New AP in range: $BSSID ($ESSID) @ ${RSSI}dBm"
            
            airodump-ng --bssid $BSSID -w "$TEMP_FILE" --output-format csv $MON_INTERFACE > /dev/null 2>&1 &
            PIDS+=($!)
            AP_MONITORING[$BSSID]=1
        fi
    done
    
    # Extract client data from all monitored APs
    TOTAL_CLIENTS=0
    for BSSID in "${!AP_MONITORING[@]}"; do
        ESSID=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $14); print $14}' "$AP_LIST_FILE")
        CLEAN_ESSID=$(echo "$ESSID" | tr -d '/' | tr ' ' '_')
        
        if [ -z "$CLEAN_ESSID" ]; then
            CLEAN_ESSID="hidden"
        fi
        
        TEMP_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_temp"
        OUTPUT_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_clients.csv"
        
        if [ -f "${TEMP_FILE}-01.csv" ]; then
            # Extract ONLY client section
            sed -n '/Station MAC/,$p' "${TEMP_FILE}-01.csv" > "$OUTPUT_FILE"
            
            # Count clients
            CLIENT_COUNT=$(awk -F',' 'NR>1 && $1 ~ /^[0-9A-Fa-f:]+$/ {print $1}' "$OUTPUT_FILE" | wc -l)
            
            if [ $CLIENT_COUNT -gt 0 ]; then
                echo "  → $BSSID: $CLIENT_COUNT client(s)"
                TOTAL_CLIENTS=$((TOTAL_CLIENTS + CLIENT_COUNT))
            fi
        fi
    done
    
    echo "  📊 Total: ${#AP_MONITORING[@]} APs, $TOTAL_CLIENTS clients"
    echo ""
done
