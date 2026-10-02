#!/usr/bin/env python3
"""Rejeu web des simulations SUMO : produit une page HTML autonome.

Les positions rejouees sont celles que SUMO ecrit dans son fichier FCD
(floating car data) pendant la simulation : ce n'est pas une animation
d'illustration, mais le trace des vehicules effectivement simules.
"""
import argparse, json, socket, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMO_DIR = ROOT / "sumo_one_junction"
ORCH = ROOT / "pyfilesTrue" / "tls_orchestrator_CORRECTED.py"
CFG = {"baseline": "one_junction_asymmetric.sumocfg",
       "webster": "one_junction_asymmetric_webster.sumocfg",
       "adaptive": "one_junction_asymmetric.sumocfg"}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def simuler(mode, seed, fin, periode, sortie):
    fcd = sortie / f"fcd_{mode}.xml"
    base = ["sumo", "-c", str(SUMO_DIR / CFG[mode]), "--seed", str(seed), "--end", str(fin),
            "--time-to-teleport", "-1", "--fcd-output", str(fcd),
            "--no-warnings", "true"]
    if mode == "adaptive":
        port = free_port()
        sumo = subprocess.Popen(base + ["--remote-port", str(port)], cwd=SUMO_DIR,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        cmd = [sys.executable, str(ORCH), "--sumo-port", str(port), "--tls-id", "J1",
               "--ns-phase-idx", "0", "--ew-phase-idx", "2", "--min-green", "10",
               "--max-green", "45", "--hysteresis", "0.15"]
        subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=600)
        sumo.wait(timeout=60)
    else:
        subprocess.run(base, cwd=SUMO_DIR, check=True, capture_output=True, timeout=600)
    return fcd


def lire_fcd(chemin, maxi, periode=1):
    """Sous-echantillonne a la lecture : la version de SUMO installee n'expose
    pas d'option de periode sur la sortie FCD."""
    pas = []
    for _, elem in ET.iterparse(chemin, events=("end",)):
        if elem.tag == "timestep":
            t = float(elem.get("time"))
            if periode > 1 and int(t) % periode:
                elem.clear(); continue
            vehs = [[round(float(v.get("x")), 1), round(float(v.get("y")), 1),
                     1 if float(v.get("speed", 0)) < 0.3 else 0] for v in elem]
            pas.append([t, vehs])
            elem.clear()
            if len(pas) >= maxi:
                break
    return pas


GABARIT = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Rejeu SUMO — carrefour J1</title><style>
body{margin:0;background:#0f1115;color:#e6e6e6;font:14px/1.5 system-ui,sans-serif}
h1{font-size:18px;margin:18px 24px 4px}p.s{margin:0 24px 16px;color:#9aa0a6}
.wrap{display:flex;gap:24px;padding:0 24px 24px;flex-wrap:wrap}
.col{background:#171a21;border:1px solid #262b36;border-radius:10px;padding:14px}
.col h2{font-size:15px;margin:0 0 2px}.col .kpi{color:#9aa0a6;margin:0 0 10px;font-size:13px}
canvas{background:#11141a;border-radius:6px;display:block}
.bar{display:flex;align-items:center;gap:12px;padding:10px 24px;color:#9aa0a6}
button{background:#2b6cb0;color:#fff;border:0;border-radius:6px;padding:7px 16px;cursor:pointer;font-size:14px}
.leg{margin:0 24px 18px;color:#9aa0a6;font-size:13px}
b.r{color:#e5534b}b.g{color:#57ab5a}
</style></head><body>
<h1>Rejeu des simulations SUMO — carrefour J1</h1>
<p class="s">Positions issues du fichier FCD ecrit par SUMO pendant la simulation. Graine __SEED__.</p>
<div class="bar"><button id="b">Pause</button><span id="t">t = 0 s</span></div>
<div class="wrap" id="w"></div>
<p class="leg"><b class="g">&#9632;</b> vehicule en mouvement &nbsp;&nbsp; <b class="r">&#9632;</b> vehicule arrete (file d'attente)</p>
<script>
const DATA = __DATA__, BORNE = 200, TAILLE = 420;
const w = document.getElementById('w');
const vues = DATA.map(d => {
  const col = document.createElement('div'); col.className = 'col';
  col.innerHTML = `<h2>${d.titre}</h2><p class="kpi">${d.kpi}</p>`;
  const c = document.createElement('canvas'); c.width = c.height = TAILLE;
  col.appendChild(c); w.appendChild(col);
  return {ctx: c.getContext('2d'), pas: d.pas};
});
const N = Math.max(...DATA.map(d => d.pas.length));
const P = x => x / BORNE * TAILLE;
function route(g){
  g.fillStyle = '#11141a'; g.fillRect(0,0,TAILLE,TAILLE);
  g.strokeStyle = '#2a2f3a'; g.lineWidth = P(16);
  g.beginPath(); g.moveTo(P(100),0); g.lineTo(P(100),TAILLE);
  g.moveTo(0,P(100)); g.lineTo(TAILLE,P(100)); g.stroke();
  g.strokeStyle='#3a4150'; g.lineWidth=1; g.strokeRect(P(92),P(92),P(16),P(16));
}
let i = 0, run = true;
function trame(){
  vues.forEach(v => {
    const g = v.ctx; route(g);
    const p = v.pas[Math.min(i, v.pas.length-1)]; if(!p) return;
    p[1].forEach(([x,y,arret]) => {
      g.fillStyle = arret ? '#e5534b' : '#57ab5a';
      g.beginPath(); g.arc(P(x), TAILLE-P(y), 3, 0, 6.284); g.fill();
    });
  });
  const p0 = vues[0].pas[Math.min(i, vues[0].pas.length-1)];
  document.getElementById('t').textContent = 't = ' + (p0 ? p0[0] : 0) + ' s';
  if(run) i = (i+1) % N;
}
document.getElementById('b').onclick = e => { run = !run; e.target.textContent = run ? 'Pause' : 'Lecture'; };
setInterval(trame, 60); trame();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--end", type=int, default=1200)
    ap.add_argument("--period", type=int, default=5)
    ap.add_argument("--out", default="results_docker/replay.html")
    a = ap.parse_args()
    out = Path(a.out).resolve(); out.parent.mkdir(parents=True, exist_ok=True)
    travail = out.parent / ".replay-work"; travail.mkdir(exist_ok=True)

    titres = {"baseline": ("Feux fixes 31 s/31 s", "complétion 74,89 % sur 30 graines"),
              "webster": ("Plan fixe calculé par Webster, cycle 50 s", "complétion 76,50 % sur 30 graines"),
              "adaptive": ("Orchestrateur adaptatif SUMO/TraCI", "complétion 100 % sur 30 graines")}
    data = []
    for mode in ("baseline", "webster", "adaptive"):
        print(f"simulation {mode}...", flush=True)
        fcd = simuler(mode, a.seed, a.end, a.period, travail)
        pas = lire_fcd(fcd, 10000, a.period)
        fcd.unlink(missing_ok=True)
        t, k = titres[mode]
        data.append({"titre": t, "kpi": k, "pas": pas})
        print(f"   {len(pas)} pas de temps rejoues", flush=True)

    html = GABARIT.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    html = html.replace("__SEED__", str(a.seed))
    out.write_text(html, encoding="utf-8")
    print(f"Rejeu web : {out}  ({out.stat().st_size//1024} Ko)")


main()
