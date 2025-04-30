    def setup_plot(self):
        """Initialize the plot appearance"""
        self.ax.set_xlim(-30, 30)
        self.ax.set_ylim(-30, 30)
        self.ax.set_xlabel('X Distance (m)')
        self.ax.set_ylabel('Y Distance (m)')
        self.ax.set_title('WiFi Access Points Real-time Visualization')
        self.ax.grid(True)
        
        # Add range circles
        for radius in [10, 15]:
            circle = Circle((0, 0), radius, fill=False, linestyle='--', alpha=0.5)
            self.ax.add_patch(circle)
            self.ax.text(radius, 0, f"{radius}m", fontsize=10, ha='left', va='bottom')
        
        # Add legend for RSSI color codes
        rssi_levels = [
            ('Excellent (> -50 dBm)', 'green'),
            ('Good (-50 to -65 dBm)', 'blue'),
            ('Fair (-65 to -75 dBm)', 'orange'),
            ('Poor (< -75 dBm)', 'red')
        ]
        for label, color in rssi_levels:
            self.ax.plot([], [], 'o', color=color, label=label)
        self.ax.legend(loc='upper right')