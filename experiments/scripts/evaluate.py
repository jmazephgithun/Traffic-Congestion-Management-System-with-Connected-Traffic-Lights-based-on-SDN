#!/usr/bin/env python3
"""Campagne reproductible baseline/adaptatif, avec statistiques appariées."""
import argparse
import json
import math
import socket
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMO_DIR = ROOT / "sumo_one_junction"
CFG = SUMO_DIR / "one_junction_asymmetric.sumocfg"
ORCHESTRATOR = ROOT / "pyfilesTrue" / "tls_orchestrator_CORRECTED.py"
TOTAL_INJECTED = 1300


def parse_seeds(value):
    result = []
    for part in value.split(","):
        if "-" in part:
            start, end = map(int, part.split("-", 1))
            result.extend(range(start, end + 1))
        else:
            result.append(int(part))
    return list(dict.fromkeys(result))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def read_trips(path):
    rows = []
    for _, elem in ET.iterparse(path):
        if elem.tag.endswith("tripinfo"):
            rows.append({k: float(elem.get(k, "nan")) for k in ("duration", "waitingTime", "timeLoss")})
            elem.clear()
    return rows


def summarize(seed, rows):
    completed = len(rows)
    def mean(key):
        vals = [row[key] for row in rows if not math.isnan(row[key])]
        return round(statistics.mean(vals), 4) if vals else None
    return {"seed": seed, "completed": completed, "blocked": TOTAL_INJECTED - completed,
            "completion_pct": round(100 * completed / TOTAL_INJECTED, 4),
            "duration_mean_s": mean("duration"), "waiting_mean_s": mean("waitingTime"),
            "timeloss_mean_s": mean("timeLoss")}


def run(seed, adaptive, work):
    label = "adaptive" if adaptive else "baseline"
    trip = work / f"tripinfo_{label}_{seed}.xml"
    base = ["sumo", "-c", str(CFG), "--seed", str(seed), "--end", "3600",
            "--time-to-teleport", "-1", "--tripinfo-output", str(trip), "--no-warnings", "true"]
    if not adaptive:
        proc = subprocess.run(base, cwd=SUMO_DIR, text=True, capture_output=True, timeout=180)
        if proc.returncode:
            raise RuntimeError(proc.stderr[-2000:])
    else:
        port = free_port()
        sumo = subprocess.Popen(base + ["--remote-port", str(port)], cwd=SUMO_DIR,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(.5)
            cmd = [sys.executable, str(ORCHESTRATOR), "--sumo-port", str(port), "--tls-id", "J1",
                   "--ns-phase-idx", "0", "--ew-phase-idx", "2", "--min-green", "10",
                   "--max-green", "45", "--hysteresis", "0.15"]
            orch = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=240)
            if orch.returncode:
                raise RuntimeError(orch.stdout[-1000:] + orch.stderr[-1000:])
            if sumo.wait(timeout=30):
                raise RuntimeError((sumo.stderr.read() if sumo.stderr else "")[-2000:])
        finally:
            if sumo.poll() is None:
                sumo.terminate()
    result = summarize(seed, read_trips(trip))
    trip.unlink(missing_ok=True)
    return result


def ci95(values):
    if not values:
        return None
    mean = statistics.mean(values)
    half = 0 if len(values) == 1 else 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return {"mean": round(mean, 4), "ci95_low": round(mean-half, 4),
            "ci95_high": round(mean+half, 4), "n": len(values)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="42", help="Ex.: 42,1-29")
    parser.add_argument("--mode", choices=("baseline", "adaptive", "both"), default="both")
    parser.add_argument("--output", default="results_docker/evaluation.json")
    args = parser.parse_args()
    seeds = parse_seeds(args.seeds)
    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / ".evaluation-work"
    work.mkdir(exist_ok=True)
    baseline, adaptive = [], []
    for seed in seeds:
        if args.mode in ("baseline", "both"):
            print(f"baseline seed={seed}", flush=True); baseline.append(run(seed, False, work))
        if args.mode in ("adaptive", "both"):
            print(f"adaptive seed={seed}", flush=True); adaptive.append(run(seed, True, work))
    deltas = [a["completion_pct"] - b["completion_pct"] for b, a in zip(baseline, adaptive)]
    report = {"protocol": {"seeds": seeds, "paired": True, "injected_per_run": TOTAL_INJECTED},
              "baseline": baseline, "adaptive": adaptive,
              "aggregate": {"baseline_completion_pct": ci95([r["completion_pct"] for r in baseline]),
                            "adaptive_completion_pct": ci95([r["completion_pct"] for r in adaptive]),
                            "paired_completion_gain_points": ci95(deltas)}}
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["aggregate"], indent=2, ensure_ascii=False))
    print(f"Rapport: {out}")


if __name__ == "__main__":
    main()
