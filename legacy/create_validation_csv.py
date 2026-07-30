#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import csv
import os
import sys

# Configuration
XML_FILE = 'SB82605_jolly_cat.xml'
VALIDATION_DIR = 'output_validation_true'
OUTPUT_CSV = 'validation_catalogue_SB82605_true.csv'
NS = {'vot': 'http://www.ivoa.net/xml/VOTable/v1.3'}

def create_csv():
    # Get list of target names from filenames
    if not os.path.exists(VALIDATION_DIR):
        print(f"Error: Directory {VALIDATION_DIR} not found.")
        sys.exit(1)

    target_names = set()
    files = [f for f in os.listdir(VALIDATION_DIR) if f.endswith('.png')]
    
    print(f"Found {len(files)} PNG files in {VALIDATION_DIR}")

    for f in files:
        # Expected format: SoFiA_J223158.71-332831.6.png
        # Target format: SoFiA J223158.71-332831.6
        name_part = f.rsplit('.', 1)[0] # Remove .png
        
        # Replace first underscore with space content
        # "SoFiA_J..." -> "SoFiA J..."
        if '_' in name_part:
            parts = name_part.split('_', 1)
            formatted_name = f"{parts[0]} {parts[1]}"
            target_names.add(formatted_name)
        else:
            print(f"Warning: Filename {f} does not match expected format with underscore")
            target_names.add(name_part)

    print(f"Extracted {len(target_names)} unique target names.")

    # Parse XML
    if not os.path.exists(XML_FILE):
        print(f"Error: File {XML_FILE} not found.")
        sys.exit(1)

    try:
        tree = ET.parse(XML_FILE)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        sys.exit(1)

    # Extract Field Names for Header
    fields = []
    # Find all FIELD elements under extracted TABLE
    # Structure: RESOURCE -> TABLE -> FIELD
    # We find the first TABLE
    table = root.find('.//vot:TABLE', NS)
    if table is None:
        print("Error: TABLE element not found")
        sys.exit(1)

    for field in table.findall('vot:FIELD', NS):
        fields.append(field.get('name'))
    
    if not fields:
        print("Error: No FIELDs found")
        sys.exit(1)

    print(f"Found {len(fields)} fields: {fields}")

    # Filter Data and Write to CSV
    table_data = root.find('.//vot:TABLEDATA', NS)
    if table_data is None:
        print("Error: TABLEDATA element not found")
        sys.exit(1)

    found_count = 0
    
    with open(OUTPUT_CSV, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(fields)

        for tr in table_data.findall('vot:TR', NS):
            tds = tr.findall('vot:TD', NS)
            if not tds:
                continue
            
            # Assuming first column is Name
            row_name = tds[0].text.strip()
            
            if row_name in target_names:
                row_data = [td.text for td in tds]
                writer.writerow(row_data)
                found_count += 1

    print(f"Created {OUTPUT_CSV} with {found_count} entries.")

    # Verification
    if found_count < len(target_names):
        print(f"Warning: {len(target_names) - found_count} targets from directory were NOT found in XML.")
    
if __name__ == '__main__':
    create_csv()
