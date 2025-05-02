#!/bin/bash

# Make sure we're running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Make the monitoring script executable
chmod +x continuous_monitor.sh
chmod +x app.py

# Create directory structure
INSTALL_DIR="/home/selmi/WifiVisualizer"
echo "Creating directory structure in $INSTALL_DIR"
mkdir -p $INSTALL_DIR
mkdir -p $INSTALL_DIR/templates
mkdir -p $INSTALL_DIR/logs

# Copy files to installation directory
echo "Copying files to installation directory..."
cp app.py $INSTALL_DIR/
cp continuous_monitor.sh $INSTALL_DIR/
cp README.md $INSTALL_DIR/
cp templates/index.html $INSTALL_DIR/templates/
cp check-wifi-services.sh $INSTALL_DIR/

# Make check script executable
chmod +x $INSTALL_DIR/check-wifi-services.sh

# Create empty CSV file to avoid initial errors
touch $INSTALL_DIR/live_clients-01.csv
# Write minimal header to make parse_aps() happy
echo "BSSID, First time seen, Last time seen, Channel, Speed, Privacy, Cipher, Authentication, Power, # beacons, # IV, LAN IP, ID-length, ESSID, Key" > $INSTALL_DIR/live_clients-01.csv

# Install required packages
echo "Installing required packages..."
apt-get update
apt-get install -y python3-flask python3-numpy aircrack-ng python3-selmip

# Install Python dependencies
selmip3 install numpy flask

# Create log files
echo "Creating log files..."
touch /var/log/wifi-monitor.log
touch /var/log/wifi-monitor-error.log
touch /var/log/wifi-visualizer.log
touch /var/log/wifi-visualizer-error.log
touch /var/log/wifi-services-status.log

# Set proper permissions
chown selmi:selmi /var/log/wifi-visualizer.log
chown selmi:selmi /var/log/wifi-visualizer-error.log
chmod 644 /var/log/wifi-*.log

# Copy service files to systemd directory
echo "Setting up systemd services..."
cp wifi-monitor.service /etc/systemd/system/
cp wifi-visualizer.service /etc/systemd/system/

# Setup cron job to check service status hourly
echo "Setting up monitoring cron job..."
(crontab -l 2>/dev/null; echo "0 * * * * /home/selmi/WifiVisualizer/check-wifi-services.sh > /dev/null 2>&1") | crontab -

# Reload systemd, enable and start services
systemctl daemon-reload
systemctl enable wifi-monitor.service
systemctl enable wifi-visualizer.service

echo "Installation complete!"
echo "Starting services..."
systemctl start wifi-monitor.service
sleep 10  # Wait for monitor service to fully initialize
systemctl start wifi-visualizer.service

echo "Running initial status check..."
/home/selmi/WifiVisualizer/check-wifi-services.sh

echo "You may need to reboot your Raspberry Pi."
echo "After rebooting, the WiFi Visualizer will be available at http://raspberry_selmi_ip:5000"
echo "Check service status anytime with: /home/selmi/WifiVisualizer/check-wifi-services.sh"
echo "View logs with: tail -f /var/log/wifi-monitor.log or tail -f /var/log/wifi-visualizer.log"
