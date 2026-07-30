#!/usr/bin/env python

# Mosaic SoFiA moment maps

from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from reproject.mosaicking import reproject_and_coadd
from reproject import reproject_interp
from mpl_toolkits.axes_grid1.inset_locator import inset_axes
from mpl_toolkits.axes_grid1.inset_locator import zoomed_inset_axes
#from mpl_toolkits.axes_grid1.inset_locator import InsetPosition
from matplotlib.offsetbox import AnchoredText
from glob import glob
import matplotlib.pyplot as plt
import numpy as np
import os



def get_pix_coords(catalog, hdr):
    """ transform sky coordinates (ra, dec) to pixels coordinates
    """
    wcs = WCS(hdr).celestial
    ra = catalog['ra'].data
    dec = catalog['dec'].data
    pos = np.ma.vstack((ra, dec)).T
    pix = np.transpose(wcs.wcs_world2pix(pos, 0))
    pix = np.rint(pix).astype('int64')

    return pix

def convert_to_z(freq):
    """ Convert frequency to redshift
    """
    freq_HI = 1420405751.786    # Hz
    z = freq_HI / freq - 1.
    return z


def convert_to_vel(freq, v_frame='optical'):
    """ Convert frequency to velocity
    """
    freq_HI = 1420405751.786    # Hz
    c = 299792.458              # km/s
    if v_frame == 'optical':
        vel = c * (freq_HI / freq - 1.)
    elif v_frame == 'radio':
        vel = c * (1. - freq / freq_HI)
    else:
        print ('Not supported velocity frame')
        sys.exit(1)
    return vel

def get_header_info(fits_cube):
    # get info from data cube
    hdu = fits.getheader(fits_cube)
    wcs = WCS(hdu).celestial
    b_maj = fits.getheader(fits_cube)['BMAJ'] * 3600     # in arcsec
    b_min = fits.getheader(fits_cube)['BMIN'] * 3600     # in arcsec
    beam = b_maj * b_min
    b_pa = fits.getheader(fits_cube)['BPA']              # in deg
    d_nu = fits.getheader(fits_cube)['CDELT3']           # in Hz
    return beam, b_maj, b_min, b_pa, d_nu

def column_density(s_int, z, beam):
    n_hi = 2.33 * 10**20 * (1 + z)**4 * s_int / beam
    return n_hi

def column_density_sen(s_rms, z, beam, dnu, sigma):
    s_lim = s_rms * dnu * sigma
    n_hi_lim = column_density(s_lim, z, beam)
    return n_hi_lim

#def mask_low_column()


