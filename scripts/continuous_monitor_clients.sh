#!/bin/bash

AP_LIST_FILE="live_aps_aps_only.csv"
OUTPUT_DIR="ap_clients"
INTERFACE="wlan0"
UPDATE_INTERVAL=5  # Update CSV files every 5 seconds

# Create output directory
mkdir -p $OUTPUT_DIR

# Check if AP list exists
if [ ! -f "$AP_LIST_FILE" ]; then
    echo "[!] AP list file not found: $AP_LIST_FILE"
    echo "[!] Run the AP discovery script first!"
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
echo ""

# Parse APs from CSV
BSSID_LIST=$(awk -F',' 'NR>2 && $1 ~ /^[0-9A-Fa-f:]+$/ {gsub(/^[ \t]+|[ \t]+$/, "", $1); print $1}' "$AP_LIST_FILE")

if [ -z "$BSSID_LIST" ]; then
    echo "[!] No APs found in CSV!"
    exit 1
fi

AP_COUNT=$(echo "$BSSID_LIST" | wc -l)
echo "[+] Found $AP_COUNT APs to monitor"
echo "[+] Starting CONTINUOUS monitoring..."
echo "[+] CSV files will update every $UPDATE_INTERVAL seconds"
echo "[+] Press Ctrl+C to stop"
echo ""

# Start monitoring each AP in background
declare -a PIDS
declare -a TEMP_FILES

for BSSID in $BSSID_LIST; do
    ESSID=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $14); print $14}' "$AP_LIST_FILE")
    CLEAN_ESSID=$(echo "$ESSID" | tr -d '/' | tr ' ' '_')
    
    if [ -z "$CLEAN_ESSID" ]; then
        CLEAN_ESSID="hidden"
    fi
    
    TEMP_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_temp"
    TEMP_FILES+=("$TEMP_FILE")
    
    echo "[*] Monitoring: $BSSID ($ESSID)"
    
    # Start airodump for this AP in background (continuous)
    sudo airodump-ng --bssid $BSSID -w "$TEMP_FILE" --output-format csv $MON_INTERFACE > /dev/null 2>&1 &
    PIDS+=($!)
done

echo ""
echo "[✓] All monitors started!"
echo ""

# Continuous update loop
ITERATION=0
while true; do
    sleep $UPDATE_INTERVAL
    
    ((ITERATION++))
    echo "[$(date '+%H:%M:%S')] Update #$ITERATION - Extracting client data..."
    
    # Extract client data from each capture
    for BSSID in $BSSID_LIST; do
        ESSID=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $14); print $14}' "$AP_LIST_FILE")
        CLEAN_ESSID=$(echo "$ESSID" | tr -d '/' | tr ' ' '_')
        
        if [ -z "$CLEAN_ESSID" ]; then
            CLEAN_ESSID="hidden"
        fi
        
        TEMP_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_temp"
        OUTPUT_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_clients.csv"
        
        if [ -f "${TEMP_FILE}-01.csv" ]; then
            # Extract ONLY the client section
            sed -n '/Station MAC/,$p' "${TEMP_FILE}-01.csv" > "$OUTPUT_FILE"
            
            # Count clients
            CLIENT_COUNT=$(awk -F',' 'NR>1 && $1 ~ /^[0-9A-Fa-f:]+$/ {print $1}' "$OUTPUT_FILE" | wc -l)
            
            if [ $CLIENT_COUNT -gt 0 ]; then
                echo "  → $BSSID: $CLIENT_COUNT client(s)"
            fi
        fi
    done
    
    echo ""
done

# Cleanup handler (runs when Ctrl+C is pressed)
cleanup() {
    echo ""
    echo "[*] Stopping all monitors..."
    
    for PID in "${PIDS[@]}"; do
        sudo kill $PID 2>/dev/null
    done
    
    echo "[*] Final client data extraction..."
    
    # Final extraction
    for BSSID in $BSSID_LIST; do
        ESSID=$(awk -F',' -v bssid="$BSSID" '$1 ~ bssid {gsub(/^[ \t]+|[ \t]+$/, "", $14); print $14}' "$AP_LIST_FILE")
        CLEAN_ESSID=$(echo "$ESSID" | tr -d '/' | tr ' ' '_')
        
        if [ -z "$CLEAN_ESSID" ]; then
            CLEAN_ESSID="hidden"
        fi
        
        TEMP_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_temp"
        OUTPUT_FILE="${OUTPUT_DIR}/${BSSID}_${CLEAN_ESSID}_clients.csv"
        
        if [ -f "${TEMP_FILE}-01.csv" ]; then
            sed -n '/Station MAC/,$p' "${TEMP_FILE}-01.csv" > "$OUTPUT_FILE"
            
            # Clean up temp files
            rm "${TEMP_FILE}-01.csv" 2>/dev/null
            rm "${TEMP_FILE}-01.kismet.csv" 2>/dev/null
            rm "${TEMP_FILE}-01.kismet.netxml" 2>/dev/null
        fi
    done
    
    echo ""
    echo "[✓] Monitoring stopped!"
    echo "[+] Final client CSVs saved in: $OUTPUT_DIR/"
    exit 0
}

trap cleanup SIGINT SIGTERM
