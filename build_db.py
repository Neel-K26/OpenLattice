"""Build lattice.duckdb from the Perovskite Database CSV with physics-consistency flags.
Usage: python build_db.py <csv>"""
import sys, numpy as np, pandas as pd, duckdb
from numpy import trapezoid
import physics_checks as pc
src = sys.argv[1]
r = pd.read_csv(src, low_memory=False)
num = lambda c: pd.to_numeric(r[c], errors="coerce")
d = pd.DataFrame({
 "doi": r["Ref_DOI_number"], "year": pd.to_datetime(r["Ref_publication_date"], errors="coerce").dt.year,
 "arch": r["Cell_architecture"], "composition": r["Perovskite_composition_long_form"],
 "etl": r["ETL_stack_sequence"], "htl": r["HTL_stack_sequence"], "deposition": r["Perovskite_deposition_procedure"],
 "eg": num("Perovskite_band_gap"), "voc": num("JV_default_Voc"), "jsc": num("JV_default_Jsc"),
 "ff": num("JV_default_FF"), "pce": num("JV_default_PCE"), "t80_h": num("Stability_PCE_T80"),
 "light_mw": num("JV_light_intensity"), "spectra": r["JV_light_spectra"]})
# Standard test condition = ~1 sun (90-110 mW/cm2) and not indoor/monochromatic/LED/outdoor spectra.
# Cells measured under other light (e.g. 1000 lux indoor, 0.27 mW/cm2) cannot be compared with the 1-sun Shockley-Queisser limit.
nonstd_spec = d["spectra"].astype(str).str.lower().str.contains("indoor|mono|led|yellow|outdoor|ligth")
d["std_illum"] = d.light_mw.between(90, 110) & ~nonstd_spec
grid = np.round(np.arange(0.8, 3.51, 0.01), 2)
PL = np.array([pc.sq_limit(g) for g in grid])
def jl(eg):
    m = (pc._E_J/pc.Q) >= eg
    return pc.Q*trapezoid(pc._PHI[m], pc._WL[m])/10
JL = np.array([jl(g) for g in grid])
ok = d.eg.between(0.8, 3.5)
d["sq_pce_limit"] = np.where(ok, np.interp(d.eg, grid, PL), np.nan)
d["jsc_limit"] = np.where(ok, np.interp(d.eg, grid, JL), np.nan)
tandem = d.arch.astype(str).str.contains("tandem|multi", case=False)
full = ok & (d.pce > 1) & ~tandem & d.std_illum
d["bad_voc"] = full & (d.voc > d.eg)
d["bad_jsc"] = full & (d.jsc > d.jsc_limit*1.02)
d["bad_pce"] = full & (d.pce > d.sq_pce_limit + 0.5)
d["bad_ff"]  = full & (d.ff > 0.9)
d["bad_math"] = full & d.voc.notna() & d.jsc.notna() & d.ff.notna() & ((d.voc*d.jsc*d.ff/d.pce - 1).abs() > 0.10)
d["bad_illum"] = ~d.std_illum
d["any_bad"] = d[["bad_voc","bad_jsc","bad_pce","bad_ff","bad_math","bad_illum"]].any(axis=1)  # excluded from cells_clean
con = duckdb.connect("lattice.duckdb")
con.execute("DROP TABLE IF EXISTS cells"); con.register("d", d); con.execute("CREATE TABLE cells AS SELECT * FROM d")
con.execute("CREATE OR REPLACE VIEW cells_clean AS SELECT * FROM cells WHERE NOT any_bad")
print(con.execute("SELECT count(*), sum(any_bad::INT), count(DISTINCT doi), sum(bad_illum::INT), sum((any_bad AND std_illum)::INT) FROM cells").fetchall())
