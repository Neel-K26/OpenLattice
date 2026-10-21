import marimo
app = marimo.App(width="full", app_title="OpenLattice")


@app.cell
def _():
    import marimo as mo, duckdb, numpy as np, pandas as pd, matplotlib.pyplot as plt
    import physics_checks as pc, agent, replay
    run_mode = replay.install(agent)
    con = duckdb.connect("lattice.duckdb", read_only=True)
    n_all = con.execute("select count(*) from cells").fetchone()[0]
    n_bad = con.execute("select count(*) from cells where any_bad").fetchone()[0]
    return agent, con, mo, n_all, n_bad, np, pc, pd, plt, run_mode


@app.cell
def _(mo, n_all, n_bad, run_mode):
    mo.md(f"""
    # OpenLattice — a physics-checked assistant for solar-cell literature
    A domain model for **{n_all:,} published perovskite solar-cell measurements**. A language model writes the query;
    a physics gate checks the question and the data against the **Shockley–Queisser limit**, Voc ≤ Eg/q and photon-limited Jsc.
    **{n_bad:,} records ({100*n_bad/n_all:.1f}%) are excluded when the gate is on**: they fail a physics check or were measured outside 1-sun illumination.

    *Model mode: **{'live on GPU' if run_mode == 'live' else 'replay (recorded 7B-model outputs; database query and physics gate run live)'}***
    """)
    return


@app.cell
def _(mo):
    from examples import EXAMPLES as examples
    pick = mo.ui.dropdown(options=list(examples), value="Best efficiency, 2.2-2.3 eV (raw table: 17.9)", label="Examples")
    return examples, pick


@app.cell
def _(examples, mo, pick):
    q = mo.ui.text_area(value=examples[pick.value], label="Your question", full_width=True, rows=3)
    mode = mo.ui.radio(options=["Physics gate ON", "Physics gate OFF", "Compare both"], value="Compare both", inline=True)
    go = mo.ui.run_button(label="Ask OpenLattice", kind="success")
    mo.vstack([pick, q, mo.hstack([mode, go], justify="start", gap=2)])
    return go, mode, q


@app.cell
def _(agent, con, go, mo, mode, q):
    mo.stop(not go.value, mo.md("*Choose an example or type a question, then press **Ask OpenLattice**. The first call loads the model (~1 min).*"))
    with mo.status.spinner(title="Thinking (model + physics checks)…"):
        runs = {}
        if mode.value in ("Physics gate ON", "Compare both"): runs["ON"] = agent.ask(q.value, True, con)
        if mode.value in ("Physics gate OFF", "Compare both"): runs["OFF"] = agent.ask(q.value, False, con)
    return (runs,)


@app.cell
def _(mo, runs):
    BADGE = {"answered": ("#2a9d8f", "ANSWERED"), "refused_impossible": ("#D1495B", "REFUSED: PHYSICALLY IMPOSSIBLE"),
             "out_of_scope": ("#777", "OUT OF SCOPE"), "failed": ("#E9A23B", "COULD NOT ANSWER")}

    def card(tag, r):
        col, label = BADGE[r["status"]]
        head = mo.md(f"### Gate {tag} &nbsp; <span style='background:{col};color:#fff;padding:2px 8px;border-radius:6px;font-size:0.7em'>{label}</span>")
        parts = [head, mo.md(r["answer"])]
        c = {k: v for k, v in r["claims"].items() if v is not None}
        if c:
            lim = f" | Shockley–Queisser limit at {c['eg']} eV = **{r['sq_limit']} %**" if r["sq_limit"] and "eg" in c else ""
            parts.append(mo.md("**Claims detected:** " + ", ".join(f"{k} = {v}" for k, v in c.items()) + lim))
        for n in r["notes"]: parts.append(mo.callout(mo.md(n), kind="warn"))
        if r["table"] is not None and len(r["table"]):
            t = r["table"]
            parts.append(mo.ui.table(t, selection=None, page_size=5))
        if r["sql"]: parts.append(mo.accordion({"SQL the model wrote": mo.md("```sql\n" + str(r["sql"]) + "\n```")}))
        return mo.vstack(parts)

    mo.hstack([card(k, v) for k, v in runs.items()], widths="equal", align="start", gap=2)
    return


