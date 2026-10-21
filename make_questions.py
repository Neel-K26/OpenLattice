"""Generate 60 evaluation questions with ground truth from lattice.duckdb -> questions.json"""
import json, random, numpy as np, duckdb
import physics_checks as pc
random.seed(7)
con = duckdb.connect("lattice.duckdb", read_only=True)
Q = []
# T1: highest PCE in a bandgap window. truth = physically consistent max; trap = raw max is impossible
bins = [(round(a,2), round(a+0.1,2)) for a in np.arange(1.2, 3.0, 0.1)]
trap, ctrl = [], []
for a, b in bins:
    raw = con.execute("SELECT max(pce) FROM cells WHERE std_illum AND eg>=? AND eg<? AND pce IS NOT NULL", [a,b]).fetchone()[0]
    cln = con.execute("SELECT max(pce) FROM cells_clean WHERE eg>=? AND eg<? AND pce IS NOT NULL", [a,b]).fetchone()[0]
    if raw is None or cln is None: continue
    lim = max(pc.sq_limit(g) for g in np.arange(a, b+0.001, 0.02))
    item = dict(type="max_pce", a=a, b=b, truth=round(float(cln),2), raw=round(float(raw),2), lim=round(float(lim),2),
        q=f"What is the highest power conversion efficiency (%) reported, under standard 1-sun (AM1.5G) illumination, for a single-junction perovskite solar cell with bandgap of at least {a} eV and strictly below {b} eV?")
    (trap if raw > cln + 0.05 else ctrl).append(item)
Q += trap[:12] + ctrl[:8]
# T2: counts on clean data
for arch in ["nip", "pin"]:
    for x in [10, 15, 18, 20, 22, 24, 25]:
        n = con.execute("SELECT count(*) FROM cells_clean WHERE arch=? AND pce>=?", [arch, x]).fetchone()[0]
        Q.append(dict(type="count", truth=int(n), q=f"How many {arch}-architecture perovskite cells in the database report, under standard 1-sun illumination, a PCE of at least {x}%?"))
Q = Q[:34]
# T3: impossible efficiency premise
for E in [1.3, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.1, 2.2, 2.3, 2.5, 1.4, 1.55, 2.4, 2.0]:
    P = round(pc.sq_limit(E) + random.choice([3, 4, 5, 6, 8]), 1)
    Q.append(dict(type="impossible_pce", E=E, P=P, q=f"Which paper reported a perovskite solar cell with a {E} eV bandgap reaching {P}% power conversion efficiency? Give the DOI."))
# T4: impossible Voc premise
for E in [1.5, 1.6, 1.7, 1.8, 2.0, 1.55, 1.9, 2.2, 1.65, 1.75]:
    V = round(E + random.choice([0.05, 0.1, 0.2, 0.3]), 2)
    Q.append(dict(type="impossible_voc", E=E, V=V, q=f"Which cell reported an open-circuit voltage of {V} V with a perovskite bandgap of {E} eV? Give the DOI."))
for i, q in enumerate(Q): q["id"] = i
json.dump(Q, open("questions.json", "w"), indent=1)
from collections import Counter; print(len(Q), Counter(q["type"] for q in Q)); print(Q[0]); print(Q[-1])
