""" Methods related to fussing with a catalog"""
from astropy.table.table import QTable
import numpy as np

from astropy.coordinates import SkyCoord
from astropy.cosmology import Planck18 as cosmo
from astropy.table import Table, hstack, vstack, setdiff, join
from astropy import units
from frb.galaxies.defs import valid_filters
import warnings

from IPython import embed


def clean_heasarc(catalog):
    """
    Insure RA/DEC are ra/dec in the Table

    Table is modified in place

    Args:
        catalog (astropy.table.Table): Catalog generated by astroquery

    """
    # RA/DEC
    catalog.rename_column("RA", "ra")
    catalog.rename_column("DEC", "dec")
    for key in ['ra', 'dec']:
        catalog[key].unit = units.deg


def clean_cat(catalog, pdict, fill_mask=None):
    """
    Convert table column names intrinsic to the slurped
    catalog with the FRB survey desired values

    Args:
        catalog (astropy.table.Table): Catalog generated by astroquery
        pdict (dict):  Defines the original key and desired key
        fill_mask (int or float, optional):  Fill masked items with this value

    Returns:
        astropy.table.Table:  modified catalog

    """
    for key,value in pdict.items():
        if value in catalog.keys():
            catalog.rename_column(value, key)
    # Mask
    if fill_mask is not None:
        if catalog.mask is not None:
            catalog = catalog.filled(fill_mask)
    return catalog


def sort_by_separation(catalog, coord, radec=('ra','dec'), add_sep=True):
    """
    Sort an input catalog by separation from input coordinate

    Args:
        catalog (astropy.table.Table):  Table of sources
        coord (astropy.coordinates.SkyCoord): Reference coordinate for sorting
        radec (tuple): Defines catalog columns holding RA, DEC (in deg)
        add_sep (bool, optional): Add a 'separation' column with units of arcmin

    Returns:
        astropy.table.Table: Sorted catalog

    """
    # Check
    for key in radec:
        if key not in catalog.keys():
            print("RA/DEC key: {:s} not in your Table".format(key))
            raise IOError("Try again..")
    # Grab coords
    cat_coords = SkyCoord(ra=catalog[radec[0]].data,
                          dec=catalog[radec[1]].data, unit='deg')

    # Separations
    seps = coord.separation(cat_coords)
    isrt = np.argsort(seps)
    # Add?
    if add_sep:
        catalog['separation'] = seps.to('arcmin')
    # Sort
    srt_catalog = catalog[isrt]
    # Return
    return srt_catalog


def match_ids(IDs, match_IDs, require_in_match=True):
    """ Match input IDs to another array of IDs (usually in a table)
    Return the rows aligned with input IDs

    Args:
        IDs (ndarray): ID values to match
        match_IDs (ndarray):  ID values to match to
        require_in_match (bool, optional): Require that each of the
          input IDs occurs within the match_IDs

    Returns:
        ndarray: Rows in match_IDs that match to IDs, aligned -1 if there is no match

    """
    rows = -1 * np.ones_like(IDs).astype(int)
    # Find which IDs are in match_IDs
    in_match = np.in1d(IDs, match_IDs)
    if require_in_match:
        if np.sum(~in_match) > 0:
            raise IOError("qcat.match_ids: One or more input IDs not in match_IDs")
    rows[~in_match] = -1
    #
    IDs_inmatch = IDs[in_match]
    # Find indices of input IDs in meta table -- first instance in meta only!
    xsorted = np.argsort(match_IDs)
    ypos = np.searchsorted(match_IDs, IDs_inmatch, sorter=xsorted)
    indices = xsorted[ypos]
    rows[in_match] = indices
    return rows


