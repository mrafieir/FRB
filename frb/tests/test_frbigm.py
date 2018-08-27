# Module to run tests on FRB calculations using DLAs
from __future__ import print_function, absolute_import, division, unicode_literals

# TEST_UNICODE_LITERALS

import numpy as np
import pytest

from astropy import units as u

from frb import igm

def test_rhoMstar():
    rho_Mstar_full = igm.avg_rhoMstar(1., remnants=True)
    # Test
    assert rho_Mstar_full.unit == u.Msun/u.Mpc**3
    assert np.isclose(rho_Mstar_full.value, 4.65882439e+08)

def test_rhoISM():
    rhoISM = igm.avg_rhoISM(0.)
    # Test
    assert rhoISM.unit == u.Msun/u.Mpc**3
    assert np.isclose(rhoISM.value, 2.19389268e+08)

def test_igmDM():
    DM = igm.average_DM(1.)
    # Value and unit
    assert DM.unit == u.pc/u.cm**3
    assert np.isclose(DM.value, 1053.0827)
    # Cumulative
    DM_cum, zeval = igm.average_DM(1., cumul=True)
    assert DM == DM_cum[-1]
    # Cross through HeII reionization
    DM4 = igm.average_DM(4.)
    assert np.isclose(DM4.value, 3866.9971167)

