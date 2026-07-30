#!/usr/bin/env python

"""
This is a script to combine all xml files into one file and 
plot the data as a function of frequency.
"""

from astropy.io.votable import parse_single_table
from astropy.io.votable import from_table, writeto
from astropy.table import vstack
from glob import glob

import matplotlib.pyplot as plt
import numpy as np


def read_sofia_cat(filenames):
    """Read SoFiA catalog from XML files and 
        combine them into a single table.
    """
    tables = []
    for filename in filenames:
        table = parse_single_table(filename).to_table(use_names_over_ids=True)
        tables.append(table)
    return tables[0] if len(tables) == 1 else vstack(tables)


def frequency_to_channel(freq_mhz, ref_freq_mhz=1295.5, ref_channel=0):
    """Convert frequency in MHz to channel number."""
    # Using the provided reference values
    return (freq_mhz - ref_freq_mhz) / 0.0185 + ref_channel


# Read SoFiA catalog (in xml format)
sofia_files = sorted(glob("SB82605*_cat.xml"))
cat_sofia = read_sofia_cat(sofia_files)
cat_sofia.sort('ra')
writeto(from_table(cat_sofia), '_'.join(sofia_files[0].split('_')[0:2]) + '_cat.xml')
cat_sofia.sort('freq')

print(f"Read {len(cat_sofia)} sources from SoFiA catalog")

freq = cat_sofia['freq'] * 1e-6
flux = np.log10(cat_sofia['f_sum'])
chan = frequency_to_channel(freq)

# Save the flux measurement to a file
outname_prefix = sofia_files[0].split('_')[0]
np.savetxt(outname_prefix + '_freq_flux.txt', np.c_[chan, freq, flux], fmt=['%5d','%12.6f','%5.2f'])

# plot frequency vs flux
fig = plt.figure(1, figsize=(10, 6))
plt.clf()

ax = fig.add_subplot(111)
ax.scatter(freq, flux, s=2, linewidth=0)
ax.set_xlabel('Frequency (MHz)')
ax.set_ylabel('log (Flux (Jy Hz))')
#ax.set_xlim(1295.5, 1439.5)
ax.set_title('SoFiA Catalog: Frequency vs Flux')
ax.grid(True)
axh = ax.twiny()
axh.scatter(chan, flux, s=2)
axh.set_xlabel('Channel')
#axh.set_xlim(0, 7776)
plt.show()
#plt.savefig(outname_prefix + '_freq_flux.png', bbox_inches='tight')