def summarize_catalog(frbc, catalog, summary_radius, photom_column, magnitude):
    """
    Generate simple text describing the sources from
    an input catalog within a given radius

    Args:
        frbc: FRB Candidate object
        catalog (astropy.table.Table): Catalog table
        summary_radius (Angle):  Radius to summarize on
        photom_column (str): Column specifying which flux to work on
        magnitude (bool): Is the flux a magnitude?

    Returns:
        list: List of comments on the catalog

    """
    # Init
    summary_list = []
    coords = SkyCoord(ra=catalog['ra'], dec=catalog['dec'], unit='deg')
    # Find all within the summary radius
    seps = frbc['coord'].separation(coords)
    in_radius = seps < summary_radius
    # Start summarizing
    summary_list += ['{:s}: There are {:d} source(s) within {:0.1f} arcsec'.format(
        catalog.meta['survey'], np.sum(in_radius), summary_radius.to('arcsec').value)]
    # If any found
    if np.any(in_radius):
        # Brightest
        if magnitude:
            brightest = np.argmin(catalog[photom_column][in_radius])
        else:
            brightest = np.argmax(catalog[photom_column][in_radius])
        summary_list += ['{:s}: The brightest source has {:s} of {:0.2f}'.format(
            catalog.meta['survey'], photom_column,
            catalog[photom_column][in_radius][brightest])]
        # Closest
        closest = np.argmin(seps[in_radius])
        summary_list += ['{:s}: The closest source is at separation {:0.2f} arcsec and has {:s} of {:0.2f}'.format(
            catalog.meta['survey'],
            seps[in_radius][closest].to('arcsec').value,
            photom_column, catalog[photom_column][in_radius][brightest])]
    # Return
    return summary_list


def xmatch_catalogs(cat1:Table, cat2:Table, skydist:units.Quantity = 5*units.arcsec,
                     RACol1:str = "ra", DecCol1:str = "dec",
                     RACol2:str = "ra", DecCol2:str = "dec",
                     return_match_idx:bool=False)->tuple:
    """
    Cross matches two astronomical catalogs and returns
    the matched tables.
    Args:
        cat1, cat2: astropy Tables
            Two tables with sky coordinates to be
            matched.
        skydist: astropy Quantity, optional
            Maximum separation for a valid match.
            5 arcsec by default.
        RACol1, RACol2: str, optional
            Names of columns in cat1 and cat2
            respectively that contain RA in degrees.
        DecCol1, DecCol2: str, optional
            Names of columns in cat1 and cat2
            respectively that contain Dec in degrees.
        return_match_idx: bool, optional
            Return the indices of the matched entries with
            with the distance instead?
    returns:
        match1, match2: astropy Table
            Tables of matched rows from cat1 and cat2.
        idx, d2d (if return_match_idx): ndarrays
            Indices of matched entries from table 2
            and an array of separations to go with.
    """
    assert isinstance(cat1, (Table, QTable))&isinstance(cat1, (Table, QTable)), "Catalogs must be astropy Table instances."
    assert (RACol1 in cat1.colnames)&(DecCol1 in cat1.colnames), " Could not find either {:s} or {:s} in cat1".format(RACol1, DecCol1)
    assert (RACol2 in cat2.colnames)&(DecCol2 in cat2.colnames), " Could not find either {:s} or {:s} in cat2".format(RACol2, DecCol2)
    # Get corodinates
    cat1_coord = SkyCoord(cat1[RACol1], cat1[DecCol1], unit = "deg")
    cat2_coord = SkyCoord(cat2[RACol2], cat2[DecCol2], unit = "deg")

    # Match 2D
    idx, d2d, _ = cat1_coord.match_to_catalog_sky(cat2_coord)

    # Get matched tables
    match1 = cat1[d2d < skydist]
    match2 = cat2[idx[d2d < skydist]]

    if return_match_idx:
        return idx, d2d
    else:
        return match1, match2


