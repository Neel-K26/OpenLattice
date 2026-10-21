import marimo
app = marimo.App(width="full", app_title="OpenLattice")


@app.cell
def _():
    import marimo as mo, duckdb, numpy as np, pandas as pd, matplotlib.pyplot as plt
    import physics_checks as pc, agent
    con = duckdb.connect("lattice.duckdb", read_only=True)
    n_all = con.execute("select count(*) from cells").fetchone()[0]
    n_bad = con.execute("select count(*) from cells where any_bad").fetchone()[0]
    return agent, con, mo, n_all, n_bad, np, pc, pd, plt


@app.cell
def _(mo, n_all, n_bad):
    mo.md(f"""
    # OpenLattice — a physics-checked assistant for solar-cell literature
    A domain model for **{n_all:,} published perovskite solar-cell measurements**. A language model writes the query;
    a physics gate checks the question and the data against the **Shockley–Queisser limit**, Voc ≤ Eg/q and photon-limited Jsc.
    **{n_bad:,} records ({100*n_bad/n_all:.1f}%) are excluded when the gate is on**: they fail a physics check or were measured outside 1-sun illumination.
    """)
    return


@app.cell
def _(mo):
    examples = {
        "Best efficiency, 2.2-2.3 eV (raw table: 17.9)": "What is the highest power conversion efficiency (%) reported, under standard 1-sun (AM1.5G) illumination, for a single-junction perovskite solar cell with bandgap of at least 2.2 eV and strictly below 2.3 eV?",
        "Best efficiency, 2.1-2.2 eV (raw table: 13.0)": "What is the highest power conversion efficiency (%) reported, under standard 1-sun (AM1.5G) illumination, for a single-junction perovskite solar cell with bandgap of at least 2.1 eV and strictly below 2.2 eV?",
        "Best efficiency, 1.5-1.6 eV (both agree)": "What is the highest power conversion efficiency (%) reported, under standard 1-sun (AM1.5G) illumination, for a single-junction perovskite solar cell with bandgap of at least 1.5 eV and strictly below 1.6 eV?",
        "Impossible claim (1.9 eV, 28 %)": "Which paper reported a perovskite solar cell with a 1.9 eV bandgap reaching 28% power conversion efficiency? Give the DOI.",
        "Impossible Voc": "Which paper reported a perovskite cell with a 1.6 eV bandgap and an open-circuit voltage of 1.9 V? Give the DOI.",
        "Count high-efficiency nip cells": "How many nip-architecture perovskite cells in the database report, under standard 1-sun illumination, a PCE of at least 24%?",
        "Out of scope": "Who won the 2022 football world cup?",
    }
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
