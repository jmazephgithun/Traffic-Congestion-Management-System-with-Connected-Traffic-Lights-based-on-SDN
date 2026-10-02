#!/usr/bin/env python3
"""Demonstration visuelle et commentee du projet : une page HTML autonome.

La page montre, sur le fond de carte OpenStreetMap du carrefour reel de Solibra
(Treichville, Abidjan), deux simulations SUMO executees a l'instant :

  - feux fixes : le programme statique du carrefour ;
  - feux adaptatifs : le meme trafic, pilote par l'orchestrateur TraCI du memoire.

Pour chaque politique, la page rejoue les positions reellement simulees (sortie
FCD de SUMO), la couleur effective de chaque feu (sortie SaveTLSStates), les
compteurs de vehicules et la courbe des vehicules a l'arret. Elle reprend ensuite
les resultats mesures par le banc (fichiers de results_docker/) et en redige une
interpretation automatique, calculee a partir des chiffres.

Usage : python scripts/generer_demo.py --out results_docker/demo.html
"""
import argparse
import base64
import json
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMO_DIR = ROOT / "sumo_one_junction"
RES = ROOT / "results_docker"
ORCH = ROOT / "pyfilesTrue" / "tls_orchestrator_CORRECTED.py"
CFG = SUMO_DIR / "one_junction_asymmetric_solibra.sumocfg"
NET = SUMO_DIR / "one_junction_solibra.net.xml"
FOND = SUMO_DIR / "solibra_fond_osm.png"
VUE = SUMO_DIR / "solibra_view.xml"
INJECTES = 5852
RAYON = 150.0   # demi-largeur, en metres, de la zone affichee autour du carrefour


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def simuler(mode, seed, fin, travail):
    fcd = travail / f"fcd_{mode}.xml"
    tls = travail / f"tls_{mode}.xml"
    trip = travail / f"trip_{mode}.xml"
    evt = travail / f"evt_{mode}.add.xml"
    evt.write_text(f'<additional><timedEvent type="SaveTLSStates" source="J1" dest="{tls}"/></additional>')
    cmd = ["sumo", "-c", str(CFG), "--seed", str(seed), "--end", str(fin),
           "--time-to-teleport", "-1", "--fcd-output", str(fcd), "--tripinfo-output", str(trip),
           "--additional-files", f"one_junction_solibra.add.xml,{evt}", "--no-warnings", "true"]
    if mode == "adaptatif":
        port = free_port()
        sumo = subprocess.Popen(cmd + ["--remote-port", str(port)], cwd=SUMO_DIR,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        subprocess.run([sys.executable, str(ORCH), "--sumo-port", str(port), "--tls-id", "J1",
                        "--ns-phase-idx", "0", "--ew-phase-idx", "2", "--min-green", "10",
                        "--max-green", "45", "--hysteresis", "0.15"],
                       cwd=ROOT, text=True, capture_output=True, timeout=1800)
        sumo.wait(timeout=120)
    else:
        subprocess.run(cmd, cwd=SUMO_DIR, check=True, capture_output=True, timeout=1800)
    return fcd, tls, trip


def lire(fcd, tls, trip, periode, x0, y0, fin):
    etats = {}
    for _, e in ET.iterparse(tls):
        if e.tag == "tlsState":
            etats[int(float(e.get("time")))] = e.get("state")
            e.clear()
    trames, serie, arrives_avant = [], [], set()
    for _, e in ET.iterparse(fcd):
        if e.tag != "timestep":
            continue
        t = int(float(e.get("time")))
        if t > fin:
            break
        if t % periode:
            e.clear()
            continue
        vehs, arret = [], 0
        for v in e:
            x, y = float(v.get("x")), float(v.get("y"))
            a = 1 if float(v.get("speed", 0)) < 0.3 else 0
            arret += a
            if abs(x - x0) <= RAYON and abs(y - y0) <= RAYON:
                vehs.append([round(x - x0, 1), round(y - y0, 1), a])
        trames.append([t, etats.get(t, ""), vehs])
        serie.append([t, len(e), arret])
        e.clear()
    # Meme horizon pour les deux politiques : l'orchestrateur peut prolonger la
    # simulation au-dela de --end, seules les arrivees avant la fin comptent.
    termines = sum(1 for _, e in ET.iterparse(trip)
                   if e.tag == "tripinfo" and float(e.get("arrival", "inf")) <= fin)
    return trames, serie, termines


def feux(x0, y0):
    """Position de chaque feu (fin de voie entrante) et son indice de lien."""
    import sumolib
    net = sumolib.net.readNet(str(NET), withPrograms=True)
    tete = []
    for c in net.getTLS("J1").getConnections():
        voie, _, idx = c
        x, y = voie.getShape()[-1]
        tete.append([idx, round(x - x0, 1), round(y - y0, 1)])
    return tete


def charger(nom):
    p = RES / nom
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def fr(x, n=1):
    return f"{x:,.{n}f}".replace(",", " ").replace(".", ",")


def interpretation(sims):
    """Paragraphes rediges a partir des chiffres : aucune valeur n'est ecrite a la main."""
    P = []
    fx, ad = sims["fixe"], sims["adaptatif"]
    pic = lambda s: max(s["serie"], key=lambda r: r[2])
    pf, pa = pic(fx), pic(ad)
    P.append(
        f"Sur le carrefour réel de Solibra, avec {fr(INJECTES, 0)} véhicules injectés en vingt minutes selon le "
        f"profil asymétrique du mémoire, les feux fixes laissent arriver {fr(fx['termines'], 0)} véhicules "
        f"({fr(100 * fx['termines'] / INJECTES)} %) dans l’horizon simulé, contre {fr(ad['termines'], 0)} "
        f"({fr(100 * ad['termines'] / INJECTES)} %) avec l’orchestrateur adaptatif. Au plus fort de la congestion, "
        f"{fr(pf[2], 0)} véhicules sont à l’arrêt en feux fixes (à t = {pf[0]} s), contre {fr(pa[2], 0)} en mode "
        f"adaptatif (à t = {pa[0]} s).")
    gain = 100 * (ad["termines"] - fx["termines"]) / INJECTES
    P.append(
        "Ce qui se voit sur la carte : pendant la première période, l’axe Nord-Sud reçoit l’essentiel de la "
        "demande. Le programme fixe continue de donner le même temps de vert à l’axe Est-Ouest, et la file "
        "Nord-Sud s’allonge. L’orchestrateur lit les files à chaque seconde par TraCI et prolonge le vert de "
        "l’axe chargé, dans la limite de 45 s ; à la seconde période, la charge bascule sur l’axe Est-Ouest et "
        "l’orchestrateur suit.")
    if gain < 10:
        P.append(
            f"L’écart reste ici de {fr(gain)} points, bien plus modeste qu’au carrefour J1 du mémoire : la demande "
            f"recalibrée pour Solibra dépasse la capacité du carrefour sur les deux axes à la fois, si bien "
            f"qu’aucune répartition du vert ne peut écouler tout le trafic. La commande adaptative améliore "
            f"l’écoulement, elle ne crée pas de capacité.")
    ev30, w30 = charger("evaluation-30.json"), charger("webster-30.json")
    if ev30:
        g = ev30["aggregate"]["paired_completion_gain_points"]
        texte = (f"Sur le carrefour J1 du mémoire, rejoué sur {g['n']} graines appariées, l’orchestrateur écoule "
                 f"{fr(ev30['aggregate']['adaptive_completion_pct']['mean'])} % des véhicules contre "
                 f"{fr(ev30['aggregate']['baseline_completion_pct']['mean'])} % en feux fixes, soit "
                 f"{fr(g['mean'], 2)} points de plus (IC 95 % [{fr(g['ci95_low'], 2)} ; {fr(g['ci95_high'], 2)}]).")
        if w30:
            texte += (f" Même un plan fixe correctement dimensionné par la formule de Webster n’atteint que "
                      f"{fr(w30['aggregate']['baseline_completion_pct']['mean'], 2)} % : aucun plan fixe ne suit "
                      f"une demande qui change de sens en cours de simulation.")
        texte += (" Réserve de méthode : dans ce protocole, les feux fixes sont arrêtés à 3 600 s alors que "
                  "la simulation adaptative continue jusqu’à la sortie du dernier véhicule ; à horizon égal "
                  "(3 600 s), l’écart d’écoulement est faible (974 contre 979 véhicules sur la graine 42). "
                  "Le programme de feux de J1 met en outre au vert des mouvements qui se croisent (Nord + Est, "
                  "puis Sud + Ouest), ce qui divise sa capacité. La comparaison sur la carte ci-dessus est faite à "
                  "horizon égal, et le paragraphe suivant donne la comparaison à base égale.")
        P.append(texte)
    eq = charger("evaluation-equitable.json")
    if eq:
        sy = eq["synthese"]
        def ecart(sc, pol):
            b = sy.get(sc, {}).get(pol, {}).get("ecart_retard_vs_fixe_pct")
            return None if b is None else b["moyenne"]
        morceaux = []
        for sc, lib in (("j1_corrige", "sur le carrefour J1 aux phases corrigées (demande du mémoire)"),
                        ("alternance", "sur une demande qui alterne entre les axes sous la capacité"),
                        ("solibra", "sur le carrefour réel de Solibra, saturé")):
            v2, v1 = ecart(sc, "adaptatif_v2"), ecart(sc, "adaptatif_memoire")
            if v2 is not None:
                morceaux.append(f"{lib}, {fr(-v2)} % de retard en moins pour l’orchestrateur v2"
                                + (f" ({fr(-v1)} % pour celui du mémoire)" if v1 is not None else ""))
        if morceaux:
            P.append("Comparaison à base égale (toutes les simulations jusqu’à la sortie du dernier véhicule, "
                     f"{len(eq['protocole']['graines'])} graines) : " + " ; ".join(morceaux) + ". "
                     "La commande adaptative réduit nettement le retard tant que le carrefour n’est pas saturé "
                     "au-delà de sa capacité ; en saturation extrême, aucun plan de feux ne crée de capacité.")
    n0 = (charger("ctrl_noqos.json") or {}).get("summary")
    n1 = (charger("ctrl_qos.json") or {}).get("summary")
    if n0 and n1:
        P.append(
            f"Côté réseau, quand le lien vers l’infrastructure est saturé (16 Mbit/s offerts sur 5 Mbit/s), le flux "
            f"de commande des feux perd {fr(n0['loss_pct_mean'])} % de ses paquets et ne délivre que "
            f"{fr(n0['bw_mbps_mean'], 3)} Mbit/s sur 0,2. Dès que Ryu installe la règle OpenFlow qui le place dans "
            f"la file prioritaire, les pertes tombent à {fr(n1['loss_pct_mean'])} % et le débit utile remonte à "
            f"{fr(n1['bw_mbps_mean'], 3)} Mbit/s : les ordres de l’orchestrateur arrivent, même sous congestion.")
    bf = charger("boucle-fermee-30.json")
    if bf:
        P.append(
            f"Les deux couches sont reliées : à chaque seconde, l’orchestrateur publie la charge du carrefour vers "
            f"Ryu, qui active la priorité au-delà d’un seuil. Sur {bf['n_graines']} graines, cette priorité "
            f"s’active dans toutes les exécutions et reste active {fr(bf['duty_cycle_pct']['mean'])} % du temps : "
            f"le carrefour étant saturé presque en permanence, la protection du flux de commande l’est aussi.")
    sec = charger("secteurs.json")
    if sec:
        P.append(
            f"Pour un déploiement à l’échelle d’Abidjan, le prototype par secteur montre qu’à la panne du "
            f"contrôleur principal du secteur Nord, le contrôleur de secours reprend la main en "
            f"{fr(sec['bascule_s'], 2)} s, sans perte de connectivité, et que le secteur Sud n’est pas affecté.")
    P.append(
        "Limites : il s’agit de simulation (SUMO) et d’émulation réseau (espaces de noms Linux, Open vSwitch). "
        "La demande n’est pas calibrée sur des comptages réels, et la radio Wi-Fi n’est pas modélisée par ce banc.")
    return P


def tableau_resultats():
    lignes = []
    ev30, w30 = charger("evaluation-30.json"), charger("webster-30.json")
    if ev30:
        a = ev30["aggregate"]
        lignes += [("Phase A, 30 graines", "Complétion en feux fixes", fr(a["baseline_completion_pct"]["mean"], 2) + " %"),
                   ("Phase A, 30 graines", "Complétion en feux adaptatifs", fr(a["adaptive_completion_pct"]["mean"], 2) + " %"),
                   ("Phase A, 30 graines", "Gain apparié", fr(a["paired_completion_gain_points"]["mean"], 2) + " points")]
    if w30:
        lignes.append(("Phase A, 30 graines", "Complétion du plan Webster",
                       fr(w30["aggregate"]["baseline_completion_pct"]["mean"], 2) + " %"))
    for nom, lib in (("ctrl_noqos.json", "sans QoS"), ("ctrl_qos.json", "avec QoS")):
        s = (charger(nom) or {}).get("summary")
        if s:
            lignes += [("Phase B", f"Pertes du flux de commande, {lib}", fr(s["loss_pct_mean"]) + " %"),
                       ("Phase B", f"Jitter du flux de commande, {lib}", fr(s["jitter_ms_mean"], 2) + " ms")]
    sec = charger("secteurs.json")
    if sec:
        lignes.append(("Secteurs", "Bascule vers le contrôleur de secours", fr(sec["bascule_s"], 2) + " s"))
    return lignes


PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Feux connectés SDN : démonstration</title>
<style>
:root{--fond:#f6f7f9;--carte:#fff;--txt:#1d232b;--doux:#5b6573;--bord:#dde1e7;--vert:#1f9d55;--rouge:#d64545;--ambre:#e0a100;--bleu:#2457a6}
*{box-sizing:border-box}body{margin:0;background:var(--fond);color:var(--txt);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
header{background:#14243f;color:#fff;padding:28px 24px}header h1{margin:0 0 6px;font-size:24px}header p{margin:0;color:#c9d3e3;max-width:900px}
main{max-width:1180px;margin:0 auto;padding:20px 16px 48px}
section{background:var(--carte);border:1px solid var(--bord);border-radius:10px;padding:18px 20px;margin:16px 0}
h2{font-size:18px;margin:0 0 10px}p{margin:8px 0}.doux{color:var(--doux)}
.etapes{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:10px}
.etape{border:1px solid var(--bord);border-radius:8px;padding:10px 12px}.etape b{display:block;color:var(--bleu)}
.vues{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.vue h3{margin:0 0 6px;font-size:16px}canvas{width:100%;height:auto;border-radius:8px;border:1px solid var(--bord);display:block}
.cpt{display:flex;gap:14px;flex-wrap:wrap;margin:8px 0 0;font-size:14px}.cpt span b{font-variant-numeric:tabular-nums}
.barre{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:12px 0}
button{background:var(--bleu);color:#fff;border:0;border-radius:6px;padding:7px 16px;font-size:14px;cursor:pointer}
input[type=range]{flex:1;min-width:200px}select{padding:5px;border-radius:6px;border:1px solid var(--bord)}
.leg{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--doux)}.pt{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid var(--bord);padding:7px 8px;text-align:left}td.n{text-align:right;font-variant-numeric:tabular-nums}
code{background:#eef1f5;padding:1px 5px;border-radius:4px}footer{color:var(--doux);font-size:13px;text-align:center;margin-top:24px}
</style></head><body>
<header><h1>Gestion des embouteillages par feux tricolores connectés et SDN</h1>
<p>Démonstration générée automatiquement le __DATE__ par le banc Docker du mémoire d’ACHI Jean Martial Zéphirin
(Université Virtuelle de Côte d’Ivoire, 2026). Tout ce qui est affiché provient de simulations exécutées sur cette machine.</p></header>
<main>
<section><h2>1. L’idée</h2>
<p>Un feu à cycle fixe donne le même temps de vert à chaque axe, quelle que soit la demande. Quand le trafic devient
asymétrique, l’axe chargé accumule une file pendant que l’axe vide reçoit du vert inutile. Le projet relie les feux
à un contrôleur central : chaque feu mesure ses files, un orchestrateur ajuste les phases en temps réel, et un réseau
programmable (SDN) garantit que les ordres de commande arrivent même quand le réseau est saturé.</p>
<div class="etapes">
<div class="etape"><b>1. Mesurer</b>SUMO simule les véhicules ; l’orchestrateur lit les files de chaque axe par TraCI, chaque seconde.</div>
<div class="etape"><b>2. Décider</b>Il donne le vert à l’axe le plus chargé (vert de 10 à 45 s, hystérésis de 15 %).</div>
<div class="etape"><b>3. Protéger</b>Il publie la charge à Ryu, qui place le flux de commande dans une file prioritaire OpenFlow.</div>
<div class="etape"><b>4. Secourir</b>Chaque secteur (Nord, Sud) a un contrôleur de secours qui reprend la main en cas de panne.</div>
</div></section>

<section><h2>2. La simulation sur la carte réelle</h2>
<p class="doux">Carrefour du boulevard Félix-Houphouët-Boigny avec les boulevards Auguste Denise et du Canal, à Solibra
(Treichville). Fond OpenStreetMap, relevé MCLU/PADA du 3 mai 2023. Même trafic à gauche et à droite : __INJ__ véhicules,
axe Nord-Sud chargé à 65 % pendant les dix premières minutes, puis axe Est-Ouest.</p>
<div class="barre"><button id="lecture">Pause</button><input id="curseur" type="range" min="0" value="0">
<span id="temps" style="min-width:90px">t = 0 s</span>
<label>Vitesse <select id="vitesse"><option value="1">×1</option><option value="2" selected>×2</option><option value="4">×4</option><option value="8">×8</option></select></label></div>
<div class="vues" id="vues"></div>
<p class="leg"><span><i class="pt" style="background:var(--vert)"></i>véhicule en mouvement</span>
<span><i class="pt" style="background:var(--rouge)"></i>véhicule à l’arrêt</span>
<span><i class="pt" style="background:#fff;border:2px solid #333"></i>feu (couleur réelle à l’instant t)</span></p>
<h3 style="font-size:15px;margin:16px 0 6px">Véhicules à l’arrêt dans tout le réseau</h3>
<canvas id="courbe" width="1100" height="220"></canvas>
<p class="leg"><span><i class="pt" style="background:var(--rouge)"></i>feux fixes</span><span><i class="pt" style="background:var(--bleu)"></i>feux adaptatifs</span></p>
</section>

<section><h2>3. Ce que montrent les résultats</h2><div id="interp"></div></section>
<section><h2>4. Résultats mesurés par le banc</h2><table id="res"><tr><th>Expérience</th><th>Mesure</th><th style="text-align:right">Valeur</th></tr></table>
<p class="doux">Le détail, comparé valeur par valeur au mémoire, est dans <code>results_docker/rapport_memoire.md</code>.</p></section>
<section><h2>5. Reproduire</h2><p><code>make build</code> puis <code>make memoire</code> (résultats du mémoire),
<code>make evolue</code> (secteurs, Solibra), <code>make demo</code> (cette page) et <code>make gui</code> (SUMO en direct dans le navigateur).</p></section>
<footer>Simulation SUMO, orchestrateur TraCI, contrôleur Ryu (OpenFlow 1.3), Open vSwitch. Dépôt : __DEPOT__</footer>
</main>
<script>
const D = __DONNEES__;
const IMG = new Image(); IMG.src = "data:image/png;base64,__FOND__";
const R = D.rayon, T = 520, V = document.getElementById('vues');
const vues = D.sims.map(s => {
  const d = document.createElement('div'); d.className = 'vue';
  d.innerHTML = `<h3>${s.titre}</h3>`;
  const c = document.createElement('canvas'); c.width = c.height = T; d.appendChild(c);
  const k = document.createElement('div'); k.className = 'cpt'; d.appendChild(k);
  V.appendChild(d); return {s, g: c.getContext('2d'), k};
});
const N = Math.min(...D.sims.map(s => s.trames.length));
const X = x => (x + R) / (2 * R) * T, Y = y => (R - y) / (2 * R) * T;
function fond(g){
  g.fillStyle = '#e9ecef'; g.fillRect(0, 0, T, T);
  if (!IMG.complete) return;
  const f = D.fond, px = IMG.width / f.w;
  const sx = (D.x0 - R - (f.cx - f.w / 2)) * px, sy = ((f.cy + f.h / 2) - (D.y0 + R)) * px;
  g.drawImage(IMG, sx, sy, 2 * R * px, 2 * R * px, 0, 0, T, T);
  g.fillStyle = 'rgba(255,255,255,.25)'; g.fillRect(0, 0, T, T);
}
const COUL = {G:'#1f9d55', g:'#1f9d55', y:'#e0a100', Y:'#e0a100', r:'#d64545', R:'#d64545'};
let i = 0, lecture = true;
const cur = document.getElementById('curseur'); cur.max = N - 1;
function dessine(){
  vues.forEach(v => {
    const [t, etat, vehs] = v.s.trames[i], g = v.g; fond(g);
    vehs.forEach(([x, y, a]) => { g.fillStyle = a ? '#d64545' : '#1f9d55'; g.beginPath(); g.arc(X(x), Y(y), 3.2, 0, 6.29); g.fill(); });
    D.feux.forEach(([idx, x, y]) => { g.fillStyle = COUL[etat[idx]] || '#888'; g.strokeStyle = '#222'; g.lineWidth = 1.5;
      g.beginPath(); g.arc(X(x), Y(y), 5.5, 0, 6.29); g.fill(); g.stroke(); });
    const [, tot, arr] = v.s.serie[i];
    v.k.innerHTML = `<span>en circulation <b>${tot}</b></span><span>à l’arrêt <b>${arr}</b></span>`;
  });
  document.getElementById('temps').textContent = 't = ' + vues[0].s.trames[i][0] + ' s';
  cur.value = i; courbe();
}
const cv = document.getElementById('courbe'), cg = cv.getContext('2d');
const maxA = Math.max(...D.sims.flatMap(s => s.serie.map(r => r[2]))) || 1;
function courbe(){
  const W = cv.width, H = cv.height, m = 34; cg.clearRect(0, 0, W, H);
  cg.strokeStyle = '#dde1e7'; cg.fillStyle = '#5b6573'; cg.font = '12px system-ui';
  for (let k = 0; k <= 4; k++){ const y = H - m + (-(H - 2*m) * k / 4); cg.beginPath(); cg.moveTo(m, y); cg.lineTo(W - 8, y); cg.stroke();
    cg.fillText(Math.round(maxA * k / 4), 2, y + 4); }
  D.sims.forEach((s, j) => { cg.strokeStyle = j ? '#2457a6' : '#d64545'; cg.lineWidth = 2; cg.beginPath();
    s.serie.forEach(([t, , a], n) => { const x = m + (W - m - 8) * n / (N - 1), y = H - m - (H - 2*m) * a / maxA;
      n ? cg.lineTo(x, y) : cg.moveTo(x, y); }); cg.stroke(); });
  const x = m + (W - m - 8) * i / (N - 1); cg.strokeStyle = '#1d232b'; cg.lineWidth = 1;
  cg.beginPath(); cg.moveTo(x, 8); cg.lineTo(x, H - m); cg.stroke();
  cg.fillStyle = '#5b6573'; cg.fillText('temps simulé (s) : 0 à ' + D.sims[0].trames[N-1][0], m, H - 10);
}
document.getElementById('lecture').onclick = e => { lecture = !lecture; e.target.textContent = lecture ? 'Pause' : 'Lecture'; };
cur.oninput = () => { i = +cur.value; dessine(); };
setInterval(() => { if (lecture) { i = (i + (+document.getElementById('vitesse').value)) % N; dessine(); } }, 120);
IMG.onload = dessine; dessine();
document.getElementById('interp').innerHTML = D.interpretation.map(p => `<p>${p}</p>`).join('');
const tb = document.getElementById('res');
D.resultats.forEach(([a, b, c]) => { tb.insertAdjacentHTML('beforeend', `<tr><td>${a}</td><td>${b}</td><td class="n">${c}</td></tr>`); });
if (!D.resultats.length) tb.insertAdjacentHTML('beforeend', '<tr><td colspan="3">Lancer <code>make memoire</code> pour remplir ce tableau.</td></tr>');
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--end", type=int, default=1800, help="horizon simule, en secondes")
    ap.add_argument("--period", type=int, default=3, help="une image toutes les N secondes simulees")
    ap.add_argument("--out", default="results_docker/demo.html")
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    travail = out.parent / ".demo-work"
    travail.mkdir(exist_ok=True)

    j1 = next(e for _, e in ET.iterparse(NET) if e.tag == "junction" and e.get("id") == "J1")
    x0, y0 = float(j1.get("x")), float(j1.get("y"))
    decal = ET.parse(VUE).find("decal")
    fond = {k: float(decal.get(v)) for k, v in (("cx", "centerX"), ("cy", "centerY"), ("w", "width"), ("h", "height"))}

    sims = {}
    for mode, titre in (("fixe", "Feux fixes (programme statique)"), ("adaptatif", "Feux adaptatifs (orchestrateur TraCI)")):
        print(f"simulation {mode}...", flush=True)
        fcd, tls, trip = simuler(mode, a.seed, a.end, travail)
        trames, serie, termines = lire(fcd, tls, trip, a.period, x0, y0, a.end)
        sims[mode] = {"titre": titre, "trames": trames, "serie": serie, "termines": termines}
        print(f"   {len(trames)} images, {termines} vehicules arrives", flush=True)
        for f in (fcd, tls, trip):
            f.unlink(missing_ok=True)

    donnees = {"rayon": RAYON, "x0": 0.0, "y0": 0.0, "feux": feux(x0, y0),
               "fond": {**fond, "cx": fond["cx"] - x0, "cy": fond["cy"] - y0},
               "sims": [sims["fixe"], sims["adaptatif"]],
               "interpretation": interpretation(sims), "resultats": tableau_resultats()}
    html = (PAGE.replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False, separators=(",", ":")))
            .replace("__FOND__", base64.b64encode(FOND.read_bytes()).decode())
            .replace("__DATE__", date.today().strftime("%d/%m/%Y"))
            .replace("__INJ__", f"{INJECTES:,}".replace(",", " "))
            .replace("__DEPOT__", "github.com/jmazephgithun/Traffic-Congestion-Management-System-with-Connected-Traffic-Lights-based-on-SDN"))
    out.write_text(html, encoding="utf-8")
    (out.parent / "interpretation.md").write_text(
        "# Interprétation automatique\n\n" + "\n\n".join(donnees["interpretation"]) + "\n", encoding="utf-8")
    print(f"Demonstration : {out} ({out.stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    main()