def _detect_mag_cols(photometry_table):
    """
    Searches the column names of a 
    photometry table for columns with mags.

    Args:
        photometry_table: astropy Table
            A table containing photometric
            data from a catlog.
    Returns:
        mag_colnames: list
            A list of column names with magnitudes
        mag_err_colnames: list
            A list of column names with errors
            in the magnitudes.
    """
    assert type(photometry_table)==Table, "Photometry table must be an astropy Table instance."
    allcols = photometry_table.colnames
    photom_cols = np.array(valid_filters)
    photom_errcols = np.array([filt+"_err" for filt in photom_cols])

    photom_cols = photom_cols[[elem in allcols for elem in photom_cols]]
    photom_errcols = photom_errcols[[elem in allcols for elem in photom_errcols]]
    
    return photom_cols.tolist(), photom_errcols.tolist()


def mag_from_flux(flux, flux_err=None):
    """
    Get the AB magnitude from a flux

    Parameters
    ----------
    flux : Quantity
        Flux
    flux_err : Quantity
        Error in flux (optional)

    Returns
    -------
    mag, mag_err : float, float
        AB magnitude and its error (if flux_err is given)
        AB magnitude and `None` (if flux_err is `None`)
    """
    # convert flux to Jansky
    flux_Jy = flux.to('Jy').value

    # get mag
    mag_AB = -2.5*np.log10(flux_Jy) + 8.9

    # get error
    if flux_err is not None:
        flux_Jy_err = flux_err.to('Jy').value
        err_mag2 = (-2.5/np.log(10.) / flux_Jy)**2 * flux_Jy_err**2
        err_mag = np.sqrt(err_mag2)
    else:
        err_mag = None
    return mag_AB, err_mag

def _mags_to_flux(mag, zpt_flux:units.Quantity=3630.7805*units.Jy, mag_err=None):
    """
    Convert a magnitude to mJy

    Args:
        mag (column): magnitude
        zpt_flux (Quantity, optional): Zero point flux for the magnitude.
            Assumes AB mags by default (i.e. zpt_flux = 3630.7805 Jy). 
        mag_err (float, optional): uncertainty in magnitude
    Returns:
        flux (column): flux in mJy
        flux_err (column): if mag_err is given, a corresponding
            flux_err is returned.
    """
    # Data validation -- check for Jy
    assert (type(zpt_flux) == units.Quantity)*(zpt_flux.decompose().unit == units.kg/units.s**2), "zpt_flux units should be Jy or with dimensions kg/s^2."

    # Prepare output column
    flux = mag.copy()

    # Convert fluxes
    badmags = mag<-10
    flux[badmags] = -99.
    flux[~badmags] = zpt_flux.value*10**(-mag[~badmags]/2.5)
    
    if mag_err is not None:
        flux_err = mag_err.copy()
        baderrs = (mag_err < 0) | (mag_err == 999.)
        flux_err[baderrs] = -99.
        flux_err[~baderrs] = flux[~baderrs]*(10**(mag_err[~baderrs]/2.5)-1)
        return flux, flux_err
    else:
        return flux    

