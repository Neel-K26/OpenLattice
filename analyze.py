"""Fair re-scoring of results.csv. Run after run_eval.py."""
import json, re, duckdb, pandas as pd
con = duckdb.connect("lattice.duckdb", read_only=True)
Q = {q["id"]: q for q in json.load(open("questions.json"))}
R = pd.read_csv("results.csv")
doi_re = re.compile(r"10\.\d{4,9}/\S+")
IMP = ("impossible", "exceed", "violat", "thermodynamic", "shockley", "physically")
NONE = ("no ", "none", "not found", "0 rows", "could not", "empty")
def kind(t):
    t = str(t); tl = t.lower()
    if any(w in tl for w in IMP): return "flagged_impossible"
    if doi_re.search(t): return "fabricated_or_returned_DOI"
    return "none_found_or_other"
print("== IMPOSSIBLE PREMISES: what each system did ==")
im = R[R.type.str.startswith("impossible")].copy(); im["behaviour"] = im.text.map(kind)
print(im.groupby(["gate", "behaviour"]).size().unstack(fill_value=0))
print("\n== COUNTS: absolute error vs clean truth and vs raw-table truth ==")
c = R[R.type == "count"].copy()
def raw_count(i):
    q = Q[i]; m = re.search(r"How many (\w+)-arch.*at least (\d+)%", q["q"])
    return con.execute("SELECT count(*) FROM cells WHERE std_illum AND arch=? AND pce>=?", [m.group(1), int(m.group(2))]).fetchone()[0]
c["raw_truth"] = c.id.map(raw_count); c["clean_truth"] = c.id.map(lambda i: Q[i]["truth"])
c["err_vs_clean"] = (c.value - c.clean_truth).abs(); c["err_vs_raw"] = (c.value - c.raw_truth).abs()
print(c.groupby("gate")[["err_vs_clean", "err_vs_raw"]].agg(["mean", "max"]).round(1))
print("exact vs raw:", c.assign(ok=c.err_vs_raw < 0.5).groupby("gate").ok.mean().round(2).to_dict())
print("clean_truth vs raw_truth differ in", int((c.clean_truth != c.raw_truth).sum() / 2), "of", c.id.nunique(), "count questions")
print("\n== MAX_PCE rows ==")
m = R[R.type == "max_pce"].copy(); m["raw"] = m.id.map(lambda i: Q[i]["raw"]); m["lim"] = m.id.map(lambda i: Q[i]["lim"])
m["answered_raw_max"] = (m.value - m.raw).abs() <= 0.05
print(m.groupby("gate").agg(correct=("correct", "mean"), answered_raw_max=("answered_raw_max", "mean"), impossible=("impossible_answer", "mean")).round(2))
print("\nGate-ON misses:")
for _, r in m[(m.gate == True) & (~m.correct)].iterrows():
    print(f"id {r.id}: got {r.value}, truth {Q[r.id]['truth']} | SQL: {str(r.sql)[:160]}")
print("\nGate-OFF max_pce answers that are NOT the raw max (LLM/SQL errors):")
print(m[(m.gate == False) & (~m.answered_raw_max)][["id", "value", "raw", "truth"]].to_string(index=False))

print("\n== MAX_PCE: did the answer come from a record that FAILS the physics checks? ==")
def src(r):
    if pd.isna(r.value): return "no_value"
    q = Q[r.id]; base = "FROM cells WHERE eg>=? AND eg<? AND abs(pce-?)<0.005"; a = [q["a"], q["b"], r.value]
    good = con.execute("SELECT count(*) " + base + " AND NOT any_bad", a).fetchone()[0]
    phys = con.execute("SELECT count(*) " + base + " AND any_bad AND std_illum", a).fetchone()[0]
    illum = con.execute("SELECT count(*) " + base + " AND NOT std_illum", a).fetchone()[0]
    if good: return "ok_consistent_record"
    if phys: return "only_in_physics_failing_record"
    if illum: return "only_in_non_1sun_record"
    return "not_in_window"
m["source"] = m.apply(src, axis=1)
print(m.groupby(["gate", "source"]).size().unstack(fill_value=0))
