


def parse_aps(filename):
    """Parse AP information from CSV file with improved format handling"""
    aps = []
    try:
        with open(filename, 'r') as f:
            # Print first few lines of file for debugging
            if DEBUG:
                debug_print(f"Opening file: {filename}")
                f.seek(0)  # Go to start of file
                content = f.read(1000)  # Read first 1000 chars for debug view
                debug_print(f"File preview:\n{content[:500]}...")
                f.seek(0)  # Reset to beginning
            
            # Read the file content
            content = f.read()
            
            # Try to identify if this is a standard CSV or airodump-ng output
            if "Station MAC" in content:
                debug_print("Detected airodump-ng output format")
                # Split into AP section and station section
                parts = content.split("Station MAC")
                ap_section = parts[0].strip()
                
                # Process AP section line by line
                lines = ap_section.split('\n')
                header_line = None
                
                for i, line in enumerate(lines):
                    if "BSSID" in line and "First time seen" in line:
                        header_line = i
                        debug_print(f"Found header line at index {i}: {line}")
                        break
                
                if header_line is not None:
                    # Process each AP line after the header
                    for line in lines[header_line + 1:]:
                        line = line.strip()
                        if not line:  # Skip empty lines
                            continue
                            
                        # Split the line by commas and clean up fields
                        fields = [field.strip() for field in line.split(',')]
                        
                        if len(fields) >= 9:  # Need at least BSSID, Power and ESSID fields
                            try:
                                bssid = fields[0].strip()
                                
                                # Extract channel (typically field 3, index 2)
                                channel_str = fields[3].strip() if len(fields) > 3 else "0"
                                try:
                                    channel = int(channel_str) if channel_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Channel to int: '{channel_str}' in line: {line}")
                                    channel = 0
                                
                                # Power is typically in field 8 (index 7)
                                power_str = fields[8].strip()
                                
                                # Handle potential errors in integer conversion
                                try:
                                    rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Power to int: '{power_str}' in line: {line}")
                                    rssi = -100  # Default poor signal if can't parse
                                
                                # Extract beacon count (typically field 9, index 8)
                                beacon_str = fields[9].strip() if len(fields) > 9 else "0"
                                try:
                                    beacons = int(beacon_str) if beacon_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Beacons to int: '{beacon_str}' in line: {line}")
                                    beacons = 0
                                
                                # ESSID is typically in field 13 (index 12)
                                essid = fields[13].strip() if len(fields) > 13 else ""
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid, beacons, channel))
                                    debug_print(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                            except Exception as e:
                                debug_print(f"Error processing line: {e}")
                                debug_print(f"Line data: {line}")
                else:
                    debug_print("Could not find header line with BSSID and First time seen")
            else:
                # Try standard CSV parsing
                debug_print("Attempting standard CSV parsing")
                f.seek(0)  # Reset to beginning
                reader = csv.reader(f)
                header = None
                
                for row in reader:
                    if not row or not any(row):  # Skip empty rows
                        continue
                        
                    # Try to identify header row
                    if not header and any(cell and "BSSID" in cell for cell in row):
                        header = row
                        debug_print(f"Found header: {header}")
                        continue
                    
                    # Process data rows
                    if header:
                        try:
                            # Find column indices
                            bssid_idx = next((i for i, cell in enumerate(header) if cell and "BSSID" in cell), 0)
                            power_idx = next((i for i, cell in enumerate(header) if cell and "Power" in cell), 8)
                            beacons_idx = next((i for i, cell in enumerate(header) if cell and "beacons" in cell), 9)
                            essid_idx = next((i for i, cell in enumerate(header) if cell and "ESSID" in cell), 13)
                            channel_idx = next((i for i, cell in enumerate(header) if cell and "channel" in cell), 3)
                            
                            # Get values
                            if len(row) > max(bssid_idx, power_idx, essid_idx):
                                bssid = row[bssid_idx].strip()
                                power_str = row[power_idx].strip()
                                beacon_str = row[beacons_idx].strip() if len(row) > beacons_idx else "0"
                                essid = row[essid_idx].strip() if len(row) > essid_idx else ""
                                channel_str = row[channel_idx].strip() if len(row) > channel_idx else "0"
                                
                                try:
                                    rssi = int(power_str) if power_str.lstrip('-').isdigit() else -100
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Power to int: '{power_str}'")
                                    rssi = -100
                                
                                try:
                                    beacons = int(beacon_str) if beacon_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Beacons to int: '{beacon_str}'")
                                    beacons = 0
                                
                                try:
                                    channel = int(channel_str) if channel_str.isdigit() else 0
                                except ValueError:
                                    debug_print(f"Warning: Could not convert Channel to int: '{channel_str}'")
                                    channel = 0
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid, beacons, channel))
                                    debug_print(f"Added AP: BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                        except Exception as e:
                            debug_print(f"Error processing row: {e}")
                            debug_print(f"Row data: {row}")
                    else:
                        debug_print("Processing without identified header")
                        # If we can't find a header, try simple format
                        if len(row) >= 3:
                            try:
                                bssid = row[0].strip()
                                # Try to find channel
                                channel = 0
                                if len(row) > 3:
                                    try:
                                        channel = int(row[3].strip())
                                    except ValueError:
                                        channel = 0
                                
                                # Try to find RSSI/Power field
                                power_found = False
                                for i, cell in enumerate(row):
                                    if cell.strip().startswith('-') and cell.strip().lstrip('-').isdigit():
                                        rssi = int(cell.strip())
                                        power_found = True
                                        break
                                        
                                if not power_found and len(row) > 8:
                                    # Try standard position
                                    try:
                                        rssi = int(row[8].strip())
                                    except ValueError:
                                        rssi = -100
                                elif not power_found:
                                    rssi = -100
                                
                                # Try to find beacons
                                beacons = 0
                                if len(row) > 9:
                                    try:
                                        beacons = int(row[9].strip())
                                    except ValueError:
                                        beacons = 0
                                
                                # Try to find ESSID
                                essid = ""
                                for i, cell in enumerate(row):
                                    if i > 0 and cell.strip() and not cell.strip().startswith('-') and not cell.strip()[0].isdigit():
                                        essid = cell.strip()
                                        break
                                
                                if not essid and len(row) > 13:
                                    essid = row[13].strip()
                                
                                if bssid and bssid != "BSSID":  # Skip if BSSID is empty or header
                                    aps.append((bssid, rssi, essid, beacons, channel))
                                    debug_print(f"Added AP (simple format): BSSID={bssid}, RSSI={rssi}, ESSID={essid}, Beacons={beacons}, Channel={channel}")
                            except Exception as e:
                                debug_print(f"Error processing simple format: {e}")
    
    except Exception as e:
        debug_print(f"Error reading file: {e}")
    
    # Remove any duplicate BSSIDs (keep the one with strongest signal)
    unique_aps = {}
    for bssid, rssi, essid, beacons, channel in aps:
        if bssid not in unique_aps or rssi > unique_aps[bssid][0]:
            unique_aps[bssid] = (rssi, essid, beacons, channel)
    
    result = [(bssid, rssi, essid, beacons, channel) for bssid, (rssi, essid, beacons, channel) in unique_aps.items()]
    debug_print(f"Returned {len(result)} unique APs")
    
    return result