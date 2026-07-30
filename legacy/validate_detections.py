#!/usr/bin/env python

# Validate all detections from SoFiA 
# by plotting moment maps, HI spectrum and PV diagram of detected sources
# by cross-matching with a catalogue with spectroscopic redshifts 
# if available for a target field.  

from astropy.table import Table, Column
from astropy.io import fits

from astropy.io.votable import parse_single_table
from astropy.io.votable import from_table, writeto
from astropy import units as u
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from astropy.visualization.wcsaxes import WCSAxes
from astropy.cosmology import FlatLambdaCDM
from astroquery.skyview import SkyView
from matplotlib.patches import Ellipse, Circle
from matplotlib.ticker import MaxNLocator, FormatStrFormatter
from MontagePy.main import mSubimage
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import warnings
import sys, os
import logging
import time
import requests

def convert_to_z(freq):
    """ Convert frequency to redshift
    
        Parameters
        ----------
        freq: frequency to convert in Hz

        Returns
        -------
        z: redshift converted from frequency
    """
    freq_HI = 1420405751.786    # Hz
    z = freq_HI / freq - 1.
    return z


def convert_to_vel(freq, v_frame='optical'):
    """ Convert frequency to velocity
        
        Parameters
        ----------
        freq: frequency to convert in Hz
        v_frame: velocity frame used for conversion (optical or radio)
    
        Returns
        -------
        vel: velocity converted from frequency
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


def convert_to_vel_disp(freq_disp, freq_c):
    """ Convert frequency width to velocity dispersion
        
        Parameters
        ----------
        freq_disp: frequency width 
        freq_c: central frequency 

        Returns
        -------
        vel_disp: velocity width
    """
    freq_HI = 1420405751.786    # Hz
    c = 299792.458              # km/s
    vel_disp = c * freq_disp / freq_c
    return vel_disp


def convert_to_freq(vel, v_frame='optical'):
    """ Convert  velocity to frequency

        Parameters
        ----------
        vel: velocity to convert in m/s
        v_frame: velocity frame used for conversion (optical or radio)
    
        Returns
        -------
        freq: frequency converted from velocity
    """
    freq_HI = 1420405751.786    # Hz
    c = 299792458              # m/s
    if v_frame == 'optical':
        freq = freq_HI / (vel / c + 1.)
    elif v_frame == 'radio':
        freq = freq_HI * (1. - vel / c)
    else:
        print ('Not supported velocity frame')
        exit(1)
    return freq


def himass(s_int, z, rest_frame='frequency'):
    """ Convert integrated HI flux to HI mass at log scale

        Parameters
        ----------
        s_int: integrated HI flux
        z: redshift
        rest_frame: rest frame used for conversion (frequency or velocity)
    
        Returns
        -------
        np.log10(hi_mass): HI mass at log scale
    
    """
    cosmo = FlatLambdaCDM(H0=70., Om0=0.3, Tcmb0=2.725)
    dL = cosmo.luminosity_distance(z).value
    if rest_frame == 'frequency':
        hi_mass = 49.7 * dL**2 * s_int
    elif rest_frame == 'velocity':
        hi_mass = 2.35 * 1e5 / (1 + z) * dL**2 * s_int * 1e-3
    return np.log10(hi_mass)


def get_header_info(fits_cube):
    """ Get info from data cube (beam sizes and frequency width)

        Parameters
        ----------
        fits_cube: data cube name

        Returns
        -------
        beam: major x minor beam size
        b_maj: major axis size of the beam
        b_min: minor axis size of the beam
        b_pa: position angle of the beam
        d_nu: frequency width
    """

    hdu = fits.getheader(fits_cube)
    wcs = WCS(hdu).celestial
    b_maj = fits.getheader(fits_cube)['BMAJ'] * 3600     # in arcsec
    b_min = fits.getheader(fits_cube)['BMIN'] * 3600     # in arcsec
    beam = b_maj * b_min
    b_pa = fits.getheader(fits_cube)['BPA']              # in deg
    d_nu = fits.getheader(fits_cube)['CDELT3']           # in Hz
    return beam, b_maj, b_min, b_pa, d_nu


def get_wcs(fitsfile):
    """ Get WCS info from a data cube
    
        Parameters
        ----------
        fitsfile: data cube name
    
        Returns
        -------
        wcs: WCS info
    """
    hdu = fits.getheader(fitsfile)
    wcs = WCS(hdu).celestial
    return wcs


def get_table_info(catalog, rest_frame):
    """ Extract useful info from SoFiA catalog (VO-table in xml format)
        to make a table in LaTex format for publication
    
        Parameters
        ----------
        catalog: SoFiA catalog
        rest_frame: rest frame used for some conversion

        Returns
        -------
        tab: new SoFiA table
    """

    if rest_frame == 'frequency':
        #col1 = Column(catalog['id'], name='id')
        col2 = Column(catalog['name'], name='name')
        col4 = Column(catalog['ra'], name='ra')
        col5 = Column(catalog['dec'], name='dec')
        col6 = Column(catalog['freq'], name='freq')
        col7 = Column(convert_to_z(catalog['freq']), name='z')
        col8 = Column(convert_to_vel(catalog['freq']), name='v_opt')
        col9 = Column(catalog['f_sum'], name='s_int')
        col10 = Column(convert_to_vel_disp(catalog['wm50'], col6), name='wm50')
        col11 = Column(convert_to_vel_disp(catalog['w20'], col6), name='w20')
        hi_mass_values = himass(catalog['f_sum'], col7, rest_frame='frequency')
        if hasattr(hi_mass_values, 'filled'):
            hi_mass_values = hi_mass_values.filled(np.nan)  # Fill masked values with NaN
        col12 = Column(hi_mass_values, name='hi_mass')
        tab = Table([col2, col4, col5, col6, col7, col8, col9, col10, col11, col12])
        #tab = Table([col1, col2, col4, col5, col6, col7, col8, col9, col10, col11])
    else:
        print('Please check if rest frame is frequency')
        sys.exit(1)

    return tab

def get_source_list(catalog):
    """ Extract a list of source names for cubeltes from the SoFiA catalog
    """
    sname_base = 'SoFiA_'
    source_list = []
    for i in range(len(catalog)):
        source_list.append(sname_base + catalog['name'][i].split()[1])

    return source_list

def get_source_name(catalog):
    """ Extract the name of source
    """
    sname = catalog['name'].split()[1]

    return sname

def get_coords(catalog):
    """ Convert coordinates in deg to hms dms format
    """
    ra = catalog['ra']
    dec = catalog['dec']
    pos_deg = SkyCoord(ra=ra, dec=dec, unit='deg')
    pos = pos_deg.to_string('hmsdms', sep=':')

    return pos

def get_opt_imag(catalog, imag_source, pix_size):
    """ Download optical image cutsouts of sources from SkyVeiw via astroquery
    """

    ra = catalog['ra']
    dec = catalog['dec']
    pos = SkyCoord(ra=ra, dec=dec, unit='deg')

    # get url link to images
    max_retries = 5
    for attempt in range(max_retries):
        try:
            fitslist = SkyView.get_images(position=pos, survey=imag_source, projection='Sin', pixels=pix_size)
            if not fitslist:
                raise ValueError("SkyView returned empty image list")
            return fitslist
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, ValueError) as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                logging.warning(f"SkyView fetch error: {e}. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error(f"Failed to retrieve image after {max_retries} attempts.")
                # We can return an empty list or raise. By raising, we ensure the script fails gracefully instead of an obscure IndexError.
                raise e

def get_cont_imag(catalog, path_to_contimag, outdir, outfile_base, size):
    """ Cut out contiuum imaage of detected sources
    """
    ra = catalog['ra']
    dec = catalog['dec']
    name = catalog['name']
    outfile = outdir + '_'.join(name.split()) + '_cont.fits'
    rtn = mSubimage(path_to_contimag, outfile, ra, dec, size, size)

    return outfile

def column_density(s_int, z, beam):
    """ Calculate column density
    """
    n_hi = 2.33 * 10**20 * (1 + z)**4 * s_int / beam
    return n_hi

def column_density_sen(s_rms, z, beam, dnu, sigma):
    """ Calculate column density sensitivity
    """
    s_lim = s_rms * dnu * sigma
    n_hi_lim = column_density(s_lim, z, beam)
    return n_hi_lim

def search_gama(sofia, gama, sep_ang):
    """ Search GAMA counterparts of SoFiA detections

        Parameters
        ----------
        sofia: sofia catalog
        gama: GAMA catalog
        sep_ang: search radius (angular separation)

        Returns
        -------
        num_match: the number of cross-matched galaxies
        gama: cross-matched GAMA catalog
        sofia: if no cross-match

    """
    c = 299792.458

    # Read sofia catalog
    ra_sofia = sofia['ra'] * u.deg
    dec_sofia = sofia['dec'] * u.deg
    vel_sofia = sofia['v_opt']
    wm50_sofia = sofia['wm50']
    w20_sofia = sofia['w20']
    sofia_pos = SkyCoord(ra_sofia, dec_sofia)

    # Read GAMA catalog
    mask_z = gama['Z'] < 0.1
    gama = gama[mask_z]
    ra_gama = gama['RAmax'] * u.deg
    dec_gama = gama['Decmax'] * u.deg
    z_gama = cat_gama['Z']
    vel_gama = c * z_gama
    GAMApos = SkyCoord(ra_gama, dec_gama)

    # Cross-match using 30 arcsec angle and velocity separation
    sep_sky = sofia_pos.separation(GAMApos).arcsec
    gama.add_column(col=sep_sky, name='sep_sky')
    sep_vel = abs(vel_sofia - vel_gama)
    mask_match = (sep_sky <= sep_ang) & (sep_vel <= (0.6 * wm50_sofia + 30))   # angular and velocity separation
    #mask_match = (sep_sky <= sep_ang) & (sep_vel <= (0.6 * w20_sofia + 30))   # angular and velocity separation
    num_match = np.count_nonzero(mask_match)
    if num_match > 0:
        gama = gama[mask_match]
        return num_match, gama
    else:
        return num_match, sofia

def copy_data(indir, outdir, sname, name, qflag):
    """ Copy SoFiA products to new directories based on detection flag
        and rename the files with DINGO name added (prefixed)
    """
    inCube = indir + sname + '_cube.fits'
    inMom0 = indir + sname + '_mom0.fits'
    inMom1 = indir + sname + '_mom1.fits'
    inMom2 = indir + sname + '_mom2.fits'
    inSpec = indir + sname + '_spec.txt'

    if qflag == 't':
        if not os.path.isdir(outdir + 'true'):
            os.system('mkdir -p ' + outdir + 'true')

        outCube = outdir + 'true/' + '_'.join(name.split()) + '_cube.fits'
        outMom0 = outdir + 'true/' + '_'.join(name.split()) + '_mom0.fits'
        outMom1 = outdir + 'true/' + '_'.join(name.split()) + '_mom1.fits'
        outMom2 = outdir + 'true/' + '_'.join(name.split()) + '_mom2.fits'
        outSpec = outdir + 'true/' + '_'.join(name.split()) + '_spec.txt'

    elif qflag == 'f':
        if not os.path.isdir(outdir + 'false'):
            os.system('mkdir -p ' + outdir + 'false')

        outCube = outdir + 'false/' + '_'.join(name.split()) + '_cube.fits'
        outMom0 = outdir + 'false/' + '_'.join(name.split()) + '_mom0.fits'
        outMom1 = outdir + 'false/' + '_'.join(name.split()) + '_mom1.fits'
        outMom2 = outdir + 'false/' + '_'.join(name.split()) + '_mom2.fits'
        outSpec = outdir + 'false/' + '_'.join(name.split()) + '_spec.txt'

    elif qflag == 'u':
        if not os.path.isdir(outdir + 'uncertain'):
            os.system('mkdir -p ' + outdir + 'uncertain')
        
        outCube = outdir + 'uncertain/' + '_'.join(name.split()) + '_cube.fits'
        outMom0 = outdir + 'uncertain/' + '_'.join(name.split()) + '_mom0.fits'
        outMom1 = outdir + 'uncertain/' + '_'.join(name.split()) + '_mom1.fits'
        outMom2 = outdir + 'uncertain/' + '_'.join(name.split()) + '_mom2.fits'
        outSpec = outdir + 'uncertain/' + '_'.join(name.split()) + '_spec.txt'

    elif qflag == 'd':
        if not os.path.isdir(outdir + 'duplicates'):
            os.system('mkdir -p ' + outdir + 'duplicates')
        
        outCube = outdir + 'duplicates/' + '_'.join(name.split()) + '_cube.fits'
        outMom0 = outdir + 'duplicates/' + '_'.join(name.split()) + '_mom0.fits'
        outMom1 = outdir + 'duplicates/' + '_'.join(name.split()) + '_mom1.fits'
        outMom2 = outdir + 'duplicates/' + '_'.join(name.split()) + '_mom2.fits'
        outSpec = outdir + 'duplicates/' + '_'.join(name.split()) + '_spec.txt'
        
    os.system('cp ' + inCube + ' ' + outCube)
    os.system('cp ' + inMom0 + ' ' + outMom0)
    os.system('cp ' + inMom1 + ' ' + outMom1)
    os.system('cp ' + inMom2 + ' ' + outMom2)
    os.system('cp ' + inSpec + ' ' + outSpec)

def get_pv_data(pvfits):
    """Get PV diagram from FITS file
    """
    pv = fits.getdata(pvfits)
    hdu_pv = fits.getheader(pvfits)
    hdu_pv['CDELT2'] = hdu_pv['CDELT2'] * 1e-6
    hdu_pv['CRVAL2'] = hdu_pv['CRVAL2'] * 1e-6
    wcs_pv = WCS(hdu_pv)

    return pv, wcs_pv    


################################################################################
# Ignore astropy warning
warnings.simplefilter('ignore')

# start logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Create file handler
fileHandle = logging.FileHandler('validation.log', mode='w+', encoding='utf-8')
fileHandle.setLevel(logging.INFO)

# Create formatter and set it for the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fileHandle.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(fileHandle)

# Input parameters (paths, source names)
cont_file = '/scratch/ja3/jrhee/WALLABY/SB51535/image.i.WALLABY_2051-53B.SB51535.cont.taylor.0.restored.conv.fits'
cont_subimg_dir = './cont_images/'
save_dir = './output_validation/'
dir_cubelets = './SB82605_jolly_cubelets/'
dir_gamacat = './gkvScienceCatv02_G23.csv'


# Control keys for writing files
do_validation = False
update_cat = True
write_latex_table = True
do_CASA_region_file = False
do_gama_crossmatch = os.path.exists(dir_gamacat)
outname = 'sofia_cat_SB82605_jolly'

if not os.path.isdir(cont_subimg_dir):
    os.system('mkdir -p ' + cont_subimg_dir)

if not os.path.isdir(save_dir):
    os.system('mkdir -p ' + save_dir)

# Read GAMA catalogue
if do_gama_crossmatch:
    cat_gama = Table.read(dir_gamacat, format='ascii.csv')
    mask_z = cat_gama['Z'] < 0.1
    cat_gama = cat_gama[mask_z]
    ra_gama = cat_gama['RAmax'] * u.deg
    dec_gama = cat_gama['Decmax'] * u.deg
    z_gama = cat_gama['Z']
    GAMAcat = SkyCoord(ra_gama, dec_gama)

# Read SoFiA catalog (in xml format)
sofia_file = 'SB82605_jolly_cat.xml'
cat_sofia = parse_single_table(sofia_file).to_table(use_names_over_ids=True)
cat_sofia.sort('name')

# Extract useful info from SoFiA catalog
tab_sofia = get_table_info(cat_sofia, rest_frame='frequency')


# Get optical & continuum images, moment maps
# sources list
source_list = get_source_list(cat_sofia)

# Dection flag (0: false, 1: true, 2: uncertain)
qa = np.zeros(len(cat_sofia))

# The number of cross_matched GAMA objects
nCrossMat = np.zeros(len(cat_sofia))

for i, sname in enumerate(source_list):
    fname_cube = dir_cubelets + sname + '_cube.fits'
    fname_mom0 = dir_cubelets + sname + '_mom0.fits'
    fname_mom1 = dir_cubelets + sname + '_mom1.fits'
    fname_mom2 = dir_cubelets + sname + '_mom2.fits'
    fname_spec = dir_cubelets + sname + '_spec.txt'
    fname_pv = dir_cubelets + sname + '_pv.fits'

    # Get info from data
    beam, b_maj, b_min, b_pa, d_nu = get_header_info(fname_cube)
    wcs_mom = get_wcs(fname_mom0)
    npix = max(wcs_mom.array_shape) * 5

    # Get an HI spectrum
    dat_spec = Table.read(fname_spec, format='ascii')
    freq = dat_spec['col2'] * 1e-6    # in MHz
    vel = convert_to_vel(freq * 1e6)
    spec = dat_spec['col3']
    vel_sys = tab_sofia['v_opt'][i]

    # Read optical image
    try:
        hdu = get_opt_imag(cat_sofia[i], 'DSS2 Red', npix)[0]
        wcs_opt = WCS(hdu[0].header)
        opt_data = hdu[0].data
        # Set the location of syntheised beam on the figure
        beam_loc_ra = wcs_opt.array_index_to_world(20, 20).ra.value
        beam_loc_dec = wcs_opt.array_index_to_world(20, 20).dec.value
        cont_imag_size = npix * hdu[0].header['CDELT2']
    except ValueError:
        logging.warning("No optical image found for source %s. Using blank placeholder.", sname)
        wcs_opt = wcs_mom
        opt_data = np.zeros(mom0.shape)
        # Set the location of syntheised beam on the figure using mom0's smaller size footprint
        try:
            beam_loc_ra = wcs_opt.array_index_to_world(5, 5).ra.value
            beam_loc_dec = wcs_opt.array_index_to_world(5, 5).dec.value
        except Exception:
            beam_loc_ra = tab_sofia['ra'][i]
            beam_loc_dec = tab_sofia['dec'][i]
        
        hdu_mom = fits.getheader(fname_mom0)
        cont_imag_size = npix * abs(hdu_mom.get('CDELT2', 0.0011))

    # Cut out continuum images of the sources from DINGO continuum map
    contfile = get_cont_imag(cat_sofia[i], cont_file, cont_subimg_dir, sname, cont_imag_size)

    cont = fits.getdata(contfile)
    wcs_cont = WCS(fits.getheader(contfile)).celestial

    # Load moment map data
    #print(fname_pv)
    mom0 = fits.getdata(fname_mom0)
    mom1 = fits.getdata(fname_mom1)
    mom2 = fits.getdata(fname_mom2)
    pv_data, wcs_pv = get_pv_data(fname_pv)
    freq_c = tab_sofia['freq'][i]

    # Convert frequency units in Hz to velocity (km/s)
    mom1_vel = convert_to_vel(mom1)
    mom2_vel = convert_to_vel_disp(mom2, cat_sofia['freq'][i])

    # Convert moment0 map to column density map
    col_den_map = column_density(mom0, tab_sofia['z'][i], beam) * 1e-19
    sen_lim = column_density_sen(cat_sofia['rms'][i], tab_sofia['z'][i], beam, d_nu, 1) * 1e-19
    #id = str(cat_sofia['id'][i]).zfill(4)
    id = str(i).zfill(3)
    name = cat_sofia['name'][i]
    #print(f'{i} {name}: contour levels 1, 3, 5, 7, 9 sigma of sensitivity limit: {sen_lim:.2f}, {3*sen_lim:.2f}, {5*sen_lim:.2f}, {7*sen_lim:.2f}, {9*sen_lim:.2f} x 10^-19')
    logging.info('%d D%s %s: contour levels 1, 3, 5, 7, 9 sigma of sensitivity limit: %.2f, %.2f, %.2f, %.2f, %.2f x 10^-19' , i, id, sname, sen_lim, 3*sen_lim, 5*sen_lim, 7*sen_lim, 9*sen_lim)

    # Mask out low column density data (< 1 sigma)
    mask = (col_den_map <= sen_lim*1)
    mom1_vel = np.ma.array(mom1_vel, mask=mask)
    mom2_vel = np.ma.array(mom2_vel, mask=mask)

    # Cross match with GAMA
    nMatch = 0
    if do_gama_crossmatch:
        nMatch, matchCat = search_gama(tab_sofia[i], cat_gama, 105)
        c = 299792.458
        if nMatch > 0:
            matchCat.sort('sep_sky')
            cz = matchCat['Z'] * c
            print(matchCat)
            for j in range(nMatch):
                logging.info('    D%s cross-matched with GAMA CATAID %d in angular separation of %.2f arcsec', id, matchCat['CATAID'][j], matchCat['sep_sky'][j])
        else:
            cz = matchCat['z'] * c
    # Update the number of cross-matched GAMA
    nCrossMat[i] = nMatch

    ############################################################################
    # plot maps
    ############################################################################

    plt.close('all')
    plt.rc('font', family='serif')
    #fig = plt.figure(1, figsize=(23, 5))
    #fig = plt.figure(1, figsize=(12, 11))
    fig = plt.figure(1, figsize=(18, 11))
    #fig.subplots_adjust(left=0.05, right=0.98, hspace=0.1, wspace=0.02, bottom=0.06, top=0.95)
    fig.subplots_adjust(left=0.05, right=0.98, wspace=0.1)

    # optical & mom0
    ax = fig.add_subplot(231, projection=wcs_opt)
    ax.contour(col_den_map, levels=[1*sen_lim, 3*sen_lim, 7*sen_lim, 9*sen_lim, 11*sen_lim, 25*sen_lim], transform=ax.get_transform(wcs_mom))
    if opt_data.std() > 0:
        vmin, vmax = opt_data.mean() - 3*opt_data.std(), opt_data.mean() + 3*opt_data.std()
    else:
        vmin, vmax = 0, 1
    ax.imshow(opt_data, origin='lower', interpolation='nearest', cmap='Greys', vmin=vmin, vmax=vmax)

    # if cross-matched with GAMA, overlay soruces
    mk = ['x', '+', (5, 2), '1', '2', '3', '4']
    if nMatch > 0:
        for j in range(nMatch):
            ax.scatter(matchCat['RAmax'][j], matchCat['Decmax'][j], transform=ax.get_transform('fk5'), s=40, marker=mk[j], lw=2.0, label='CATAID '+str(matchCat['CATAID'][j]))

    ax.coords.grid(color='k', alpha=0.5, linestyle='dashed')
    ax.coords[0].set_major_formatter('hh:mm:ss')
    ax.coords[1].set_major_formatter('dd:mm')
    ax.coords[0].set_axislabel('RA (J2000)', fontsize=14)
    ax.coords[1].set_axislabel('Dec (J2000)', fontsize=14)

    ax.annotate('Moment 0', (0.75, 0.93), size=12, xycoords='axes fraction', bbox=dict(boxstyle='round', fc='w', alpha=0.7))
    #ax.set_title(sname.split('_')[-1] + '(Optical DSS)', size=14)
    ax.set_title('Optical DSS2 Red', size=14)

    ellip = Ellipse((beam_loc_ra, beam_loc_dec), b_maj/3600, b_min/3600, angle=b_pa, fc='C3', ec='C3', alpha=0.5, transform=ax.get_transform('fk5'))
    ax.add_patch(ellip)
    if nMatch > 0:
        ax.legend(loc='upper left')

    # contmap & mom0
    ax1 = fig.add_subplot(232, projection=wcs_cont)
    ax1.contour(col_den_map, levels=[1*sen_lim, 3*sen_lim, 7*sen_lim, 9*sen_lim, 11*sen_lim, 25*sen_lim], transform=ax1.get_transform(wcs_mom))
    #ax1.imshow(cont, origin='lower', interpolation='nearest', cmap='afmhot', vmin=cont.mean() - 7*cont.std(), vmax=cont.mean() + 7*cont.std())
    ax1.imshow(cont, origin='lower', interpolation='nearest', cmap='afmhot', vmin=-0.0001, vmax=0.00025)

    ax1.coords.grid(color='k', alpha=0.5, linestyle='dashed')
    ax1.coords[0].set_major_formatter('hh:mm:ss')
    ax1.coords[1].set_major_formatter('dd:mm')
    ax1.coords[0].set_axislabel('RA (J2000)', fontsize=14)
    ax1.coords[1].set_auto_axislabel(False)
    #ax1.coords[1].set_axislabel('Dec (J2000)', fontsize=14)

    ax1.annotate('Moment 0', (0.75, 0.93), size=12, xycoords='axes fraction', bbox=dict(boxstyle='round', fc='w', alpha=0.7))
    ax1.set_title('DINGO Continuum', size=14)

    # mom 0
    ax2 = fig.add_subplot(234, projection=wcs_opt)
    m1 = ax2.imshow(mom0, origin='lower', interpolation='nearest', cmap='YlOrBr', transform=ax2.get_transform(wcs_mom))
    ax2.contour(col_den_map, levels=[1*sen_lim, 3*sen_lim, 7*sen_lim, 9*sen_lim, 11*sen_lim, 25*sen_lim], lw=1.0, transform=ax2.get_transform(wcs_mom))

    ax2.coords.grid()
    ax2.coords[0].set_major_formatter('hh:mm:ss')
    ax2.coords[1].set_major_formatter('dd:mm')
    ax2.coords[0].set_axislabel('RA (J2000)', fontsize=14)
    ax2.coords[1].set_axislabel('Dec (J2000)', fontsize=14)

    ax2.set_xlim(ax.get_xlim())
    ax2.set_ylim(ax.get_ylim())

    ax2.annotate('Moment 0', (0.75, 0.93), size=12, xycoords='axes fraction', bbox=dict(boxstyle='round', fc='w', alpha=0.7))
    #cbar = plt.colorbar(m1, orientation='vertical', pad=0.01, aspect=30)
    #cbar.ax.set_ylabel(r'Velocity (km s$^{-1}$)')

    # mom 1
    ax3 = fig.add_subplot(235, projection=wcs_opt)
    m2 = ax3.imshow(mom1_vel, origin='lower', interpolation='nearest', cmap='jet', transform=ax3.get_transform(wcs_mom))

    ax3.coords.grid()
    ax3.coords[0].set_major_formatter('hh:mm:ss')
    ax3.coords[1].set_major_formatter('dd:mm')
    ax3.coords[0].set_axislabel('RA (J2000)', fontsize=14)
    ax3.coords[1].set_auto_axislabel(False)
    #ax3.coords[1].set_axislabel('Dec (J2000)', fontsize=14)

    ax3.set_xlim(ax.get_xlim())
    ax3.set_ylim(ax.get_ylim())

    ax3.annotate('Moment 1', (0.75, 0.93), size=12, xycoords='axes fraction', bbox=dict(boxstyle='round', fc='w', alpha=0.7))
    cbar = plt.colorbar(m2, orientation='vertical', pad=0.01, aspect=30)
    cbar.ax.set_ylabel(r'Velocity (km s$^{-1}$)')

    # spectrum
    ax4 = fig.add_subplot(233)
    ax4.plot(vel, spec, color='k')
    ax4.axvline(vel_sys, color='grey', ls='dotted')
    ax4.axhline(0, color='grey', ls='dotted')
    #ax4.set_xlabel('Frequency (MHz)', fontsize=14)
    ax4.set_xlabel('Velocity (km/s)', fontsize=14)
    ax4.set_ylabel('Flux density (Jy)', fontsize=14)
    #ax4.set_title('HI spectrum', fontsize=14)
    ax4.annotate('HI Spectrum', (0.75, 0.93), size=12, xycoords='axes fraction', bbox=dict(boxstyle='round', fc='silver', alpha=0.7))
    ax4.grid()
    ax4h = ax4.twiny()
    ax4h.invert_xaxis()
    ax4h.plot(freq, spec, color='k')
    ax4h.ticklabel_format(axis='x', style='plain', useOffset=False)
    ax4h.xaxis.set_major_formatter(FormatStrFormatter('%.1f'))
    ax4h.set_xlabel('Frequency (MHz)', fontsize=12, labelpad=8)
    # if cross-matched with GAMA, overlay soruces
    cs = ['C0', 'C1', 'C2', 'C3', 'C4']
    if nMatch > 0:
        for j in range(nMatch):
            #ax4.axvline(cz[j], ls=lstyle[j], label='CATAID ' + str(matchCat['CATAID'][j]))
            ax4.axvline(cz[j], ls='dashed', color=cs[j], lw=1.5, label='CATAID ' + str(matchCat['CATAID'][j]))
        ax4.legend(loc='upper left', frameon=False)

    #plt.suptitle(f'DCATAID ' + str(tab_sofia['id'][i]).zfill(4) + ': ' + sname.split('_')[-1] + ' (RA: ' + str(tab_sofia['ra'][i]) + ', Dec: ' + str(tab_sofia['dec'][i]) + ')', y=0.96, fontsize=16)
    plt.suptitle('DINGO {0} (RA: {1:.5f}, Dec: {2:.5f})'.format(tab_sofia['name'][i].split()[1], tab_sofia['ra'][i], tab_sofia['dec'][i]), y=0.96, fontsize=16)
    plt.show()
    #plt.savefig(save_dir + 'D' + str(tab_sofia['id'][i]).zfill(4) + '_' + sname.split('_')[-1] + '_validation.png', bbox_inches='tight')

    # PV diagram

    if do_validation:
        # validate detections (True/False/Uncertain)

        ax5 = fig.add_subplot(236, projection=wcs_pv)
        #line_pixel_coords = wcs_pv.wcs_world2pix(0, freq_c*1e-6, 0)
        #ax5.imshow(pv_data, origin='lower', interpolation='nearest', cmap='viridis', aspect=pv_data.shape[1]/pv_data.shape[0])
        #ax5.axhline(y=line_pixel_coords[1], color='red', linestyle='--')
        #ax5.coords.grid(color='k', alpha=0.5, linestyle='dashed')
        #ax5.coords[0].set_axislabel('Angular Offset (arcsec)', fontsize=14)
        #ax5.coords[0].set_format_unit(u.arcsec)
        #ax5.coords[0].set_major_formatter('x')
        #ax5.coords[1].set_axislabel('Frequency (MHz)', fontsize=14)
        #ax5.annotate('PV map', (0.8, 0.93), size=12, xycoords='axes fraction', bbox=dict(boxstyle='round', fc='w', alpha=0.7))
        plt.show()
        
        qflag = input('Enter quality flag of this detection (t: True, f: False, u: Uncertain): ')
        if qflag == 't':
            ax5.text(0.25, 0.85, 'True', transform=ax5.transAxes, fontsize=40, color='w', alpha=0.7, ha='center', va='center', rotation='0')
            copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
            qa[i] = 1.0
        elif qflag == 'f':
            ax5.text(0.25, 0.85, 'False', transform=ax5.transAxes, fontsize=40, color='w', alpha=0.7, ha='center', va='center', rotation='0')
            copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
            qa[i] = 0.0
        elif qflag == 'u':
            ax5.text(0.35, 0.9, 'Uncertain', transform=ax5.transAxes, fontsize=30, color='w', alpha=0.7, ha='center', va='center', rotation='0')
            copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
            qa[i] = 2.0
        elif qflag == 'd':
            ax5.text(0.35, 0.9, 'Uncertain', transform=ax5.transAxes, fontsize=30, color='w', alpha=0.7, ha='center', va='center', rotation='0')
            copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
            qa[i] = 3.0
        else:
            qflag = input('Invalid quality flag. Please enter quality flag of this detection (t: True, f: False, u: Uncertain): ')
            if qflag == 't':
                ax5.text(0.25, 0.85, 'True', transform=ax5.transAxes, fontsize=40, color='w', alpha=0.7, ha='center', va='center', rotation='0')
                copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
                qa[i] = 1.0
            elif qflag == 'f':
                ax5.text(0.25, 0.85, 'False', transform=ax5.transAxes, fontsize=40, color='w', alpha=0.7, ha='center', va='center', rotation='0')
                copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
                qa[i] = 0.0
            elif qflag == 'u':
                ax5.text(0.35, 0.9, 'Uncertain', transform=ax5.transAxes, fontsize=30, color='w', alpha=0.7, ha='center', va='center', rotation='0')
                copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
                qa[i] = 2.0
            elif qflag == 'd':
                ax5.text(0.35, 0.9, 'Uncertain', transform=ax5.transAxes, fontsize=30, color='w', alpha=0.7, ha='center', va='center', rotation='0')
                copy_data(dir_cubelets, save_dir, sname, tab_sofia['name'][i], qflag)
                qa[i] = 3.0
            else:
                sys.exit(1)
        plt.savefig(save_dir + '_'.join(tab_sofia['name'][i].split()) + '_validation_' + qflag.upper() + '.png', bbox_inches='tight')

    else:
        
        ax5 = fig.add_subplot(236, projection=wcs_pv)
        line_pixel_coords = wcs_pv.wcs_world2pix(0, freq_c*1e-6, 0)
        ax5.imshow(pv_data, origin='lower', interpolation='nearest', cmap='viridis', aspect=pv_data.shape[1]/pv_data.shape[0])
        ax5.axhline(y=line_pixel_coords[1], color='red', linestyle='--')
        ax5.coords.grid(color='k', alpha=0.5, linestyle='dashed')
        ax5.coords[0].set_axislabel('Angular Offset (arcsec)', fontsize=14)
        ax5.coords[0].set_format_unit(u.arcsec)
        ax5.coords[0].set_major_formatter('x')
        ax5.coords[1].set_axislabel('Frequency (MHz)', fontsize=14)
        ax5.annotate('PV map', (0.8, 0.93), size=12, xycoords='axes fraction', bbox=dict(boxstyle='round', fc='w', alpha=0.7))
        
        plt.savefig(save_dir + '_'.join(tab_sofia['name'][i].split()) + '.png', bbox_inches='tight')


# Update and write the SoFiA catalogue and table with detection quality flags
# 0: false, 1: true, 2: uncertain, 3: duplicate
if update_cat:
    # Add quality flag to the SoFiA catalogue and table
    cat_sofia.add_column(col=qa, name='qa')
    cat_sofia.add_column(col=nCrossMat, name='N_match')

    tab_sofia.add_column(col=qa, name='qa')
    tab_sofia.add_column(col=nCrossMat, name='N_match')


    vocat = from_table(cat_sofia)
    vocat.to_xml(outname+'.xml')
    cat_sofia.write(outname+'.csv', format='ascii.csv', overwrite=True)

    # Write CASA CRTF file
    symbols = {'cross':'x', 'circle':'o', 'square':'s'}
    colors = ['red', 'green', 'yellow']
    #id_source = tab_sofia['id']
    ra = tab_sofia['ra']
    dec = tab_sofia['dec']
    qa = tab_sofia['qa']

    if do_CASA_region_file:
        with open(outname + '.crtf', 'w') as outfile:
            print('#CRTFv0', end='\n', file=outfile)

            for i in range(len(ra)):
                if qa[i] == 0.0:
                    print('symbol[['+str(ra[i])+'deg, '+str(dec[i])+'deg], '+symbols['cross']+'], coord=J2000, color='+colors[0]+', symsize=1, label="' + str(id_source[i]) + '", labelpos=bottom, labelcolor=' + colors[0], end='\n', file=outfile)

                elif qa[i] == 1.0:
                    print('symbol[['+str(ra[i])+'deg, '+str(dec[i])+'deg], '+symbols['circle']+'], coord=J2000, color='+colors[1]+', symsize=1, label="' + str(id_source[i]) + '", labelpos=bottom, labelcolor=' + colors[1], end='\n', file=outfile)

                elif qa[i] == 2.0:
                    print('symbol[['+str(ra[i])+'deg, '+str(dec[i])+'deg], '+symbols['square']+'], coord=J2000, color='+colors[2]+', symsize=1, label="' + str(id_source[i]) + '", labelpos=bottom, labelcolor=' + colors[2], end='\n', file=outfile)

                elif qa[i] == 3.0:
                    print('symbol[['+str(ra[i])+'deg, '+str(dec[i])+'deg], '+symbols['square']+'], coord=J2000, color='+colors[2]+', symsize=1, label="' + str(id_source[i]) + '", labelpos=bottom, labelcolor=' + colors[2], end='\n', file=outfile)


# Write the SoFiA table in latex format for publication
if write_latex_table:
    #tab_sofia.write('dingo_detection_table_final_v2.tex', format='ascii.latex', overwrite=True)
    tab_sofia.write(outname + '.txt', format='ascii.fixed_width', overwrite=True, delimiter='\t')
