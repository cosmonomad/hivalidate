#!/usr/bin/env python
import os
import time
import requests
import numpy as np
import matplotlib.pyplot as plt
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.visualization import make_lupton_rgb
import astropy.units as u

# 1. Define target sample list (supports decimal degrees or sexagesimal strings)
targets = [
    {"name": "galaxy_A", "ra": "190.1086", "dec": "1.2005"},
    {"name": "galaxy_B", "ra": "00h00m00s", "dec": "+00d00m00s"},
    {"name": "cluster_C", "ra": "211.2134", "dec": "15.1124"}
]

# 2. Configuration parameters
layers = ["ls-dr10", "ls-dr9"]          # Legacy Survey layers to query
size = 256                             # Dimensions in pixels (max 512)
pixscale = 0.262                       # Arcsec per pixel (0.262 matches DECam)
output_dir = "./legacy_dual_outputs"

os.makedirs(output_dir, exist_ok=True)

# 3. Processing loop
for target in targets:
    try:
        if 'h' in str(target['ra']) or ':' in str(target['ra']):
            coords = SkyCoord(target['ra'], target['dec'], frame='icrs')
        else:
            coords = SkyCoord(ra=float(target['ra']), dec=float(target['dec']), unit=u.deg, frame='icrs')
    except Exception as e:
        print(f"Skipping {target['name']} due to coordinate error: {e}")
        continue

    ra_deg = coords.ra.deg
    dec_deg = coords.dec.deg

    for layer in layers:
        print(f"Processing {target['name']} from {layer}...")
        
        # Build API endpoint url for pixel-level data extraction
        url = (
            f"https://www.legacysurvey.org/viewer/cutout.fits?"
            f"ra={ra_deg}&dec={dec_deg}&"
            f"size={size}&pixscale={pixscale}&"
            f"layer={layer}&bands=gri"
        )
        
        try:
            response = requests.get(url, timeout=20)
            
            if response.status_code == 200:
                # Temporary file designation to process the download stream
                temp_fits_path = os.path.join(output_dir, f"temp_{target['name']}_{layer}.fits")
                
                with open(temp_fits_path, 'wb') as f:
                    f.write(response.content)
                
                # --- Read Data & Generate Composites ---
                with fits.open(temp_fits_path) as hdul:
                    data_cube = hdul[0].data
                    header = hdul[0].header  # Extract spatial/WCS metadata
                    
                    if data_cube is not None and data_cube.ndim == 3 and data_cube.shape[0] == 3:
                        # Extract bands (Plane 0=g, 1=r, 2=i)
                        g = np.nan_to_num(data_cube[0])
                        r = np.nan_to_num(data_cube[1])
                        i = np.nan_to_num(data_cube[2])
                        
                        # Apply non-linear Lupton scaling (stretch and Q handle contrast)
                        rgb_array = make_lupton_rgb(image_r=i, image_g=r, image_b=g, stretch=0.5, Q=10)
                        
                        # --- OUTPUT TYPE 1: Standard PNG Image ---
                        png_filename = f"{target['name']}_{layer}_composite.png"
                        png_filepath = os.path.join(output_dir, png_filename)
                        plt.imsave(png_filepath, rgb_array)
                        
                        # --- OUTPUT TYPE 2: Multi-channel FITS Cube ---
                        # Transpose or stack back into FITS layout: (Channel, Y, X)
                        # Plane 0=Red(i), Plane 1=Green(r), Plane 2=Blue(g)
                        fits_cube = np.stack([rgb_array[:,:,0], rgb_array[:,:,1], rgb_array[:,:,2]], axis=0)
                        
                        # Inject lineage documentation into the metadata header
                        header['HISTORY'] = "RGB color scaling applied via astropy make_lupton_rgb"
                        header['HISTORY'] = "Data layers order: 0=Red(i), 1=Green(r), 2=Blue(g)"
                        
                        composite_hdu = fits.PrimaryHDU(data=fits_cube, header=header)
                        
                        fits_filename = f"{target['name']}_{layer}_composite.fits"
                        fits_filepath = os.path.join(output_dir, fits_filename)
                        composite_hdu.writeto(fits_filepath, overwrite=True)
                        
                        print(f"  [Success] Saved PNG and FITS files for {target['name']}.")
                    else:
                        print(f"  [Warning] Unexpected structure found in response. Skipping {target['name']}.")
                
                # Clean up the temporary download cache file
                if os.path.exists(temp_fits_path):
                    os.remove(temp_fits_path)
                    
                time.sleep(0.5)  # Polite scrape interval delay
            else:
                print(f"  [Failed] Layer '{layer}' returned status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"  [Network Error] Connection failed for {target['name']} on layer {layer}: {e}")

print("\nBatch processing finished! Both FITS and PNG formats are saved in:", os.path.abspath(output_dir))

