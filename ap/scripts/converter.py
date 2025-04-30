


def rssi_to_distance(rssi, measured_power=-30, path_loss_exponent=3.0):
    """
    Convert RSSI to estimated distance in meters
    Using improved path loss exponent based on WiFi characteristics
    """
    # Prevent division by zero or negative values that would break the logarithm
    if rssi >= measured_power:
        return 1.0  # Minimum distance
    
    return 10 ** ((measured_power - rssi) / (10 * path_loss_exponent))




def channel_to_frequency(channel):
    """Convert WiFi channel to frequency in GHz with more accurate mapping"""
    if channel <= 0:
        return 2.4  # Default to 2.4 GHz
    
    if 1 <= channel <= 14:
        # 2.4 GHz band
        if channel == 14:  # Special case for channel 14
            return 2.484
        else:
            return 2.407 + 0.005 * channel
    elif 32 <= channel <= 68:  # U-NII-1 and U-NII-2A bands
        return 5.16 + 0.005 * (channel - 32)
    elif 96 <= channel <= 144:  # U-NII-2C band
        return 5.49 + 0.005 * (channel - 96)
    elif 149 <= channel <= 177:  # U-NII-3 band
        return 5.735 + 0.005 * (channel - 149)
    else:
        # Unknown channel - make an educated guess based on channel number
        if 15 <= channel <= 31:
            return 2.4  # Assume 2.4 GHz
        elif channel >= 32:
            return 5.0 + (channel - 32) * 0.005  # Assume 5 GHz with standard spacing
        else:
            return 2.4  # Default

def adjust_rssi_by_channel(rssi, channel):
    """
    Adjust RSSI based on channel frequency with improved accuracy
    Higher frequencies (5GHz) attenuate more than 2.4GHz
    """
    freq = channel_to_frequency(channel)
    
    if freq >= 5.7:  # Upper 5GHz band (U-NII-3)
        # Higher 5GHz signals attenuate significantly more
        return rssi + 8
    elif freq >= 5.4:  # Mid 5GHz band (U-NII-2C)
        # Mid 5GHz signals attenuate more
        return rssi + 7
    elif freq >= 5.15:  # Lower 5GHz band (U-NII-1)
        # Lower 5GHz signals attenuate more than 2.4GHz
        return rssi + 6
    elif freq > 2.45:  # Upper 2.4GHz band (channels 10-14)
        # Upper 2.4GHz signals attenuate slightly more
        return rssi + 1
    elif freq < 2.425:  # Lower 2.4GHz band (channels 1-4)
        # Lower 2.4GHz signals attenuate slightly less
        return rssi - 1
    else:
        # Mid 2.4GHz band (channels 5-9)
        return rssi

def calculate_distance_with_channel(rssi, channel):
    """Calculate distance taking into account the channel frequency with improved accuracy"""
    adjusted_rssi = adjust_rssi_by_channel(rssi, channel)
    
    # Use different path loss exponents based on frequency and environment
    freq = channel_to_frequency(channel)
    
    if freq >= 5.7:  # Upper 5GHz band
        path_loss = 3.6  # Higher attenuation
    elif freq >= 5.15:  # Any 5GHz band
        path_loss = 3.5  # High attenuation
    elif freq > 2.45:  # Upper 2.4GHz band
        path_loss = 3.1  # Slightly higher attenuation
    elif freq < 2.425:  # Lower 2.4GHz band
        path_loss = 2.9  # Slightly lower attenuation
    else:  # Mid 2.4GHz band
        path_loss = 3.0  # Standard path loss
        
    # Calculate measured reference power based on frequency
    # Different frequencies have different reference powers at 1m distance
    if freq >= 5.15:
        measured_power = -32  # 5GHz reference
    else:
        measured_power = -30  # 2.4GHz reference
        
    return rssi_to_distance(adjusted_rssi, measured_power=measured_power, path_loss_exponent=path_loss)

def beacons_to_distance(beacon_count, max_beacons=1000, min_beacons=10):
    """Convert beacon count to distance with improved scaling"""
    if beacon_count <= 0:
        return 50  # Max distance
    
    # Normalize beacon count between min and max
    normalized_beacons = min(max_beacons, max(min_beacons, beacon_count))
    log_scale = math.log(normalized_beacons) / math.log(max_beacons)
    
    # More aggressive scaling for better distance discrimination
    return max(1, 40 * (1 - log_scale ** 0.7))

def calculate_xy_position(distance, angle=None):
    """Convert distance to X,Y coordinates with optional fixed or random angle"""
    if angle is None:
        angle = np.random.uniform(0, 2 * np.pi)  # Random angle
    return (
        distance * np.cos(angle),  # X
        distance * np.sin(angle)   # Y
    )