def convert_mags_to_flux(photometry_table, fluxunits='mJy'):
    """
    Takes a table of photometric measurements
    in mags and converts it to flux units.

    ..todo..   NEED TO ADD DOCS ON VISTA, ETC..

    Args:
        photometry_table (astropy.table.Table):
            A table containing photometric
            data from a catlog.
        fluxunits (str, optional):
            Flux units to convert the magnitudes
            to, as parsed by astropy.units. Default is mJy.

    Returns:
        fluxtable: astropy Table
                `photometry_table` but the magnitudes
                are converted to fluxes.
                For upper limits, the flux is the 3sigma value and
                the error is set to -99.
    """
    fluxtable = photometry_table.copy()
    # Find columns with magnitudes based on filter names
    mag_cols, mag_errcols = _detect_mag_cols(fluxtable)
    convert = units.Jy.to(fluxunits)
    #If there's a "W" in the column name, it's from WISE
    # TODO -- We need to deal with this hack
    #wisecols = sorted([col for col in mag_cols if ("W" in col and 'WFC3' not in col)])
    #wise_errcols = sorted([col for col in mag_errcols if ("W" in col and 'WFC3' not in col)])

    #Similarly define vista cols
    vistacols = sorted([col for col in mag_cols if "VISTA" in col])
    vista_errcols = sorted([col for col in mag_errcols if "VISTA" in col])

    fnu0 = {#'WISE_W1':309.54,   # THIS IS NOW DONE IN the WISE survey class
            #'WISE_W2':171.787,
            #'WISE_W3':31.674,
            #'WISE_W4':8.363,
            'VISTA_Y':2087.32,
            'VISTA_J':1554.03,
            'VISTA_H':1030.40,
            'VISTA_Ks':674.83} #http://wise2.ipac.caltech.edu/docs/release/allsky/expsup/sec4_4h.html#conv2flux
                               #http://svo2.cab.inta-csic.es/svo/theory/fps3/index.php?mode=browse&gname=Paranal&gname2=VISTA
    #for mag,err in zip(wisecols+vistacols,wise_errcols+vista_errcols):
    for mag,err in zip(vistacols,vista_errcols):
        flux, flux_err = _mags_to_flux(photometry_table[mag], 
                                       fnu0[mag]*units.Jy, 
                                       photometry_table[err])
        badflux = flux == -99.
        fluxtable[mag][badflux] = flux[badflux]
        fluxtable[mag][~badflux] = flux[~badflux]*convert
        #if flux != -99.:
        #    fluxtable[mag] = flux*convert
        #else:
        #    fluxtable[mag] = flux
        baderr = flux_err == -99.0
        fluxtable[err][baderr] = flux_err[baderr]
        fluxtable[err][~baderr] = flux_err[~baderr]*convert
        #if flux_err != -99.:
        #    fluxtable[err] = flux_err*convert
        #else:
        #    fluxtable[err] = flux_err
        if "W" in mag and "WISE" not in mag and 'WFC3' not in mag:
            fluxtable.rename_column(mag,mag.replace("W","WISE"))
            fluxtable.rename_column(err,err.replace("W","WISE"))

    #For all other photometry:
    other_mags = np.setdiff1d(mag_cols, vistacols)
    other_errs = np.setdiff1d(mag_errcols, vista_errcols)

    for mag, err in zip(other_mags, other_errs):
        flux, flux_err = _mags_to_flux(photometry_table[mag], 
                                       mag_err=photometry_table[err])

        # Allow for bad flux values
        badflux = flux == -99.
        fluxtable[mag][badflux] = flux[badflux]
        fluxtable[mag][~badflux] = flux[~badflux]*convert

        # Allow for bad errors
        baderr = flux_err == -99.0
        fluxtable[err][baderr] = flux_err[baderr]
        fluxtable[err][~baderr] = flux_err[~baderr]*convert

        # Upper limits -- Record as 3sigma
        #   and set error to -99.
        uplimit = photometry_table[err] == 999.
        fluxtable[err][uplimit] = -99. #fluxtable[mag][uplimit] / 3.
        fluxtable[mag][uplimit] = fluxtable[mag][uplimit] 

    return fluxtable

def remove_duplicates(tab:Table, idcol:str)->Table:
    """
    In an astropy table if there are duplicate
    entries, remove the duplicates. Generally,
    these will be duplicate objects (i.e. multiple
    observations of same object ID or the same
    entry repeated multiple times from cross-matching.)

    Args:
        tab (Table): A table of entries.
        idcol (str): A column name that has unique ids
            for each table entry.
    Returns:
        unique_tab (Table): A table with only the unique ids.
    """
    unique_tab = tab.copy()
    assert isinstance(unique_tab, Table), "Please provide an astropy table."
    assert isinstance(idcol, str), "Please provide a valid column name."
    assert idcol in tab.colnames, "{} not a column in the given table".format(idcol)
    # Sort entries first.
    unique_tab.sort(idcol)
    # Get the duplicates.
    duplicate_ids = np.where(unique_tab[1:][idcol]==unique_tab[:-1][idcol])[0]+1
    unique_tab.remove_rows(duplicate_ids)
    return unique_tab
    
