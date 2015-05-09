"""
#;+ 
#; NAME:
#; utils
#;    Version 1.0
#;
#; PURPOSE:
#;    Module for spectral utilities
#;       Primarily overloads of Spectrum1D
#;   07-Sep-2014 by JXP
#;-
#;------------------------------------------------------------------------------
"""
from __future__ import print_function, absolute_import, division, unicode_literals

import numpy as np
import os
import astropy as apy

from astropy import units as u
from astropy import constants as const
from astropy.io import fits 

from specutils import Spectrum1D
from specutils.wcs import BaseSpectrum1DWCS, Spectrum1DLookupWCS
from specutils.wcs.specwcs import Spectrum1DPolynomialWCS

from xastropy.xutils import xdebug as xdb

# Child Class of specutils/Spectrum1D 
#    Generated by JXP to add functionality before it gets ingested in the specutils distribution
class XSpectrum1D(Spectrum1D):

    #### ###############################
    #  Instantiate from Spectrum1D [best to avoid!]
    @classmethod
    def from_spec1d(cls, spec1d):
            
        # Giddy up
        return cls(flux=spec1d.flux, wcs=spec1d.wcs, unit=spec1d.unit,
                   uncertainty=spec1d.uncertainty, mask=spec1d.mask, meta=spec1d.meta)
        

    #### ###############################
    #  Grabs spectrum pixels in a velocity window
    def pix_minmax(self, *args):
        """Pixels in velocity range

        Parameters
        ----------
        Option 1: wvmnx
          wvmnx: Tuple of 2 floats
            wvmin, wvmax in spectral units

        Option 2: zabs, wrest, vmnx 
          zabs: Absorption redshift
          wrest: Rest wavelength  (with Units!)
          vmnx: Tuple of 2 floats
            vmin, vmax in km/s
    
        Returns:
        pix: array
          Integer list of pixels
        """
        if len(args) == 1: # Option 1
            wvmnx = args[0]
        elif len(args) == 3: # Option 2
            from astropy import constants as const
            # args = zabs, wrest, vmnx
            wvmnx = (args[0]+1) * (args[1] + (args[1] * args[2] / const.c.to('km/s')) )
            wvmnx.to(u.AA)

        # Locate the values
        pixmin = np.argmin( np.fabs( self.dispersion-wvmnx[0] ) )
        pixmax = np.argmin( np.fabs( self.dispersion-wvmnx[1] ) )

        gdpix = np.arange(pixmin,pixmax+1)

        # Fill + Return
        self.sub_pix = gdpix
        return gdpix, wvmnx, (pixmin, pixmax)

    #### ###############################
    #  Box car smooth
    def box_smooth(self, nbox, preserve=False):
        """ Box car smooth spectrum and return a new one
        Is a simple wrapper to the rebin routine

        Parameters
        ----------
        nbox: integer
          Number of pixels to smooth over
        preserve: bool (False) 
          Keep the new spectrum at the same number of pixels as original
        Returns:
          XSpectrum1D of the smoothed spectrum
        """
        from xastropy.xutils import arrays as xxa
        if preserve:
            from astropy.convolution import convolve, Box1DKernel
            new_fx = convolve(self.flux, Box1DKernel(nbox))
            new_sig = convolve(self.sig, Box1DKernel(nbox))
            new_wv = self.dispersion
        else:
            # Truncate arrays as need be
            npix = len(self.flux)
            new_npix = npix // nbox # New division
            orig_pix = np.arange( new_npix * nbox )

            # Rebin (mean)
            new_wv = xxa.scipy_rebin( self.dispersion[orig_pix], new_npix )
            new_fx = xxa.scipy_rebin( self.flux[orig_pix], new_npix )
            new_sig = xxa.scipy_rebin( self.sig[orig_pix], new_npix ) / np.sqrt(nbox)

        # Return
        return XSpectrum1D.from_array(new_wv, new_fx,
                                      uncertainty=apy.nddata.StdDevUncertainty(new_sig))

    # Quick plot
    def plot(self):
        ''' Plot the spectrum 
        Parameters
        ----------
        '''
        xdb.xplot(self.dispersion, self.flux, self.sig)

    # Velo array
    def relative_vel(self, wv_obs):
        ''' Return a velocity array relative to an input wavelength
        Should consider adding a velocity array to this Class, i.e. self.velo

        Parameters
        ----------
        wv_obs : float
          Wavelength to set the zero of the velocity array.
          Often (1+z)*wrest
        '''
        return  (self.dispersion-wv_obs) * const.c.to('km/s')/wv_obs

    # Write to fits
    def write_to_fits(self, outfil, clobber=True):
        ''' Write to a FITS file
        Should generate a separate code to make a Binary FITS table format

        Parameters
        ----------
        outfil: String
          Name of the FITS file
        clobber: bool (True)
          Clobber existing file?
        '''
        # TODO
        #  1. Add unit support for wavelength arrays
    
        from specutils.io import write_fits as sui_wf
        prihdu = sui_wf._make_hdu(self.data)  # Not for binary table format
        multi = 0 #  Multi-extension?

        # Type
        if type(self.wcs) is Spectrum1DPolynomialWCS:  # CRVAL1, etc. WCS
            # WCS
            wcs = self.wcs
            wcs.write_fits_header(prihdu.header)
            # Error array?
            if self.sig is not None:
                sighdu = fits.ImageHDU(self.sig)
                hdu = fits.HDUList([prihdu, sighdu])
                multi=1
            else:
                hdu = prihdu
            
        elif type(self.wcs) is Spectrum1DLookupWCS: # Wavelengths as an array (without units for now)
            # Add sig, wavelength to HDU
            sighdu = fits.ImageHDU(self.sig)
            wvhdu = fits.ImageHDU(self.dispersion.value)
            hdu = fits.HDUList([prihdu, sighdu, wvhdu])
            multi=1
        else:
            raise ValueError('write_to_fits: Not ready for this type of spectrum wavelengths')

        # Deal with header
        if hasattr(self,'head'):
            hdukeys = prihdu.header.keys()
            # Append ones to avoid
            hdukeys = hdukeys + ['BUNIT','COMMENT','', 'NAXIS2']
            for key in self.head.keys():
                # Use new ones
                if key in hdukeys:
                    continue
                # Update unused ones
                try:
                    prihdu.header[key] = self.head[key]
                except ValueError:
                    xdb.set_trace()

        # Write
        hdu.writeto(outfil, clobber=clobber)
        print('Wrote spectrum to {:s}'.format(outfil))

    