@app.cell
def _(con, mo, np, pc, plt):
    import json as _json
    _BLUE, _ORG, _INK, _MUTED, _GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e6e5e1"
    _d = con.execute("select eg, pce, any_bad from cells where std_illum and pce>1 and eg between 1 and 3.3 and voc is not null and jsc is not null and ff is not null and arch not ilike '%tandem%'").fetchdf()
    _Q = sorted([_x for _x in _json.load(open("questions.json")) if _x["type"] == "max_pce" and _x["raw"] > _x["truth"] + 0.05], key=lambda _x: _x["a"])
    fig2, ax2 = plt.subplots(1, 2, figsize=(11.5, 4.4), gridspec_kw={"width_ratios": [1.25, 1]})
    _ok, _bad = _d[~_d.any_bad], _d[_d.any_bad]
    ax2[0].scatter(_ok.eg, _ok.pce, s=3, alpha=.25, color=_BLUE, lw=0, label=f"consistent (n={len(_ok):,})")
    ax2[0].scatter(_bad.eg, _bad.pce, s=7, alpha=.8, color=_ORG, lw=0, label=f"fails a check (n={len(_bad):,})")
    _gg = np.arange(1.0, 3.3, 0.02)
    ax2[0].plot(_gg, [pc.sq_limit(x) for x in _gg], color=_INK, lw=1.6, label="Shockley–Queisser limit")
    ax2[0].set_xlim(1, 3.2); ax2[0].set_ylim(0, 36); ax2[0].set_xlabel("Reported bandgap (eV)"); ax2[0].set_ylabel("Reported PCE (%)")
    ax2[0].set_title("1-sun measurements vs. the physical limit", loc="left", fontsize=10); ax2[0].legend(frameon=False, fontsize=8, loc="upper right", markerscale=2.5)
    for _i, _q in enumerate(_Q):
        ax2[1].plot([_q["truth"], _q["raw"]], [_i, _i], color=_GRID, lw=3, solid_capstyle="round")
        ax2[1].scatter(_q["truth"], _i, s=48, color=_BLUE, zorder=3); ax2[1].scatter(_q["raw"], _i, s=48, color=_ORG, zorder=3)
        ax2[1].text(_q["raw"] + .5, _i, f"{_q['raw']:g}", va="center", fontsize=8, color=_MUTED)
    ax2[1].set_yticks(range(len(_Q))); ax2[1].set_yticklabels([f"{_q['a']:.1f}–{_q['b']:.1f} eV" for _q in _Q], fontsize=8.5); ax2[1].invert_yaxis()
    ax2[1].set_xlim(0, 21); ax2[1].set_xlabel("Highest efficiency returned (%)")
    ax2[1].set_title("Best cell per bandgap window: raw (orange) vs. gated (blue)", loc="left", fontsize=10)
    for _a in ax2:
        for _s in ("top", "right"): _a.spines[_s].set_visible(False)
    fig2.tight_layout()
    mo.vstack([mo.md("---\n## What the audit found"), fig2])
    return


@app.cell
def _(mo):
    import compare_agent as ca
    from examples import COMPARE
    cq = mo.ui.dropdown(options=COMPARE, value=COMPARE[0], label="Silicon vs perovskite question", full_width=True)
    cgo = mo.ui.run_button(label="Ask", kind="success")
    mo.vstack([mo.md("---\n## Silicon vs perovskite: is perovskite ready for the market?\nVerified facts from NREL's record table and our perovskite audit; impossible claims are refused and every number the model writes is checked."), cq, cgo])
    return ca, cgo, cq


@app.cell
def _(ca, cgo, cq, mo):
    mo.stop(not cgo.value, mo.md("*Pick a question and press Ask.*"))
    _r = ca.ask_compare(cq.value)
    mo.vstack([mo.md(f"**{_r['status'].upper().replace('_', ' ')}**"), mo.md(_r["answer"].replace("\n", "\n\n")),
               mo.image("pv_compare.png")])
    return


@app.cell
def _(mo):
    mo.md("---\n## Check any claim yourself")
    eg = mo.ui.slider(0.9, 3.3, value=1.55, step=0.01, label="Bandgap (eV)", full_width=True)
    pce = mo.ui.slider(1, 40, value=26, step=0.1, label="Claimed efficiency (%)", full_width=True)
    mo.hstack([eg, pce])
    return eg, pce


@app.cell
def _(eg, mo, np, pc, pce, plt):
    ok, msg = pc.check_solar(pce.value, eg.value)
    g = np.arange(0.9, 3.3, 0.02)
    L = [pc.sq_limit(x) for x in g]
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.plot(g, L, "k", label="Shockley–Queisser limit")
    ax.scatter([eg.value], [pce.value], c="#2a9d8f" if ok else "#D1495B", s=60, zorder=3, label="your claim")
    ax.set_xlabel("Bandgap (eV)")
    ax.set_ylabel("Efficiency (%)")
    ax.legend(frameon=False)
    fig.tight_layout()
    mo.vstack([mo.md(("✅ " if ok else "❌ ") + msg), fig])
    return


if __name__ == "__main__":
    app.run()