def mask_true(catalog_name, dir2true, ax, hdr):
    """
    For moment 0 maps
    """
    catalog_true = Table.read(catalog_name, format='ascii.csv')
    #mask_true = (catalog['qa'] == 1.0)
    #catalog_true = catalog[mask_true]
    #catalog_true = catalog

    x = get_pix_coords(catalog_true, hdr)[0]
    y = get_pix_coords(catalog_true, hdr)[1]

    #x = x[:2]
    #y = y[:2]
    #mom0_list = sorted(glob(dir2true + '*moment0.fits'))

    for i in range(len(catalog_true)):
        mom0_name = dir2true + 'SoFiA_' + str(catalog_true['name'][i].split()[1]) + '_mom0.fits'
        z = convert_to_z(catalog_true['freq'][i])
        print(mom0_name)
        print(x[i], y[i], z)

        hd = fits.getheader(mom0_name)
        x_size = hd['NAXIS1']
        y_size = hd['NAXIS2']
        print(f'x size: {x_size}, y size= {y_size}')
        #box = (x[i] - x_size, x[i] + x_size, y[i] - y_size, y[i] + y_size)
        #box = (x[i] + x_size,  y[i] + y_size, x_size*2, y_size*2)
        #box = (x[i] + x_size,  y[i] + y_size)
        #mom_box = (x[i] + x_size*2, y[i] + y_size*2, x_size, y_size)
        #mom_box = (x[i], y[i], x_size, y_size)
        mom_box = (x[i]-x_size/2, y[i]-y_size/2, x_size, y_size)
        #mom_box = (x[i] + x_size*2,  y[i] + y_size*2)
        #box = (x[i] ,  y[i])
        print(mom_box)
        #ax.plot(x[i], y[i], 'o', mfc='none', mec='C0', ms=20)
        """
        imsize = [(x[i] - x_size, y[i] - y_size), (x[i] + x_size, y[i] + y_size)]
        axinv = ax.transData.inverted()
        box_pos = axinv.transform(imsize).astype(int)
        print(box_pos)
        width = np.diff(box_pos, axis=0).astype(int)
        box = (box_pos[0][0], box_pos[0][1], width[0][0], width[0][1])
        """
        #xdisplay, ydisplay = ax.transData.transform((x[i], y[i]))
        #mom_box =(xdisplay, ydisplay, 10, 10)
        #ax2 = inset_axes(ax, width='200%', height='200%', bbox_to_anchor=box, bbox_transform=ax.transData)
        ax2 = zoomed_inset_axes(ax, 1, bbox_to_anchor=mom_box, bbox_transform=ax.transData)
        #ip = InsetPosition(ax, mom_box)
        #ax2.set_axes_locator(ip)
        #ax2 = inset_axes(ax, width='200%', height='200%', bbox_to_anchor=mom_box, bbox_transform=ax.transAxes)
        ax2.patch.set_alpha(0.0)
        ax2.tick_params(labelleft=False, labelbottom=False)
        ax2.set_xticks([])
        ax2.set_yticks([])
        [i.set_visible(False) for i in ax2.spines.values()]

        mom = fits.open(mom0_name)[0].data
        mom[mom==0] = np.nan
        """
        if z <= 0.02:
            ax2.imshow(mom, origin='lower', interpolation='nearest', cmap='Blues_r')
        elif (z > 0.02) & (z <= 0.04):
            ax2.imshow(mom, origin='lower', interpolation='nearest', cmap='Greens_r')
        elif (z > 0.04) & (z <= 0.06):
            ax2.imshow(mom, origin='lower', interpolation='nearest', cmap='Wistia_r')
        elif (z > 0.06):
            ax2.imshow(mom, origin='lower', interpolation='nearest', cmap='Reds_r')
        """
        ax2.imshow(mom, origin='lower', interpolation='nearest', cmap='rainbow')
        ax2.set_xlim(0, x_size)
        ax2.set_ylim(0, y_size)
        plt.draw()

        #input('Enter')
        #return ax2


def mask_true2(catalog_name, dir2true, ax, hdr):
    """
    For moment 1 maps
    """
    catalog = Table.read(catalog_name, format='ascii.csv')
    #mask_true = (catalog['qa'] == 1.0)
    #catalog_true = catalog[mask_true]
    catalog_true = catalog

    x = get_pix_coords(catalog_true, hdr)[0]
    y = get_pix_coords(catalog_true, hdr)[1]

    #x = x[:2]
    #y = y[:2]
    #mom0_list = sorted(glob(dir2true + '*moment0.fits'))

    for i in range(len(catalog_true)):
        mom1_name = dir2true + 'DINGO_' + str(catalog_true['name'][i].split()[1]) + '_mom1.fits'
        z = convert_to_z(catalog_true['freq'][i])
        print(mom1_name)
        print(x[i], y[i], z)

        hd = fits.getheader(mom1_name)
        x_size = hd['NAXIS1']
        y_size = hd['NAXIS2']
        print(f'x size: {x_size}, y size= {y_size}')
        #box = (x[i] - x_size, x[i] + x_size, y[i] - y_size, y[i] + y_size)
        #box = (x[i] + x_size,  y[i] + y_size, x_size*2, y_size*2)
        #box = (x[i] + x_size,  y[i] + y_size)
        #mom_box = (x[i] + x_size*2, y[i] + y_size*2, x_size, y_size)

        mom_box = (x[i] ,  y[i])
        print(mom_box)
        #ax.plot(x[i], y[i], 'o', mfc='none', mec='C0', ms=20)
        """
        imsize = [(x[i] - x_size, y[i] - y_size), (x[i] + x_size, y[i] + y_size)]
        axinv = ax.transData.inverted()
        box_pos = axinv.transform(imsize).astype(int)
        print(box_pos)
        width = np.diff(box_pos, axis=0).astype(int)
        box = (box_pos[0][0], box_pos[0][1], width[0][0], width[0][1])
        """
        #xdisplay, ydisplay = ax.transData.transform((x[i], y[i]))
        #mom_box =(xdisplay, ydisplay, 10, 10)
        #ax2 = inset_axes(ax, width='200%', height='200%', bbox_to_anchor=box, bbox_transform=ax.transData)
        ax2 = zoomed_inset_axes(ax, 4, bbox_to_anchor=mom_box, bbox_transform=ax.transData)
        #ip = InsetPosition(ax, mom_box)
        #ax2.set_axes_locator(ip)
        #ax2 = inset_axes(ax, width='200%', height='200%', bbox_to_anchor=mom_box, bbox_transform=ax.transAxes)
        ax2.patch.set_alpha(0.0)
        ax2.tick_params(labelleft=False, labelbottom=False)
        ax2.set_xticks([])
        ax2.set_yticks([])
        [i.set_visible(False) for i in ax2.spines.values()]

        mom = fits.open(mom1_name)[0].data
        mom[mom==0] = np.nan
        
        ax2.imshow(mom, origin='lower', interpolation='nearest', cmap='rainbow')
        ax2.set_xlim(0, x_size)
        ax2.set_ylim(0, y_size)
        plt.draw()

