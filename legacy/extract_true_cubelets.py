import os
import shutil
import csv
import glob

csv_file = 'validation_catalogue_SB82605_true.csv'
src_dir = 'SB82605_jolly_cubelets'
dst_dir = 'SB82605_jolly_cubelets_true'

def main():
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
        print(f"Created directory: {dst_dir}")

    count = 0
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['name'].replace(' ', '_')
            
            pattern = os.path.join(src_dir, f"{name}*")
            matching_files = glob.glob(pattern)
            
            for file_path in matching_files:
                filename = os.path.basename(file_path)
                dest_path = os.path.join(dst_dir, filename)
                shutil.copy2(file_path, dest_path)
                count += 1
                
    print(f"Done. Copied {count} files matching names from {csv_file} to {dst_dir}.")

if __name__ == '__main__':
    main()
