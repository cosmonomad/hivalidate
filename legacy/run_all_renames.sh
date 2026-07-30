#!/bin/bash

# Output directory for all cubelets
OUTPUT_DIR="SB82605_jolly_cubelets"
mkdir -p "$OUTPUT_DIR"

# Iterate through all XML catalogue files
for xml_file in SB82605_jolly_*_cat.xml; do
    # Check if the file exists (in case the glob matches nothing)
    [ -e "$xml_file" ] || continue

    # Extract the base name (e.g., G23_T0_350h_001)
    # Remove the _cat.xml suffix
    base_name="${xml_file%_cat.xml}"
    
    # Construct the cubelets directory name
    cubelets_dir="${base_name}_cubelets"
    
    # Check if the cubelets directory exists
    if [ -d "$cubelets_dir" ]; then
        echo "Processing $base_name..."
        
        # Run the python script
        # Usage: python3 rename_cubelets.py <xml_file> <cubelets_dir> <output_dir>
        python3 rename_cubelets.py "$xml_file" "$cubelets_dir" "$OUTPUT_DIR"
        
    else
        echo "Warning: Directory $cubelets_dir not found for $xml_file. Skipping."
    fi
    
    echo "---------------------------------------------------"
done

echo "Batch processing complete."
