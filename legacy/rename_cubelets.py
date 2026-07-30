import os
import argparse
import xml.etree.ElementTree as ET
import shutil

def parse_catalogue(xml_file):
    """
    Parses the VOTable XML to extract a mapping from ID to Name.
    Assumes VOTable structure with FIELDs defining columns and TABLEDATA for rows.
    """
    tree = ET.parse(xml_file)
    root = tree.getroot()
    
    # Namespace handling
    ns = {'vo': 'http://www.ivoa.net/xml/VOTable/v1.3'}
    # Try finding Table with and without namespace if needed, but usually we can search recursively
    
    # Find the table
    table = root.find('.//TABLE') 
    if table is None:
        # Try with namespace
        table = root.find('.//vo:TABLE', ns)
        
    if table is None:
        raise ValueError("Could not find TABLE element in XML")
        
    # Get Fields to find indices of 'id' and 'name'
    fields = table.findall('FIELD') + table.findall('vo:FIELD', ns)
    
    id_idx = -1
    name_idx = -1
    
    for i, field in enumerate(fields):
        name_attr = field.get('name')
        if name_attr == 'id':
            id_idx = i
        elif name_attr == 'name':
            name_idx = i
            
    if id_idx == -1 or name_idx == -1:
        raise ValueError(f"Could not find 'id' (idx={id_idx}) or 'name' (idx={name_idx}) fields")
        
    # Parse Data
    mapping = {}
    table_data = root.find('.//TABLEDATA')
    if table_data is None:
        table_data = root.find('.//vo:TABLEDATA', ns)
        
    if table_data is None:
         raise ValueError("Could not find TABLEDATA element")
         
    for tr in table_data.findall('TR') + table_data.findall('vo:TR', ns):
        tds = tr.findall('TD') + tr.findall('vo:TD', ns)
        if len(tds) > max(id_idx, name_idx):
            src_id = tds[id_idx].text.strip()
            src_name = tds[name_idx].text.strip()
            # Replace spaces with underscores
            src_name = src_name.replace(' ', '_')
            mapping[src_id] = src_name
            
    return mapping


def process_renaming(xml_file, cubelets_dir, output_dir, dry_run=True):
    mapping = parse_catalogue(xml_file)
    print(f"Loaded {len(mapping)} entries from catalogue.")
    
    # Determine the prefix from the xml filename ?? 
    # Or strict 'G23_T0_350h_001_' 
    # The xml file is G23_T0_350h_001_cat.xml
    # The files are G23_T0_350h_001_{ID}_{Suffix}
    
    xml_basename = os.path.basename(xml_file)
    # G23_T0_350h_001_cat.xml -> G23_T0_350h_001
    base_prefix = xml_basename.replace('_cat.xml', '')
    
    if not dry_run:
        os.makedirs(output_dir, exist_ok=True)
        print(f"Ensured output directory exists: {output_dir}")
    
    files = sorted(os.listdir(cubelets_dir))
    count = 0
    
    print(f"Scanning directory: {cubelets_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Using base prefix: {base_prefix}")
    
    for filename in files:
        if not filename.startswith(base_prefix + '_'):
            continue
            
        # Structure: prefix_{id}_{suffix}
        # But wait, prefix itself contains underscores.
        # base_prefix = G23_T0_350h_001
        # filename = G23_T0_350h_001_1_chan.fits
        
        remainder = filename[len(base_prefix)+1:] # content after G23_T0_350h_001_
        # remainder = 1_chan.fits
        
        parts = remainder.split('_', 1)
        if len(parts) < 2:
            # Maybe just ID? unlikely for fits files but possible for others
            continue
            
        src_id = parts[0]
        suffix = parts[1]
        
        if src_id in mapping:
            new_name = f"{mapping[src_id]}_{suffix}"
            old_path = os.path.join(cubelets_dir, filename)
            new_path = os.path.join(output_dir, new_name)
            
            if dry_run:
                print(f"[DRY RUN] Copy: {filename} -> {os.path.join(os.path.basename(output_dir), new_name)}")
            else:
                shutil.copy2(old_path, new_path)
                print(f"Copied: {filename} -> {new_name}")
            count += 1
        else:
            # Sometimes ID matching might fail if leading zeros etc?
            # The XML IDs seem to be integers '1', '2'. Filenames have '1', '2'.
            # Should be fine.
            pass
            
    print(f"Processed {count} files.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Rename and copy cubelets based on SoFiA catalogue')
    parser.add_argument('xml_file', help='Path to the catalogue XML file')
    parser.add_argument('cubelets_dir', help='Path to the source cubelets directory')
    parser.add_argument('output_dir', help='Path to the destination directory')
    parser.add_argument('--dry-run', action='store_true', help='Print changes without executing')
    
    args = parser.parse_args()
    
    process_renaming(args.xml_file, args.cubelets_dir, args.output_dir, args.dry_run)
