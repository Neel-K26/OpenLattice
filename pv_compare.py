"""Silicon vs perovskite comparison from the NREL research-cell record table + our perovskite database.
Usage: python pv_compare.py data/nrel_cells.xlsx   (optionally run after build_db.py so stability stats are included)
Outputs: compare.duckdb (tables nrel, tech_summary), pv_compare_summary.txt, pv_compare.png"""
import sys, json, os, numpy as np, pandas as pd, duckdb
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import physics_checks as pc, pv_limits as pl

src = sys.argv[1] if len(sys.argv) > 1 else "data/nrel_cells.xlsx"
d = pd.read_excel(src).iloc[:, :22]; d.columns = [str(c).strip() for c in d.columns]
num = lambda c: pd.to_numeric(d[c], errors="coerce")
n = pd.DataFrame({"id": d["Record Identifier"].astype(str), "year": num("Year"), "material_class": d["Eff. Chart Material Class"],
                  "cell_type": d["Eff. Chart Cell Type"], "group": d["Group(s)"], "pce": num("Combined efficiency (%)"),
                  "voc_raw": num("VOC (V)"), "jsc": num("Jsc (mA/cm2)"), "ff_raw": num("FF (%)"), "suns": num("Suns"), "area_cm2": num("Area (cm2)")})
n["voc"] = np.where(n.voc_raw > 5, n.voc_raw / 1000, n.voc_raw); n["voc_unit_fixed"] = n.voc_raw > 5          # mV entered as V
n["ff"] = np.where(n.ff_raw > 1.0, n.ff_raw / 100, n.ff_raw)                                                     # percent -> fraction
def tech(r):
    c, t = r.material_class, r.cell_type
    if c == "Crystalline Si Cells": return "c-Si (concentrator)" if "concentrator)" in t and "non" not in t else "c-Si"
    if t == "Perovskite cells": return "perovskite (single junction)"
    if t == "Perovskite/Si": return "perovskite/Si tandem"
    if t == "III-V/Si": return "III-V/Si tandem"
    return c
n["tech"] = n.apply(tech, axis=1)
# --- physics checks, applied where the bandgap is known and conditions are 1 sun ---
one = n.suns.fillna(1).between(0.99, 1.01)
si = (n.tech == "c-Si") & one
n["bad_voc"] = si & (n.voc > pl.SI_EG)
n["bad_jsc"] = si & (n.jsc > pl.jsc_limit(pl.SI_EG) * 1.02)
n["bad_pce"] = si & (n.pce > pc.sq_limit(pl.SI_EG) + 0.5)
n["bad_ff"] = one & (n.ff > 0.9) & n.tech.isin(["c-Si", "perovskite (single junction)"])
n["bad_math"] = one & n.voc.notna() & n.jsc.notna() & n.ff.notna() & n.pce.notna() & ((n.voc * n.jsc * n.ff / n.pce - 1).abs() > 0.05) & n.tech.isin(["c-Si", "perovskite (single junction)"]) & (n.area_cm2 > 0)
n["any_bad"] = n[["bad_voc", "bad_jsc", "bad_pce", "bad_ff", "bad_math"]].any(axis=1)
# --- technology summary ---
def best(mask):
    s = n[mask & n.pce.notna()].sort_values("pce", ascending=False).iloc[0]; return float(s.pce), int(s.year), str(s.group)
rows = []
bs, ys, gs = best((n.tech == "c-Si") & one & ~n.any_bad); sq_si = pc.sq_limit(pl.SI_EG)
rows.append(dict(tech="c-Si", best_pce=bs, year=ys, lab=gs, bandgap_ev="1.12", sq_limit=round(sq_si, 1), practical_limit=pl.SI_PRACTICAL, pct_of_sq=round(100 * bs / sq_si, 1), n_records=int((n.tech == "c-Si").sum())))
bp, yp, gp = best((n.tech == "perovskite (single junction)") & one)
lo, hi = pc.sq_limit(1.6), pc.sq_limit(1.5)
rows.append(dict(tech="perovskite (single junction)", best_pce=bp, year=yp, lab=gp, bandgap_ev="1.5-1.6 (assumed; table has no bandgap)", sq_limit=round((lo + hi) / 2, 1), practical_limit=None, pct_of_sq=round(100 * bp / ((lo + hi) / 2), 1), n_records=int((n.tech == "perovskite (single junction)").sum())))
bt, yt, gt = best((n.tech == "perovskite/Si tandem") & one); tl = pl.tandem_limit(1.68, 1.12)
rows.append(dict(tech="perovskite/Si tandem", best_pce=bt, year=yt, lab=gt, bandgap_ev="1.68 / 1.12 (assumed)", sq_limit=round(tl, 1), practical_limit=None, pct_of_sq=round(100 * bt / tl, 1), n_records=int((n.tech == "perovskite/Si tandem").sum())))
ts = pd.DataFrame(rows)
# --- stability evidence from our perovskite database, if built ---
stab = {}
if os.path.exists("lattice.duckdb"):
    c = duckdb.connect("lattice.duckdb", read_only=True)
    r = c.execute("select count(*), count(t80_h), median(t80_h), max(t80_h), sum((t80_h>=8760)::int) from cells_clean").fetchone()
    stab = dict(perovskite_records=int(r[0]), with_t80=int(r[1]), median_t80_h=float(r[2]), max_t80_h=float(r[3]), n_ge_1yr=int(r[4] or 0)); c.close()
