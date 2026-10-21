"""Detailed-balance limits beyond a single junction + silicon reference values.
tandem_limit(): ideal two-terminal (series, current-matched) tandem, AM1.5G, 1 sun, no radiative coupling."""
import numpy as np
from numpy import trapezoid
import physics_checks as pc

SI_EG = 1.12            # eV, crystalline silicon
SI_PRACTICAL = 29.0     # % practical limit, wafers 40-500 um (Kowalczewski & Andreani, arXiv:1505.03985: "close to 29%")

def _j0(eg_J, T=298.15):
    e = np.linspace(eg_J, eg_J + 100 * pc.KB * T, 20000)
    return pc.Q * (2 * np.pi / (pc.H**3 * pc.C**2)) * trapezoid(e**2 / np.expm1(e / (pc.KB * T)), e)

def jsc_limit(eg_eV):
    """Photon-limited Jsc in mA/cm2 for a single absorber."""
    m = pc._E_J >= eg_eV * pc.Q
    return float(pc.Q * trapezoid(pc._PHI[m], pc._WL[m]) / 10)

def tandem_limit(e_top, e_bot, T=298.15):
    """Max PCE (%) of an ideal 2-terminal tandem with top bandgap e_top > bottom bandgap e_bot."""
    if e_top <= e_bot: return 0.0
    et, eb = e_top * pc.Q, e_bot * pc.Q
    m_top = pc._E_J >= et; m_bot = (pc._E_J >= eb) & (pc._E_J < et)
    jt = pc.Q * trapezoid(pc._PHI[m_top], pc._WL[m_top]); jb = pc.Q * trapezoid(pc._PHI[m_bot], pc._WL[m_bot])
    j0t, j0b = _j0(et, T), _j0(eb, T); kT = pc.KB * T / pc.Q
    J = np.linspace(1e-6, min(jt, jb) * 0.99999, 4000)
    v = kT * np.log((jt - J) / j0t + 1) + kT * np.log((jb - J) / j0b + 1)
    return float(100 * np.max(J * v) / pc._PIN)

def best_tandem(e_bot):
    """Best top-cell bandgap for a given bottom bandgap and its limit."""
    g = np.arange(e_bot + 0.2, 2.6, 0.02)
    vals = np.array([tandem_limit(x, e_bot) for x in g]); i = int(vals.argmax())
    return round(float(g[i]), 2), float(vals[i])

if __name__ == "__main__":
    print("Si SQ:", round(pc.sq_limit(SI_EG), 2), "| Jsc limit Si:", round(jsc_limit(SI_EG), 1), "mA/cm2")
    print("tandem 1.68/1.12:", round(tandem_limit(1.68, 1.12), 1), "| best top for Si:", best_tandem(1.12))
    print("tandem 1.6/0.95:", round(tandem_limit(1.6, 0.95), 1))
