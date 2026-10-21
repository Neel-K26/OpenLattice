"""OpenLattice agent: text-to-SQL over the Perovskite DB, with an optional physics gate.
gate=False -> LLM+SQL over raw table (the published baseline approach).
gate=True  -> + premise check (Shockley-Queisser / Voc<=Eg / photon-limited Jsc) and querying only physics-consistent rows."""
import json, re, os, duckdb
import physics_checks as pc

MODEL = os.environ.get("LATTICE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
_tok = _mdl = None
def generate(messages, max_new=400):
    global _tok, _mdl
    if _mdl is None:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        _tok = AutoTokenizer.from_pretrained(MODEL)
        _mdl = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="cuda")
    text = _tok.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
    enc = _tok(text, return_tensors="pt").to(_mdl.device)
    out = _mdl.generate(**enc, max_new_tokens=max_new, do_sample=False)
    return _tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True)

SCHEMA = """DuckDB table {t}(doi, year, arch, composition, etl, htl, deposition, eg, voc, jsc, ff, pce, t80_h, sq_pce_limit, jsc_limit, light_mw, spectra)
- one row = one measured perovskite solar cell from the literature
- eg = perovskite bandgap in eV; voc in volts; jsc in mA/cm2; ff as a fraction (0-1); pce in percent
- arch is 'nip' or 'pin' (and a few rare values); doi identifies the paper
- sq_pce_limit = Shockley-Queisser efficiency limit (%) at that bandgap
- light_mw = illumination intensity of the measurement in mW/cm2 (100 = standard 1 sun); spectra = light spectrum, e.g. 'AM 1.5' or 'Indoor light'"""

RULES = """Rules:
- Use ONLY the filters the question asks for. Do not filter on arch, year, composition, etc. unless the question names them.
- 'standard 1-sun illumination' means: light_mw BETWEEN 90 AND 110
- Always put parentheses around any OR condition.
- For 'highest efficiency' use max(pce); for 'how many' use count(*)."""
SHOTS = [
 ("What is the highest power conversion efficiency (%) reported, under standard 1-sun (AM1.5G) illumination, for a single-junction perovskite solar cell with bandgap of at least 1.45 eV and strictly below 1.55 eV?",
  "```sql\nSELECT max(pce) AS max_pce FROM {t} WHERE light_mw BETWEEN 90 AND 110 AND eg >= 1.45 AND eg < 1.55\n```"),
 ("How many pin-architecture perovskite cells in the database report, under standard 1-sun illumination, a PCE of at least 12%?",
  "```sql\nSELECT count(*) AS n FROM {t} WHERE light_mw BETWEEN 90 AND 110 AND arch = 'pin' AND pce >= 12\n```"),
 ("Which paper reported a perovskite solar cell with a 1.55 eV bandgap and 19% power conversion efficiency? Give the DOI.",
  "```sql\nSELECT doi, eg, pce FROM {t} WHERE eg BETWEEN 1.50 AND 1.60 AND pce BETWEEN 18.5 AND 19.5 LIMIT 5\n```"),
]

def sql_prompt(q, table):
    msgs = [{"role": "system", "content": "You write one DuckDB SQL query that answers the question. Output only the query in a ```sql block.\n" + SCHEMA.format(t=table) + "\n" + RULES}]
    for u, a in SHOTS:
        msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a.format(t=table)}]
    return msgs + [{"role": "user", "content": q}]


def get_sql(text):
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";")

def run_sql(con, sql):
    if not re.match(r"^\s*(select|with)\b", sql, re.I): raise ValueError("read-only SELECT only")
    return con.execute(sql).fetchdf().head(20)

IMPOSSIBLE_WORDS = ("impossible", "exceed", "violat", "thermodynamic", "shockley", "physically")

def extract_claims(q):
    """Deterministic claim extraction (no LLM => no hallucinated checks)."""
    c = {}
    m = re.search(r"([\d.]+)\s*eV", q);                      c["eg"] = float(m.group(1)) if m else None
    m = re.search(r"([\d.]+)\s*%\s*(?:power conversion )?efficien", q); c["pce"] = float(m.group(1)) if m else None
    m = re.search(r"voltage of ([\d.]+)\s*V", q);            c["voc"] = float(m.group(1)) if m else None
    return c