def xmatch_and_merge_cats(tab1:Table, tab2:Table, tol:units.Quantity=1*units.arcsec,
                        table_names:tuple=('1','2'), **kwargs)->Table:
    """
    Given two source catalogs, cross-match and merge them. This function 
    ensures there is a unique match between tables as opposed to the default join_skycoord
    behavior which matches multiple objects on the right table to
    a source on the left. The two tables must contain the columns 'ra' and 'dec' (case-sensitive).
    Args:
        tab1, tab2 (Table): Photometry catalogs. Must contain columns named
            ra and dec.
        tol (Quantity[Angle], optional): Maximum separation for cross-matching.
        table_names (tuple of str, optional): Names of the two tables for
            naming unique columns in the merged table.
        kwargs: Additional keyword arguments to be passed onto xmatch_catalogs
    Returns:
        merged_table (Table): Merged catalog.
    """
    if table_names is not None:
        assert len(table_names)==2, "Invalid number of table names for two tables."
        assert (type(table_names[0])==str)&(type(table_names[1])==str), "Table names should be strings."
    
    assert np.all(np.isin(['ra','dec'],tab1.colnames)), "Table 1 doesn't have column 'ra' and/or 'dec'."
    assert np.all(np.isin(['ra','dec'],tab2.colnames)), "Table 2 doesn't have column 'ra' and/or 'dec'."

    # Cross-match tables for tab1 INTERSECTION tab2.
    matched_tab1, matched_tab2 = xmatch_catalogs(tab1, tab2, tol, **kwargs)

    # tab1 INTERSECTION tab2
    inner_join = hstack([matched_tab1, matched_tab2],
                        table_names=table_names)
    # Remove unnecessary ra/dec columns and rename remaining coordinate
    # columns corectly. 
    tab1_coord_cols = ['ra_'+table_names[0],"dec_"+table_names[0]]
    tab2_coord_cols = ['ra_'+table_names[1],"dec_"+table_names[1]]


    inner_join.remove_columns(tab2_coord_cols)
    inner_join.rename_columns(tab1_coord_cols, ['ra', 'dec'])

    # Now get all objects that weren't matched.
    not_matched_tab1 = setdiff(tab1, matched_tab1)
    not_matched_tab2 = setdiff(tab2, matched_tab2)

    # (tab1 UNION tab2) - (tab1 INTERSECTION tab2)

    # Are there unmatched entries in both tables?
    if (len(not_matched_tab1)!=0)&(len(not_matched_tab2)!=0):
        outer_join = join(not_matched_tab1, not_matched_tab2,
                    keys=['ra','dec'], join_type='outer', table_names=table_names)
        merged = vstack([inner_join, outer_join]).filled(-999.)
    # Only table 1 has unmatched entries?
    elif (len(not_matched_tab1)!=0)&(len(not_matched_tab2)==0):
        merged = vstack([inner_join, not_matched_tab1])
    # Only table 2?
    elif (len(not_matched_tab1)==0)&(len(not_matched_tab2)!=0):
        merged = vstack([inner_join, not_matched_tab2])
    # Neither?
    else:
        merged = inner_join
    # Final cleanup. Just in case.
    weird_cols = np.isin(['ra_1','dec_1','ra_2','dec_2'],merged.colnames)
    if np.any(weird_cols):
        merged.remove_columns(np.array(['ra_1','dec_1','ra_2','dec_2'])[weird_cols])
    # Fill and return.
    return merged.filled(-999.)
    
    '''
    TODO: Write this function once CDS starts working again (through astroquery) 
    def xmatch_gaia(catalog,max_sep = 5*u.arcsec,racol='ra',deccol='dec'):
        """
        Cross match against Gaia DR2
        and return the cross matched table.
        Args:
            max_sep (Angle): maximum separation to be
                            considered a valid match.
        Returns:
            xmatch_tab (Table): a table with corss matched
                                entries.
        """
    ''' 