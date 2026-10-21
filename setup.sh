#!/usr/bin/env bash
# OpenLattice pod setup. Run once in the Jupyter terminal:  bash setup.sh
set -e
nvidia-smi --query-gpu=name,memory.total --format=csv
python -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
pip install -q pandas numpy scipy matplotlib pvlib pymatgen duckdb transformers accelerate huggingface_hub marimo
# optional, faster batched extraction (install later if the first install is slow):
#   pip install -q vllm
mkdir -p data papers out
python physics_checks.py
echo "Setup OK. Next: upload the Perovskite Database CSV into ./data/ and run: python audit_perovskite.py data/<file>.csv"
