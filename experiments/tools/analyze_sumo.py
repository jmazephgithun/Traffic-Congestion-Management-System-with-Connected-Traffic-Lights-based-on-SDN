#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze SUMO tripinfo XML (+ optional statistics XML).

Computes mobility KPIs:
- total_vehicles, sim_begin_s, sim_end_s
- duration_s: mean/median/p95
- timeLoss_s: mean/p95
- waiting_s:  mean/p95
- routeLength_m: mean
- mean_speed_mps (routeLength/duration)
- throughput_vph (completed vehicles per hour)

Usage:
  python3 analyze_sumo.py --tripinfo ~/experiments/results/tripinfo_baseline.xml \
                          --out      ~/experiments/results/sumo_baseline.json
  # optionally:
  python3 analyze_sumo.py --tripinfo tripinfo.xml --statistics stats.xml --csv per_vehicle.csv --out out.json
"""

import argparse, json, math, statistics, xml.etree.ElementTree as ET

def pctl(arr, p):
    if not arr: return None
    a = sorted(arr)
    k = (len(a)-1) * (p/100.0)
    f, c = math.floor(k), math.ceil(k)
    return a[int(k)] if f == c else a[f]*(c-k) + a[c]*(k-f)

def parse_tripinfo(path):
    # SUMO tripinfo root: <root><tripinfo .../></root>
    duration, waiting, timeLoss, routeLen, arrival, depart = [], [], [], [], [], []
    # iterparse for low memory
    for ev, elem in ET.iterparse(path):
        if elem.tag.endswith('tripinfo'):
            d  = float(elem.get('duration', 'nan'))
            w  = float(elem.get('waitingTime', elem.get('waiting', 'nan')))
            tl = float(elem.get('timeLoss', 'nan'))
            rl = float(elem.get('routeLength', 'nan'))
            dep = float(elem.get('depart', 'nan'))
            arr = float(elem.get('arrival', elem.get('arrivalTime', 'nan')))
            if not math.isnan(d):  duration.append(d)
            if not math.isnan(w):  waiting.append(w)
            if not math.isnan(tl): timeLoss.append(tl)
            if not math.isnan(rl): routeLen.append(rl)
            if not math.isnan(dep): depart.append(dep)
            if not math.isnan(arr): arrival.append(arr)
            elem.clear()

    n = len(duration)
    if n == 0:
        return {
            "total_vehicles": 0,
            "sim_begin_s": None, "sim_end_s": None,
            "duration_s_mean": None, "duration_s_median": None, "duration_s_p95": None,
            "timeloss_s_mean": None, "timeloss_s_p95": None,
            "waiting_s_mean": None,  "waiting_s_p95": None,
            "routeLength_m_mean": None,
            "mean_speed_mps": None,
            "throughput_vph": None
        }

    dur_mean   = statistics.mean(duration)
    dur_med    = statistics.median(duration)
    dur_p95    = pctl(duration, 95)
    tl_mean    = statistics.mean(timeLoss) if timeLoss else 0.0
    tl_p95     = pctl(timeLoss, 95) if timeLoss else 0.0
    wt_mean    = statistics.mean(waiting) if waiting else 0.0
    wt_p95     = pctl(waiting, 95) if waiting else 0.0
    rl_mean    = statistics.mean(routeLen) if routeLen else None
    spd_mps    = (rl_mean / dur_mean) if (rl_mean and dur_mean) else None

    sim_begin  = min(depart) if depart else None
    sim_end    = max(arrival) if arrival else None
    horizon_h  = ((sim_end - sim_begin) / 3600.0) if (sim_end is not None and sim_begin is not None and sim_end>sim_begin) else None
    throughput = (n / horizon_h) if horizon_h else None

    return {
        "total_vehicles": n,
        "sim_begin_s": sim_begin, "sim_end_s": sim_end,
        "duration_s_mean": round(dur_mean, 4),
        "duration_s_median": round(dur_med, 4),
        "duration_s_p95": round(dur_p95, 4) if dur_p95 is not None else None,
        "timeloss_s_mean": round(tl_mean, 4) if tl_mean is not None else None,
        "timeloss_s_p95": round(tl_p95, 4) if tl_p95 is not None else None,
        "waiting_s_mean": round(wt_mean, 4) if wt_mean is not None else None,
        "waiting_s_p95": round(wt_p95, 4) if wt_p95 is not None else None,
        "routeLength_m_mean": round(rl_mean, 4) if rl_mean is not None else None,
        "mean_speed_mps": round(spd_mps, 4) if spd_mps is not None else None,
        "throughput_vph": round(throughput, 4) if throughput is not None else None
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tripinfo", required=True)
    ap.add_argument("--statistics")             # optional SUMO stats xml (not strictly needed)
    ap.add_argument("--csv")                    # optional per-vehicle dump later (not implemented; KPI-focused)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    summary = parse_tripinfo(args.tripinfo)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary}, f, indent=2)
    print(f"[analyze_sumo] Wrote {args.out} with {summary['total_vehicles']} trips.")

if __name__ == "__main__":
    main()