if os.path.exists("compare.duckdb"): os.remove("compare.duckdb")
cc = duckdb.connect("compare.duckdb"); cc.register("n", n); cc.register("ts", ts)
cc.execute("create table nrel as select * from n"); cc.execute("create table tech_summary as select * from ts")
json.dump(dict(tech_summary=ts.to_dict("records"), stability=stab, si_practical_limit_note="about 29% for 40-500 um wafers (Kowalczewski & Andreani, arXiv:1505.03985)",
               si_warranty_note="commercial silicon modules typically carry 25-year or longer warranties (general industry knowledge, not from our data)"), open("compare_facts.json", "w"), indent=1, default=float)
L = ["== NREL record table ==", f"records: {len(n)} ({int(n.year.min())}-{int(n.year.max())}); c-Si {int((n.tech=='c-Si').sum())}, perovskite {int((n.tech=='perovskite (single junction)').sum())}, perovskite/Si {int((n.tech=='perovskite/Si tandem').sum())}",
     f"rows with Voc entered in mV (fixed): {int(n.voc_unit_fixed.sum())}", f"rows failing >=1 check (c-Si / perovskite, 1 sun): {int(n.any_bad.sum())}: " + ", ".join(f"{k}={int(n[k].sum())}" for k in ['bad_voc','bad_jsc','bad_pce','bad_ff','bad_math']),
     "", "== technology summary ==", ts[["tech", "best_pce", "year", "sq_limit", "pct_of_sq", "n_records"]].to_string(index=False),
     f"Silicon: SQ {sq_si:.1f}%, practical limit ~{pl.SI_PRACTICAL:.0f}%; best record {bs:.1f}% = {100*bs/pl.SI_PRACTICAL:.0f}% of the practical limit.",
     f"Ideal 2-terminal tandem limit for 1.68/1.12 eV: {tl:.1f}% (best top gap for silicon {pl.best_tandem(1.12)[0]} eV -> {pl.best_tandem(1.12)[1]:.1f}%)", "", "== stability evidence (perovskite database) ==", json.dumps(stab)]
open("pv_compare_summary.txt", "w").write("\n".join(L) + "\n"); print("\n".join(L))
# --- figure: record efficiency over time ---
BLUE, ORG, GRN, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#e6e5e1"
fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.4), dpi=150, gridspec_kw={"width_ratios": [1.3, 1]})
a = ax[0]
for t, col, lab in [("c-Si", BLUE, "crystalline silicon"), ("perovskite (single junction)", ORG, "perovskite"), ("perovskite/Si tandem", GRN, "perovskite/Si tandem")]:
    s = n[(n.tech == t) & one & n.pce.notna()].sort_values("year"); s = s.assign(run=s.pce.cummax()); y = s.groupby("year").run.max()
    a.step(y.index, y.values, where="post", color=col, lw=2, label=lab)
a.axhline(pl.SI_PRACTICAL, color=BLUE, ls=":", lw=1); a.text(1977, pl.SI_PRACTICAL + .4, "silicon practical limit ~29%", fontsize=8, color=MUTED)
a.axhline(tl, color=GRN, ls=":", lw=1); a.text(1977, tl + .4, f"ideal perovskite/Si tandem limit {tl:.0f}%", fontsize=8, color=MUTED)
a.set_xlabel("Year"); a.set_ylabel("Best certified efficiency so far (%)"); a.set_title("Record efficiency over time (NREL record table)", loc="left", fontsize=10); a.legend(frameon=False, fontsize=8, loc="lower center")
b = ax[1]; names = ["c-Si", "perovskite", "perovskite/Si\ntandem"]; vals = [100 * bs / sq_si, 100 * bp / ((lo + hi) / 2), 100 * bt / tl]
labs = [f"{bs:.1f}% of {sq_si:.1f}% (SQ)", f"{bp:.1f}% of {(lo+hi)/2:.1f}% (SQ)", f"{bt:.1f}% of {tl:.1f}% (ideal 2-J)"]
b.barh(names, vals, color=[BLUE, ORG, GRN], height=.55); b.invert_yaxis(); b.set_xlim(0, 125)
for i, (v, t) in enumerate(zip(vals, labs)): b.text(v + 1.5, i, f"{v:.0f}%   {t}", va="center", fontsize=8, color=INK)
b.set_xlabel("Best record as % of its physical limit"); b.set_title("How close is each technology to its limit?", loc="left", fontsize=10)
for x in ax:
    x.grid(color=GRID, lw=.6); x.set_axisbelow(True)
    for s_ in ("top", "right"): x.spines[s_].set_visible(False)
fig.tight_layout(); fig.savefig("pv_compare.png")