def premise_check(q):
    c = extract_claims(q)
    if c["eg"] and c["pce"]:
        ok, msg = pc.check_solar(c["pce"], c["eg"])
        if not ok: return msg
    if c["eg"] and c["voc"] and c["voc"] > c["eg"]:
        return f"Voc {c['voc']} V exceeds the bandgap {c['eg']} eV (qVoc cannot exceed Eg), so this cell cannot exist."
    return None

def answer(q, gate, con):
    table = "cells_clean" if gate else "cells"
    if gate:
        v = premise_check(q)
        if v: return dict(text=f"Not physically possible: {v}", sql=None, refused=True)
    sql, err = None, None
    for _ in range(2):
        msgs = sql_prompt(q, table) + ([{"role": "user", "content": f"That failed: {err}. Fix it."}] if err else [])
        sql = get_sql(generate(msgs))
        try: res = run_sql(con, sql); break
        except Exception as e: err, res = str(e)[:200], None
    if res is None: return dict(text="Could not answer.", sql=sql, refused=False)
    note = ""
    if gate:
        n = con.execute("SELECT count(*) FROM cells WHERE any_bad").fetchone()[0]
        note = f" (computed on physics-consistent records only; {n} records were excluded: they fail Shockley-Queisser/Voc/Jsc/FF consistency checks or were measured outside standard 1-sun illumination)"
    ans = generate([{"role": "system", "content": "Answer the question from the SQL result. End with a line 'ANSWER: <value or short statement>'."},
                    {"role": "user", "content": f"Question: {q}\nSQL: {sql}\nResult:\n{res.to_string()}"}], 200)
    return dict(text=ans + note, sql=sql, refused=False)


# ---------- structured interface for the demo app (eval code above is untouched) ----------
SCOPE_WORDS = ("perovskite", "solar", "bandgap", "band gap", "efficien", "pce", "voc", "jsc", "fill factor",
               "doi", "paper", "cell", "ev", "stability", "t80", "architecture", "nip", "pin", "composition",
               "htl", "etl", "deposition", "photovoltaic", "shockley")

def in_scope(q):
    ql = q.lower()
    return any(re.search(r"\b" + re.escape(w), ql) for w in SCOPE_WORDS)

def ask(q, gate, con):
    """Returns a structured dict: status, answer, claims, sq_limit, sql, table (with failing-record flags), notes."""
    out = dict(q=q, gate=gate, status="answered", answer="", claims=extract_claims(q), sq_limit=None,
               sql=None, table=None, n_flagged=0, notes=[])
    c = out["claims"]
    if c.get("eg"): out["sq_limit"] = round(pc.sq_limit(c["eg"]), 2)
    if not in_scope(q):
        out.update(status="out_of_scope", answer="I only answer questions about the perovskite solar-cell database "
                   "(efficiency, bandgap, Voc, Jsc, fill factor, architecture, composition, stability, DOIs).")
        return out
    r = answer(q, gate, con)
    out["sql"] = r["sql"]
    if r.get("refused"):
        out.update(status="refused_impossible", answer=r["text"])
        return out
    out["answer"] = r["text"]
    if r["sql"]:
        try:
            df = run_sql(con, r["sql"])
            if {"doi", "pce"} <= set(df.columns):
                flags = []
                for d, p in zip(df["doi"], df["pce"]):
                    k = con.execute("SELECT count(*) FROM cells WHERE doi=? AND abs(pce-?)<1e-9 AND any_bad", [d, float(p)]).fetchone()[0]
                    flags.append(bool(k))
                df["fails_physics_check"] = flags
                out["n_flagged"] = int(sum(flags))
                if out["n_flagged"] and not gate:
                    out["notes"].append(f"{out['n_flagged']} of the {len(df)} returned records fail physics consistency checks.")
            out["table"] = df
        except Exception as e:
            out["notes"].append("could not render result table: " + str(e)[:100])
    if not r["sql"]: out["status"] = "failed"
    return out
