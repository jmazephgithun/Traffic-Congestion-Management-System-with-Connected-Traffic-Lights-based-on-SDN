#!/usr/bin/env python3
"""Genere le fichier de flux du carrefour Solibra reel, meme profil 65/35 que
l'original mais volume multiplie pour retrouver un regime sature sur la
capacite reelle du carrefour (une voie par sens, contre le modele
synthetique). Voir README.md, section 3.0a, pour le calcul du facteur.

Usage : python3 scripts/gen_routes_solibra.py 4.5 > sumo_one_junction/routes_asymmetric_solibra.rou.xml
"""
import sys
mult = float(sys.argv[1])
base = {
 'fNS_p1':(0,600,250),'fSN_p1':(0,600,250),'fEW_p1':(0,600,75),'fWE_p1':(0,600,75),
 'fNS_p2':(600,1200,75),'fSN_p2':(600,1200,75),'fEW_p2':(600,1200,250),'fWE_p2':(600,1200,250),
}
routes = {'fNS_p1':('N2J1','J1toS'),'fSN_p1':('S2J1','J1toN'),'fEW_p1':('E2J1','J1toW'),'fWE_p1':('W2J1','J1toE'),
          'fNS_p2':('N2J1','J1toS'),'fSN_p2':('S2J1','J1toN'),'fEW_p2':('E2J1','J1toW'),'fWE_p2':('W2J1','J1toE')}
print('<routes>')
print('  <vType id="car" accel="2.0" decel="4.5" sigma="0.5" length="5" maxSpeed="13.9"/>')
tot=0
for fid,(b,e,n) in base.items():
    n2 = round(n*mult)
    tot += n2
    frm,to = routes[fid]
    print(f'  <flow id="{fid}" type="car" from="{frm}" to="{to}" begin="{b}" end="{e}" number="{n2}" departLane="best" departSpeed="max"/>')
print('</routes>')
print(f'<!-- total {tot} -->', file=sys.stderr)
