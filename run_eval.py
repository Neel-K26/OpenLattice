"""Run gate-off vs gate-on on questions.json -> results.csv + summary"""
import json, re, sys, duckdb, pandas as pd, agent
con = duckdb.connect("lattice.duckdb", read_only=True)
Q = json.load(open("questions.json"))
if len(sys.argv) > 1: Q = Q[:int(sys.argv[1])]
def num(t):
    m = re.search(r"ANSWER:\s*[^0-9\-]*(-?[\d,]*\.?\d+)", t); 
    return float(m.group(1).replace(",", "")) if m else None
rows = []
for gate in (False, True):
    for q in Q:
        r = agent.answer(q["q"], gate, con); t = r["text"]; v = num(t)
        flagged = any(w in t.lower() for w in agent.IMPOSSIBLE_WORDS)
        if q["type"] in ("max_pce", "count"):
            tol = 0.05 if q["type"] == "max_pce" else 0.5
            correct = v is not None and abs(v - q["truth"]) <= tol
            impossible = q["type"] == "max_pce" and v is not None and v > q["lim"] + 0.5
        else:
            correct, impossible = flagged, False
        rows.append(dict(gate=gate, id=q["id"], type=q["type"], correct=correct, impossible_answer=impossible, value=v, truth=q.get("truth"), sql=r["sql"], text=t[:300]))
df = pd.DataFrame(rows); df.to_csv("results.csv", index=False)
s = df.groupby(["gate", "type"]).agg(n=("correct", "size"), accuracy=("correct", "mean"), impossible_rate=("impossible_answer", "mean")).round(3)
print(s); s.to_csv("summary.csv")
