"""Cross-technology reasoning (silicon vs perovskite) grounded in verified facts, with a physics gate on claims.
Needs compare_facts.json (written by pv_compare.py) and, optionally, lattice.duckdb for the perovskite-database facts."""
import json, re, os
import physics_checks as pc, pv_limits as pl
import agent

FACTS = json.load(open("compare_facts.json"))

def facts_text():
    L = []
    for t in FACTS["tech_summary"]:
        L.append(f"- {t['tech']}: best certified record {t['best_pce']:.1f}% ({t['year']}, {t['lab']}); physical limit used {t['sq_limit']}% "
                 f"(bandgap {t['bandgap_ev']}); record is {t['pct_of_sq']}% of that limit; {t['n_records']} records in the NREL table.")
    si=[t for t in FACTS["tech_summary"] if t["tech"]=="c-Si"][0]; pk=[t for t in FACTS["tech_summary"] if t["tech"].startswith("perovskite (")][0]; td=[t for t in FACTS["tech_summary"] if "tandem" in t["tech"]][0]
    L.append(f"- Gap between best silicon and best single-junction perovskite record: {si['best_pce']-pk['best_pce']:.1f} percentage points (both about 28%). The tandem record is {td['best_pce']-si['best_pce']:.1f} points above silicon. Tandem limit {td['sq_limit']}% belongs to the tandem only.")
    L.append(f"- Silicon: Shockley-Queisser limit {pc.sq_limit(pl.SI_EG):.1f}% at 1.12 eV; practical limit {FACTS['si_practical_limit_note']}.")
    s = FACTS.get("stability") or {}
    if s:
        L.append(f"- Perovskite stability in the literature database: only {s['with_t80']} of {s['perovskite_records']} physics-consistent records report a T80 lifetime; "
                 f"median {s['median_t80_h']:.0f} h, longest {s['max_t80_h']:.0f} h (about {s['max_t80_h']/8760:.1f} years); records reaching 1 year: {s['n_ge_1yr']}.")
    L.append(f"- Silicon modules: {FACTS['si_warranty_note']}.")
    L.append("- Stability numbers describe typical literature devices, not record cells.")
    L.append("- The NREL table holds record (best) cells only; the literature database holds typical devices (median perovskite PCE about 12.5%, best consistent lead-iodide cells 22-25%).")
    return "\n".join(L)

def claim_check(q):
    """Deterministic check of an efficiency claim about silicon or a perovskite/silicon tandem. Returns (status, message) or None."""
    ql = q.lower(); m = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    if not m: return None
    p = float(m.group(1)); tandem = "tandem" in ql
    if tandem and ("perovskite" in ql or "silicon" in ql):
        top, lim = pl.best_tandem(pl.SI_EG)
        if p > lim + 0.5: return "refused_impossible", f"Not physically possible: {p:.1f}% exceeds the ideal two-terminal perovskite/silicon limit of {lim:.1f}% (best top bandgap {top} eV, 1 sun, AM1.5G)."
        return "plausible", f"{p:.1f}% is below the ideal two-terminal limit of {lim:.1f}% for a silicon bottom cell. The best certified record in the NREL table is {[t for t in FACTS['tech_summary'] if 'tandem' in t['tech']][0]['best_pce']:.1f}%."
    if "silicon" in ql or "c-si" in ql:
        sq = pc.sq_limit(pl.SI_EG)
        if p > sq + 0.5: return "refused_impossible", f"Not physically possible: {p:.1f}% exceeds the Shockley–Queisser limit of {sq:.1f}% for a 1.12 eV single junction."
        if p > pl.SI_PRACTICAL + 0.5: return "beyond_practical", f"{p:.1f}% is below the theoretical {sq:.1f}% but above the practical silicon limit of about {pl.SI_PRACTICAL:.0f}% (Auger recombination), so a single-junction silicon cell is not expected to reach it."
        return "plausible", f"{p:.1f}% is within the practical limit of about {pl.SI_PRACTICAL:.0f}%. The best certified silicon record in the NREL table is {[t for t in FACTS['tech_summary'] if t['tech']=='c-Si'][0]['best_pce']:.1f}%."
    return None

def unsupported_numbers(ans, facts):
    """Numbers written in the answer that do not appear in the facts (model slips)."""
    nums = lambda t: {x.rstrip('.') for x in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", t.replace(",", ""))}
    return sorted(nums(ans) - nums(facts) - {"1","2","3","4","5"})

def ask_compare(q):
    if not agent.in_scope(q) and not re.search(r"silicon|tandem|perovskite", q, re.I):
        return dict(status="out_of_scope", answer="I answer questions about silicon and perovskite solar cells.", facts=None)
    c = claim_check(q)
    if c and c[0] in ("refused_impossible",): return dict(status=c[0], answer=c[1], facts=None)
    ft = facts_text()
    msgs = [{"role": "system", "content": "You are a photovoltaics assistant. Answer ONLY from the FACTS below, in at most 5 sentences. Copy differences from the facts, never compute your own. Say stability numbers describe typical devices. "
             "Quote the numbers you use. If the facts do not cover the question, say what is missing. Do not invent numbers.\nFACTS:\n" + ft},
            {"role": "user", "content": q}]
    ans = agent.generate(msgs, 300).strip()
    bad = unsupported_numbers(ans, ft)
    if bad: ans += "\n\n[check] These figures are not in the verified facts: " + ", ".join(bad) + " - treat them with caution."
    if c: ans = c[1] + "\n\n" + ans
    return dict(status=c[0] if c else "answered", answer=ans, facts=ft)
