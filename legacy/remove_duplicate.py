#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import shutil
import os

FILE_PATH = 'SB82605_jolly_cat.xml'
BACKUP_PATH = FILE_PATH + '.bak'

# Namespace map (as seen in the file: xmlns="http://www.ivoa.net/xml/VOTable/v1.3")
NS = {'vot': 'http://www.ivoa.net/xml/VOTable/v1.3'}

def remove_duplicates():
    if not os.path.exists(FILE_PATH):
        print(f"Error: File {FILE_PATH} not found.")
        return

    # Create backup
    try:
        shutil.copy2(FILE_PATH, BACKUP_PATH)
        print(f"Backup created at {BACKUP_PATH}")
    except IOError as e:
        print(f"Error creating backup: {e}")
        return

    # Register namespace to prevent ns0: prefixes in output
    ET.register_namespace('', NS['vot'])

    try:
        tree = ET.parse(FILE_PATH)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        return

    # Find TABLEDATA
    # The structure is usually RESOURCE -> TABLE -> DATA -> TABLEDATA
    table_data = root.find('.//vot:TABLEDATA', NS)
    if table_data is None:
        print("Error: TABLEDATA element not found in the XML.")
        return

    seen_names = set()
    rows_to_remove = []
    
    # Iterate through TR elements
    # Since we are modifying the list (removing items), we should collect them first
    # or be careful. ET iterators over children are robust if we don't modify structure
    # during simple iteration, but deleting while iterating can be tricky.
    # Safe approach: Collect to remove, then remove.
    
    all_rows = table_data.findall('vot:TR', NS)
    print(f"Total rows found: {len(all_rows)}")

    for tr in all_rows:
        tds = tr.findall('vot:TD', NS)
        if not tds:
            continue
        
        # Determine the Name column. Based on file inspection, it is the first TD.
        # <FIELD ID="name" ...> is the first FIELD.
        # <TD>SoFiA J...</TD> is the first TD.
        
        name_td = tds[0]
        name = name_td.text
        
        if name and name.strip():
            name = name.strip()
            if name in seen_names:
                rows_to_remove.append(tr)
            else:
                seen_names.add(name)
        else:
            # Handle empty name? Assuming valid data has name.
            pass

    duplicate_count = len(rows_to_remove)
    print(f"Found {duplicate_count} duplicate rows.")

    if duplicate_count > 0:
        for tr in rows_to_remove:
            table_data.remove(tr)
        
        print(f"Removed {duplicate_count} rows.")
        
        # Write back to file
        try:
            tree.write(FILE_PATH, encoding='utf-8', xml_declaration=True)
            print(f"Successfully updated {FILE_PATH}")
            print(f"Unique entries remaining: {len(seen_names)}")
        except IOError as e:
            print(f"Error writing to file: {e}")
    else:
        print("No duplicates found. File not modified.")

if __name__ == '__main__':
    remove_duplicates()
