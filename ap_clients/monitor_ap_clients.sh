#!/bin/bash

# Set interface and input file
INTERFACE="wlan1"
INPUT_CSV="../ap/bssid.txt"
OUTPUT_DIR="ap_clients"
declare -a PIDS

# Cleanup function
cleanup() {
    echo -e "\nStopping all monitoring sessions..."
    # Kill all background processes
    kill ${PIDS[@]} 2>/dev/null
    # Rename output files
    for BSSID in $AP_BSSIDS; do
        SANITIZED=${BSSID//:/_}
        mv "$OUTPUT_DIR/clients_${SANITIZED}-01.csv" "$OUTPUT_DIR/clients_${SANITIZED}.csv" 2>/dev/null
    done
    # Combine all client CSVs
    echo "Combining results to $OUTPUT_DIR/all_clients.csv"
    awk 'FNR==1 && NR!=1 {next} {print}' "$OUTPUT_DIR"/clients_*.csv > "$OUTPUT_DIR/all_clients.csv"
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Put interface in monitor mode
sudo ip link set $INTERFACE down
sudo iw $INTERFACE set monitor control
sudo ip link set $INTERFACE up

# Extract AP BSSIDs from CSV

mapfile -t AP_BSSIDS< <(grep -v '^#\|^$' "$INPUT_CSV")

# Start monitoring for each AP in background
for BSSID in ${AP_BSSIDS[@]}  ; do
    echo "Starting background monitoring for AP: $BSSID"
    SANITIZED=${BSSID//:/_} 
    
    # Start airodump-ng in background
    timeout 5s sudo airodump-ng \
        --bssid "$BSSID" \
        --output-format csv \
        --write "$OUTPUT_DIR/clients_${SANITIZED}" \
        $INTERFACE >/dev/null 2>&1 &
    
    # Store PID
    PIDS+=($!)
done

echo "All monitoring sessions running in background. Press Ctrl+C to stop..."
wait
