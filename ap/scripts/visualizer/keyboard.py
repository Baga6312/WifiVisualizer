   
   
   
   
    def on_key_press(self, event):
        """Handle keyboard events for adjusting parameters"""
        if event.key == '+' or event.key == '=':
            # Increase position update factor
            self.position_update_factor = min(1.0, self.position_update_factor + 0.1)
            debug_print(f"Increased position update factor to {self.position_update_factor:.1f}")
        elif event.key == '-' or event.key == '_':
            # Decrease position update factor
            self.position_update_factor = max(0.1, self.position_update_factor - 0.1)
            debug_print(f"Decreased position update factor to {self.position_update_factor:.1f}")
        elif event.key == '[':
            # Decrease RSSI/beacon change threshold
            if self.use_beacons:
                self.beacon_change_threshold = max(0, self.beacon_change_threshold - 1)
                debug_print(f"Decreased beacon change threshold to {self.beacon_change_threshold}")
            else:
                self.rssi_change_threshold = max(0, self.rssi_change_threshold - 1)
                debug_print(f"Decreased RSSI change threshold to {self.rssi_change_threshold}")
        elif event.key == ']':
            # Increase RSSI/beacon change threshold
            if self.use_beacons:
                self.beacon_change_threshold = self.beacon_change_threshold + 1
                debug_print(f"Increased beacon change threshold to {self.beacon_change_threshold}")
            else:
                self.rssi_change_threshold = self.rssi_change_threshold + 1
                debug_print(f"Increased RSSI change threshold to {self.rssi_change_threshold}")
        elif event.key == 'r':
            # Reset all AP positions
            debug_print("Resetting all AP positions")
            self.ap_data.clear()
            self.ap_history.clear()
        elif event.key == 'b':
            # Toggle between RSSI and beacon-based positioning
            self.use_beacons = not self.use_beacons
            debug_print(f"{'Enabled' if self.use_beacons else 'Disabled'} beacon-based positioning")
        elif event.key == 'c':
            # Toggle channel-based adjustments
            self.use_channels = not self.use_channels
            debug_print(f"{'Enabled' if self.use_channels else 'Disabled'} channel-based adjustments")