"""Multi-check physics audit of the Perovskite Database. Usage: python audit2.py data.csv"""
import sys, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import physics_checks as pc
from numpy import trapezoid
csv = sys.argv[1]
d = pd.read_csv(csv, low_memory=False)
n = lambda c: pd.to_numeric(d[c], errors="coerce")
d["pce"],d["voc"],d["jsc"],d["ff"],d["eg"] = n("JV_default_PCE"),n("JV_default_Voc"),n("JV_default_Jsc"),n("JV_default_FF"),n("Perovskite_band_gap")
d["light"] = n("JV_light_intensity"); sp = d["JV_light_spectra"].astype(str).str.lower()
d = d[(d.pce>1)&d.eg.between(0.8,3.5)&d.voc.notna()&d.jsc.notna()&d.ff.notna()].copy()
sp = d["JV_light_spectra"].astype(str).str.lower()
d["std"] = d.light.between(90,110) & ~sp.str.contains("indoor|mono|led|yellow|outdoor|ligth")
n_nonstd = int((~d["std"]).sum())
d = d[d["std"]].copy()   # SQ limit applies to standard 1-sun illumination only
d = d[~d["Cell_architecture"].astype(str).str.contains("tandem|multi",case=False)]
grid = np.round(np.arange(0.8,3.51,0.01),2)
def jsc_lim(eg):  # mA/cm2, all photons above gap collected
    m = (pc._E_J/pc.Q) >= eg
    return pc.Q*trapezoid(pc._PHI[m], pc._WL[m])/10
JL = np.array([jsc_lim(g) for g in grid]); PL = np.array([pc.sq_limit(g) for g in grid])
d["jsc_lim"]=np.interp(d.eg,grid,JL); d["pce_lim"]=np.interp(d.eg,grid,PL)
d["f_voc"]  = d.voc > d.eg                          # Voc cannot exceed bandgap/q
d["f_jsc"]  = d.jsc > d.jsc_lim*1.02                # more current than photons available (2% tol)
d["f_pce"]  = d.pce > d.pce_lim + 0.5               # beats detailed-balance limit
d["f_ff"]   = d.ff > 0.9                            # FF above ~0.9 is beyond any reported
d["pce_calc"]= d.voc*d.jsc*d.ff                     # Pin=100 mW/cm2
d["f_math"] = (d.pce_calc/d.pce - 1).abs() > 0.10   # PCE != Voc*Jsc*FF (10% tol)
fl = ["f_voc","f_jsc","f_pce","f_ff","f_math"]
d["any"] = d[fl].any(axis=1)
out = [f"Excluded (non-1-sun illumination, e.g. indoor light): {n_nonstd}", f"Single-junction 1-sun rows with full JV data: {len(d)}"]
names = {"f_voc":"Voc > bandgap (impossible)","f_jsc":"Jsc > photon-limit for that bandgap","f_pce":"PCE > Shockley-Queisser limit",
         "f_ff":"FF > 0.90","f_math":"PCE != Voc x Jsc x FF (>10%)"}
for f in fl: out.append(f"{names[f]}: {int(d[f].sum())} ({100*d[f].mean():.2f}%)")
out.append(f"Rows failing at least one check: {int(d['any'].sum())} ({100*d['any'].mean():.2f}%)")
out.append(f"Papers (DOIs) with >=1 failing row: {d.loc[d['any'],'Ref_DOI_number'].nunique()} of {d['Ref_DOI_number'].nunique()}")
open("out/audit2_summary.txt","w").write("\n".join(out)+"\n"); print("\n".join(out))
cols=["Ref_DOI_number","Cell_architecture","eg","voc","jsc","ff","pce","pce_calc","pce_lim","jsc_lim"]+fl
d.loc[d["any"],cols].to_csv("out/audit2_flags.csv",index=False)
fig,ax=plt.subplots(1,2,figsize=(11,4.4),dpi=150)
g=d[~d["any"]]; b=d[d["any"]]
ax[0].scatter(g.eg,g.pce,s=3,alpha=.2,c="#1F3A5F"); ax[0].scatter(b.eg,b.pce,s=8,c="#D1495B"); ax[0].plot(grid,PL,"k"); ax[0].set_xlim(1,3.2); ax[0].set_ylim(0,40)
ax[0].set_xlabel("Bandgap (eV)"); ax[0].set_ylabel("PCE (%)"); ax[0].set_title("Efficiency vs SQ limit")
ax[1].scatter(g.eg,g.jsc,s=3,alpha=.2,c="#1F3A5F"); ax[1].scatter(b.eg,b.jsc,s=8,c="#D1495B"); ax[1].plot(grid,JL,"k"); ax[1].set_xlim(1,3.2); ax[1].set_ylim(0,50)
ax[1].set_xlabel("Bandgap (eV)"); ax[1].set_ylabel("Jsc (mA/cm$^2$)"); ax[1].set_title("Current vs photon limit (red=fails any check)")
fig.tight_layout(); fig.savefig("out/audit2_scatter.png")