def make_mosaic_fits(dir2true, hdr, mosaic_true_name):
    """ Make mosaic fits file for true detections

    Parameters:
        dir2true (str): Directory to save the mosaic fits file
        hdr (astropy.io.fits.header.Header): Header of the original data cube
        data (np.ndarray): Data cube
    """
    fitslist = sorted(glob(dir2true + '*mom0.fits'))
    imsize = (hdr['NAXIS1'], hdr['NAXIS2'])
    data, footprint = reproject_and_coadd(fitslist, hdr, shape_out=imsize, reproject_function=reproject_interp)
    data = np.nan_to_num(data)
    # write to a FITS file
    fits.writeto(mosaic_true_name, data, hdr, overwrite=True)
    
    return data

catalog_name = 'validation_catalogue_SB82605_true.csv'
mosaic_name = 'mom0.fits'
mosaic_true_name = './SB82605_mom0_true.fits'
dir_true = './SB82605_jolly_cubelets_true/'
maskout_false = True


# Read header of the original data cube
hdr = fits.getheader(mosaic_name)
w = WCS(hdr)
wcs = w.celestial
hdr = wcs.to_header()

# Read data cube
data = fits.open(mosaic_name)[0].data
hd = fits.getheader(mosaic_name)
mask = (data >= 0.0)
data[mask] = np.nan

# Make mosaic fits file for true detections
data = make_mosaic_fits(dir_true, hd, mosaic_true_name)

# plot
fig = plt.figure(1)
#plt.style.use('dark_background')
plt.rc('font', family='serif')
plt.clf()
ax = fig.add_subplot(111, projection=wcs)
#data[data==0] = np.nan
#cmap.set_bad(color='black')
#ax = fig.add_subplot(111)
#plt.imshow(data, origin='lower', interpolation='nearest', cmap='afmhot', vmin=-10, vmax=100)
plt.imshow(data, origin='lower', interpolation='nearest', cmap='inferno', vmin=-40, vmax=400)
#plt.cm.inferno_r.set_bad(color='k')
ax.set_xlim(0.0, hd['NAXIS1']-1)
ax.set_ylim(0.0, hd['NAXIS2']-1)
#title = ax.set_title('DINGO Pilot Survey GAMA 23, 100hr', fontsize=14, backgroundcolor='black', horizontalalignment="center")
#title._bbox_patch._mutation_aspect = 0.05
#title.get_bbox_patch().set_boxstyle("square", pad=5.825)
#[i.set_color('white') for i in ax.spines.values()]
[i.set_linewidth(2.0) for i in ax.spines.values()]
#title = ax.set_title('True Detections (Traditional)', fontsize=14, backgroundcolor='black', horizontalalignment="center")
#title = ax.set_title('DINGO Pilot + Main Survey GAMA 23, 350hr', fontsize=16, horizontalalignment="center")

#title._bbox_patch._mutation_aspect = 0.05

x = ax.coords[0]
y = ax.coords[1]

x.set_axislabel('RA (J2000)', fontsize=16)
y.set_axislabel('Dec (J2000)', fontsize=16)

x.set_major_formatter('hh:mm:ss.s')
y.set_major_formatter('dd:mm')
x.set_ticklabel(size=14)
y.set_ticklabel(size=14)
x.set_ticks(color='white', width=1.5)
y.set_ticks(color='white', width=1.5)
ax.grid()

"""
# for mom0
mask_true(catalog_name, dir_true, ax, hd)
ax.grid()

# for mom1
#mask_true2(catalog_name, dir_true, ax, hd)

ax.axis('off')
x.tick_params(labelleft=False, labelbottom=False)
y.tick_params(labelleft=False, labelbottom=False)
x.set_ticks_visible(False)
y.set_ticks_visible(False)
"""

plt.show()
#plt.savefig('SB82605_jolly_true_mom0.png', bbox_inches='tight')
