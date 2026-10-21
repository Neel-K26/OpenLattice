"""Lead-halide spotlight + silicon reference. Reads lattice.duckdb; does NOT change the audit flags or the evaluation.
Usage: python spotlight.py   -> spotlight_summary.txt, spotlight.png
Reference bandgap ranges below are PROVISIONAL (to be confirmed by a domain expert)."""
import duckdb, numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import physics_checks as pc
BLUE, ORG, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e1"
con = duckdb.connect("lattice.duckdb", read_only=True)
REF = {"MAPbI3": (1.60, 1.50, 1.65), "FAPbI3": (1.48, 1.40, 1.55), "CsPbI3": (1.72, 1.65, 1.80)}  # typical, low, high (eV)
SI_EG = 1.12
lines = [f"Silicon reference: Eg {SI_EG} eV -> Shockley-Queisser limit {pc.sq_limit(SI_EG):.1f}% (this code, AM1.5G). The database contains no silicon or tandem cells."]
best = {}
for comp, (eg0, lo, hi) in REF.items():
    n, mx, med = con.execute("select count(*), max(pce), median(pce) from cells_clean where composition=? and pce>1", [comp]).fetchone()
    allr, out, dois = con.execute("select count(*), sum(((eg<? or eg>?))::int), count(distinct case when eg<? or eg>? then doi end) from cells where composition=? and std_illum and eg is not null", [lo, hi, lo, hi, comp]).fetchone()
    lim = pc.sq_limit(eg0); best[comp] = (eg0, mx, lim)
    lines.append(f"{comp}: {allr} 1-sun records; reported bandgap outside {lo}-{hi} eV in {out} ({100*out/allr:.1f}%) from {dois} papers. "
                 f"Best physics-consistent PCE {mx:.2f}% = {100*mx/lim:.0f}% of the SQ limit ({lim:.1f}% at {eg0} eV); median {med:.1f}%.")
tot = con.execute("select count(*) from cells where composition in ('MAPbI3','MAPb1.0I3','FAPbI3','CsPbI3')").fetchone()[0]
lines.append(f"Pure lead-iodide compositions (MAPbI3, MAPb1.0I3, FAPbI3, CsPbI3) are {tot:,} of {con.execute('select count(*) from cells').fetchone()[0]:,} records.")
open("spotlight_summary.txt", "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
fig, ax = plt.subplots(1, 2, figsize=(11.5, 4.4), dpi=150)
a = ax[0]; g = np.arange(0.95, 2.05, 0.01)
a.plot(g, [pc.sq_limit(x) for x in g], color=INK, lw=1.6, label="Shockley–Queisser limit")
a.scatter([SI_EG], [pc.sq_limit(SI_EG)], marker="D", s=50, color=MUTED, zorder=3); a.annotate("silicon (1.12 eV)\nSQ limit", (SI_EG, pc.sq_limit(SI_EG)), xytext=(8, 6), textcoords="offset points", fontsize=8, color=MUTED)
for comp, (eg0, mx, lim) in best.items():
    a.scatter([eg0], [mx], s=55, color=BLUE, zorder=3, edgecolor="white")
    a.annotate(f"{comp}\n{mx:.1f}% ({100*mx/lim:.0f}% of limit)", (eg0, mx), xytext=((-92, 4) if comp == "FAPbI3" else (6, -22)), textcoords="offset points", fontsize=8, color=INK)
a.set_xlim(0.95, 2.0); a.set_ylim(10, 36); a.set_xlabel("Bandgap (eV)"); a.set_ylabel("Efficiency (%)")
a.set_title("Best physics-consistent lead-iodide cells vs. the limit", loc="left", fontsize=10); a.legend(frameon=False, fontsize=8, loc="upper right")
b = ax[1]; r = con.execute("select eg from cells where composition='MAPbI3' and std_illum and eg is not null").fetchdf().eg
lo, hi = REF["MAPbI3"][1:]; bins = np.arange(1.0, 3.1, 0.05)
inn, outn = r[(r >= lo) & (r <= hi)], r[(r < lo) | (r > hi)]
b.hist(inn, bins=bins, color=BLUE, label=f"within {lo}–{hi} eV (n={len(inn):,})"); b.hist(outn, bins=bins, color=ORG, label=f"outside (n={len(outn)})")
b.set_yscale("log"); b.set_xlabel("Reported bandgap of MAPbI3 records (eV)"); b.set_ylabel("Records (log scale)")
b.set_title("MAPbI3 should sit near 1.6 eV; some records say 2–3 eV", loc="left", fontsize=10); b.legend(frameon=False, fontsize=8)
for x in ax:
    x.grid(color=GRID, lw=.6); x.set_axisbelow(True)
    for s in ("top", "right"): x.spines[s].set_visible(False)
fig.tight_layout(); fig.savefig("spotlight.png")
