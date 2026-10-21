# PASTE AS A NEW NOTEBOOK CELL (after the cell that loads agent/model). Needs compare_facts.json + compare_agent.py in the same folder.
import ipywidgets as w
from IPython.display import display, clear_output, Image
import compare_agent as ca
ca.agent = agent            # reuse the loaded model/module
_q = w.Dropdown(options=["Perovskite is not used in the market yet - how close is it to silicon?",
    "A silicon solar cell with 31% efficiency",
    "A perovskite silicon tandem with 48% efficiency",
    "Which is closer to its physical limit: silicon, perovskite, or the tandem?",
    "Should a company bet on perovskite or silicon today?"], layout=w.Layout(width="95%"))
_b = w.Button(description="Ask", button_style="primary"); _o = w.Output()
def _go(_):
    with _o:
        clear_output(); r = ca.ask_compare(_q.value); print(r["status"].upper(), "\n"); print(r["answer"])
_b.on_click(_go); display(_q, _b, _o); display(Image("pv_compare.png"))