# Quick plot
def bspline_stack(spectra):
    ''' "Stack" a set of spectra with a bspline algorithm
    Might be useful for coadding

    Parameters:
    -----------
    spectra: List of Spectrum1D

    Returns:
    -------
    bspline
    '''

# ################
if __name__ == "__main__":

    flg_test = 0 
    #flg_test += 2**0  # Test write (simple)
    #flg_test += 2**1  # Test write with 3 arrays
    flg_test += 2**2  # Test boxcar

    from xastropy.spec import readwrite as xsr

    if (flg_test % 2**1) >= 2**0:
        # Standard log-linear read + write (MagE)
        fil = '~/PROGETTI/LLSZ3/data/normalize/UM669_nF.fits'
        myspec = xsr.readspec(fil)
        # Write
        myspec.write_to_fits('tmp.fits')

    if (flg_test % 2**2) >= 2**1:
        # Now 2D
        fil = '/Users/xavier/Dropbox/QSOPairs/data/LRIS_redux/SDSSJ231254.65-025403.1_b400_F.fits.gz'
        myspec = xsr.readspec(fil)
        myspec.write_to_fits('tmp.fits')
    
    if (flg_test % 2**3) >= 2**2: # Boxcar
        fil = '~/PROGETTI/LLSZ3/data/normalize/UM669_nF.fits'
        myspec = xsr.readspec(fil)
        newspec = myspec.box_smooth(3)
        # 
        newspec2 = myspec.box_smooth(3, preserve=True)
        xdb.xplot(myspec.dispersion, myspec.flux, newspec2.flux)
    
