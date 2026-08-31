#!/usr/bin/env python3
import argparse, json
from pathlib import Path

p = argparse.ArgumentParser(); p.add_argument('--out', default='results_docker/report.md'); a = p.parse_args()
root = Path('results_docker')
ev = json.loads((root/'evaluation.json').read_text())
def net(name):
    path = root/f'ctrl_{name}.json'
    return json.loads(path.read_text())['summary'] if path.exists() else {}
n0, n1 = net('noqos'), net('qos')
agg = ev['aggregate']
lines = ['# Rapport expérimental consolidé', '', '## Mobilité — phase A', '',
         '| Mesure | Baseline | Adaptatif |', '|---|---:|---:|',
         f"| Complétion moyenne (%) | {agg['baseline_completion_pct']['mean']} | {agg['adaptive_completion_pct']['mean']} |", '',
         '## Réseau — phase B', '', '| Mesure | Sans QoS | Avec QoS |', '|---|---:|---:|',
         f"| Débit émis moyen (Mbit/s) | {n0.get('bw_mbps_mean', '—')} | {n1.get('bw_mbps_mean', '—')} |", '',
         '## Boucle fermée — phase C', '',
         'Validée si `orchestrator_closed_loop.log` contient des changements de phase et `ryu.log` une installation de règle.']
out=Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text('\n'.join(lines)+'\n'); print(out)
