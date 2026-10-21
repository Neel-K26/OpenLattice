"""OpenLattice physics gate: Shockley-Queisser limit and theoretical battery capacity.

Usage:
    from physics_checks import sq_limit, check_solar, theoretical_capacity_mAh_g, check_capacity
Dependencies: numpy, scipy, pvlib (only for its bundled ASTM G173 spectrum file).
"""
import os
import numpy as np
from scipy.integrate import trapezoid

# ---- constants (SI) ----
Q = 1.602176634e-19      # C
H = 6.62607015e-34       # J s
C = 2.99792458e8         # m/s
KB = 1.380649e-23        # J/K
F = 96485.33212          # C/mol

# ---- AM1.5G spectrum (ASTM G173-03 global tilt), bundled with pvlib ----
def _load_am15g():
    import pvlib
    path = os.path.join(os.path.dirname(pvlib.__file__), "data", "ASTMG173.csv")
    raw = np.genfromtxt(path, delimiter=",", skip_header=2)
    wl_nm, irr = raw[:, 0], raw[:, 2]        # nm, W m^-2 nm^-1 (global tilt)
    return wl_nm, irr

_WL, _IRR = _load_am15g()
_E_J = H * C / (_WL * 1e-9)                          # photon energy, J
_PHI = _IRR * (_WL * 1e-9) / (H * C)                 # photons m^-2 s^-1 nm^-1
_PIN = trapezoid(_IRR, _WL)                           # W m^-2 (~1000)

def sq_limit(bandgap_eV, T=298.15):
    """Detailed-balance (Shockley-Queisser) max PCE (%) under AM1.5G at 1 sun for one bandgap."""
    eg = bandgap_eV * Q
    mask = _E_J >= eg
    if mask.sum() < 2:
        return 0.0
    # short-circuit current density (A m^-2): every above-gap photon gives one electron
    jsc = Q * trapezoid(_PHI[mask], _WL[mask])
    # radiative dark current: blackbody emission above gap into half-space
    e = np.linspace(eg, eg + 100 * KB * T, 20000)
    j0 = Q * (2 * np.pi / (H**3 * C**2)) * trapezoid(e**2 / np.expm1(e / (KB * T)), e)
    voc = KB * T / Q * np.log(jsc / j0 + 1)
    v = np.linspace(0, voc, 4000)
    j = jsc - j0 * np.expm1(Q * v / (KB * T))
    return float(100 * np.max(v * j) / _PIN)

def check_solar(pce_pct, bandgap_eV, tol_pct_abs=0.5):
    """Return (ok, message). Flags a reported single-junction 1-sun AM1.5G PCE above the SQ limit."""
    lim = sq_limit(bandgap_eV)
    if pce_pct > lim + tol_pct_abs:
        return False, f"PCE {pce_pct:.1f}% exceeds SQ limit {lim:.1f}% at Eg={bandgap_eV} eV (check units, tandem, concentrator, or extraction error)"
    return True, f"OK: PCE {pce_pct:.1f}% <= SQ limit {lim:.1f}% at Eg={bandgap_eV} eV ({100*pce_pct/lim:.0f}% of limit)"

# ---- batteries: Faraday's law ----
ATOMIC_MASS = {"H":1.008,"Li":6.94,"C":12.011,"O":15.999,"F":18.998,"Na":22.990,"Mg":24.305,"Al":26.982,
               "Si":28.086,"P":30.974,"S":32.06,"K":39.098,"Ca":40.078,"Ti":47.867,"V":50.942,"Mn":54.938,
               "Fe":55.845,"Co":58.933,"Ni":58.693,"Cu":63.546,"Zn":65.38,"Sn":118.71}

def molar_mass(formula_dict):
    return sum(ATOMIC_MASS[el] * n for el, n in formula_dict.items())

def theoretical_capacity_mAh_g(formula_dict, electrons_transferred):
    """Q = n F / (3.6 M) in mAh/g, n = electrons per formula unit that the host can exchange."""
    return electrons_transferred * F / (3.6 * molar_mass(formula_dict))

def check_capacity(reported_mAh_g, formula_dict, electrons_transferred, tol_pct=2.0):
    q = theoretical_capacity_mAh_g(formula_dict, electrons_transferred)
    if reported_mAh_g > q * (1 + tol_pct / 100):
        return False, f"Reported {reported_mAh_g:.0f} mAh/g exceeds theoretical {q:.0f} mAh/g (check mass basis: active material vs electrode, or conversion/alloy chemistry)"
    return True, f"OK: {reported_mAh_g:.0f} mAh/g <= theoretical {q:.0f} mAh/g ({100*reported_mAh_g/q:.0f}%)"

if __name__ == "__main__":
    for eg in (1.12, 1.34, 1.55, 1.77, 2.0):
        print(f"SQ limit at {eg} eV: {sq_limit(eg):.2f}%")
    print(check_solar(26.0, 1.55))
    print(check_solar(35.0, 1.55))
    print("LiFePO4 (n=1):", round(theoretical_capacity_mAh_g({"Li":1,"Fe":1,"P":1,"O":4},1),1), "mAh/g")
    print("graphite LiC6 (n=1, C6):", round(theoretical_capacity_mAh_g({"C":6},1),1), "mAh/g")
    print("LiCoO2 (n=1):", round(theoretical_capacity_mAh_g({"Li":1,"Co":1,"O":2},1),1), "mAh/g")
    print(check_capacity(200, {"Li":1,"Fe":1,"P":1,"O":4}, 1))
