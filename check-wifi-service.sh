#!/bin/bash

# Log file
LOG_FILE="/var/log/wifi-services-status.log"

# Create log directory if it doesn't exist
touch $LOG_FILE
chmod 644 $LOG_FILE

# Get current timestamp
TIMESTAMP=$(date "+%Y-%m-%d %H:%M:%S")

echo "========== $TIMESTAMP ==========" >> $LOG_FILE

# Check wifi-monitor service
MONITOR_STATUS=$(systemctl is-active wifi-monitor.service)
MONITOR_ENABLED=$(systemctl is-enabled wifi-monitor.service)
echo "WiFi Monitor Service:" >> $LOG_FILE
echo "  - Status: $MONITOR_STATUS" >> $LOG_FILE
echo "  - Enabled: $MONITOR_ENABLED" >> $LOG_FILE

if [ "$MONITOR_STATUS" = "active" ]; then
    echo "  - Running since: $(systemctl show -p ActiveEnterTimestamp --value wifi-monitor.service)" >> $LOG_FILE
    echo "  - Last log entries:" >> $LOG_FILE
    tail -n 5 /var/log/wifi-monitor.log | sed 's/^/    /' >> $LOG_FILE
else
    echo "  - WARNING: Service not running" >> $LOG_FILE
    echo "  - Last error messages:" >> $LOG_FILE
    tail -n 5 /var/log/wifi-monitor-error.log | sed 's/^/    /' >> $LOG_FILE
fi

# Check wifi-visualizer service
VISUALIZER_STATUS=$(systemctl is-active wifi-visualizer.service)
VISUALIZER_ENABLED=$(systemctl is-enabled wifi-visualizer.service)
echo "WiFi Visualizer Service:" >> $LOG_FILE
echo "  - Status: $VISUALIZER_STATUS" >> $LOG_FILE
echo "  - Enabled: $VISUALIZER_ENABLED" >> $LOG_FILE

if [ "$VISUALIZER_STATUS" = "active" ]; then
    echo "  - Running since: $(systemctl show -p ActiveEnterTimestamp --value wifi-visualizer.service)" >> $LOG_FILE
    echo "  - Last log entries:" >> $LOG_FILE
    tail -n 5 /var/log/wifi-visualizer.log | sed 's/^/    /' >> $LOG_FILE
else
    echo "  - WARNING: Service not running" >> $LOG_FILE
    echo "  - Last error messages:" >> $LOG_FILE
    tail -n 5 /var/log/wifi-visualizer-error.log | sed 's/^/    /' >> $LOG_FILE
fi

# Check sequence verification
if [ "$MONITOR_STATUS" = "active" ] && [ "$VISUALIZER_STATUS" = "active" ]; then
    MONITOR_START=$(systemctl show -p ActiveEnterTimestampMonotonic --value wifi-monitor.service)
    VISUALIZER_START=$(systemctl show -p ActiveEnterTimestampMonotonic --value wifi-visualizer.service)
    
    if [ $MONITOR_START -lt $VISUALIZER_START ]; then
        echo "✓ CORRECT SEQUENCE: wifi-monitor started before wifi-visualizer" >> $LOG_FILE
    else
        echo "❌ INCORRECT SEQUENCE: wifi-visualizer may have started before wifi-monitor" >> $LOG_FILE
    fi
fi

echo "" >> $LOG_FILE

# Print to console
cat $LOG_FILE | tail -n 20

exit 0
