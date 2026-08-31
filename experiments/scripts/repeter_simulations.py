#!/usr/bin/env python3
"""Rejoue les scenarios Baseline et Adaptatif sur plusieurs graines aleatoires."""
import json, math, socket, statistics, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path("/home/curtis_dogbo/Projects/Memoire/memoire_3/experiments/experiments")
SUMO_DIR = ROOT / "sumo_one_junction"
SUMO_BIN = Path("/home/curtis_dogbo/Projects/Memoire/.venv/bin/sumo")
PY = Path("/home/curtis_dogbo/Projects/Memoire/.venv/bin/python")
ORCH = ROOT / "pyfilesTrue" / "tls_orchestrator_CORRECTED.py"
OUT_DIR = ROOT / "results" / "seeds"
CFG = SUMO_DIR / "one_junction_asymmetric.sumocfg"
TOTAL_INJECTE = 1300

SEEDS = [42] + list(range(1, 30))  # 30 graines au total, 42 inclus (deja documentee)

def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def parse_tripinfo(path):
    duration, waiting, timeloss = [], [], []
    for _, elem in ET.iterparse(path):
        if elem.tag.endswith("tripinfo"):
            duration.append(float(elem.get("duration")))
            waiting.append(float(elem.get("waitingTime")))
            timeloss.append(float(elem.get("timeLoss")))
            elem.clear()
    return duration, waiting, timeloss

def run_baseline(seed):
    trip = OUT_DIR / f"tripinfo_baseline_{seed}.xml"
    subprocess.run(
        [str(SUMO_BIN), "-c", str(CFG), "--end", "3600", "--seed", str(seed),
         "--time-to-teleport", "-1", "--tripinfo-output", str(trip),
         "--no-warnings", "true"],
        cwd=SUMO_DIR, capture_output=True, text=True, timeout=120,
    )
    duration, waiting, timeloss = parse_tripinfo(trip)
    completed = len(duration)
    blocked = TOTAL_INJECTE - completed
    trip.unlink(missing_ok=True)
    return {
        "seed": seed, "completed": completed, "blocked": blocked,
        "pct_blocked": round(100 * blocked / TOTAL_INJECTE, 4),
        "duration_mean": round(statistics.mean(duration), 3) if duration else None,
        "waiting_mean": round(statistics.mean(waiting), 3) if waiting else None,
        "timeloss_mean": round(statistics.mean(timeloss), 3) if timeloss else None,
    }

def run_adaptive(seed):
    port = free_port()
    trip = OUT_DIR / f"tripinfo_adaptive_{seed}.xml"
    sumo_proc = subprocess.Popen(
        [str(SUMO_BIN), "-c", str(CFG), "--remote-port", str(port), "--seed", str(seed),
         "--time-to-teleport", "-1", "--tripinfo-output", str(trip)],
        cwd=SUMO_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1.0)
    orch = subprocess.run(
        [str(PY), str(ORCH), "--sumo-port", str(port), "--tls-id", "J1",
         "--ns-phase-idx", "0", "--ew-phase-idx", "2",
         "--min-green", "10", "--max-green", "45", "--hysteresis", "0.15"],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    sumo_proc.wait(timeout=30)
    switches_ns = orch.stdout.count("Switch -> NS_GREEN")
    switches_ew = orch.stdout.count("Switch -> EW_GREEN")
    sim_end = None
    m = None
    for line in reversed(orch.stdout.splitlines()):
        if "SUMO finished" in line:
            continue
        if line.strip().startswith("[orchestrator] [") and "queues" in line:
            try:
                m = float(line.split("[")[2].split("s]")[0])
            except Exception:
                pass
            if m is not None:
                break
    duration, waiting, timeloss = parse_tripinfo(trip)
    completed = len(duration)
    blocked = TOTAL_INJECTE - completed
    trip.unlink(missing_ok=True)
    return {
        "seed": seed, "completed": completed, "blocked": blocked,
        "sim_end_s": m,
        "switches_total": switches_ns + switches_ew,
        "duration_mean": round(statistics.mean(duration), 3) if duration else None,
        "waiting_mean": round(statistics.mean(waiting), 3) if waiting else None,
        "timeloss_mean": round(statistics.mean(timeloss), 3) if timeloss else None,
    }

def ci95(values):
    n = len(values)
    if n < 2:
        return None
    m = statistics.mean(values)
    sd = statistics.stdev(values)
    t_table = {29: 2.045, 30: 2.042, 28: 2.048}
    t = t_table.get(n, 2.045)
    half = t * sd / math.sqrt(n)
    return {"mean": round(m, 4), "std": round(sd, 4), "n": n,
            "ci95_low": round(m - half, 4), "ci95_high": round(m + half, 4)}

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    baseline_results, adaptive_results = [], []
    for i, seed in enumerate(SEEDS, 1):
        print(f"[{i}/{len(SEEDS)}] baseline seed={seed}", flush=True)
        baseline_results.append(run_baseline(seed))
    for i, seed in enumerate(SEEDS, 1):
        print(f"[{i}/{len(SEEDS)}] adaptive seed={seed}", flush=True)
        adaptive_results.append(run_adaptive(seed))

    summary = {
        "n_seeds": len(SEEDS),
        "seeds": SEEDS,
        "baseline": {
            "runs": baseline_results,
            "blocked_count": ci95([r["blocked"] for r in baseline_results]),
            "pct_blocked": ci95([r["pct_blocked"] for r in baseline_results]),
            "duration_mean": ci95([r["duration_mean"] for r in baseline_results if r["duration_mean"] is not None]),
        },
        "adaptive": {
            "runs": adaptive_results,
            "blocked_count": ci95([r["blocked"] for r in adaptive_results]),
            "all_cleared": all(r["blocked"] == 0 for r in adaptive_results),
            "sim_end_s": ci95([r["sim_end_s"] for r in adaptive_results if r["sim_end_s"] is not None]),
            "duration_mean": ci95([r["duration_mean"] for r in adaptive_results if r["duration_mean"] is not None]),
            "switches_total": ci95([r["switches_total"] for r in adaptive_results]),
        },
    }
    out = ROOT / "results" / "repetitions_30_graines.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEcrit : {out}")
    print(json.dumps({
        "baseline_pct_blocked": summary["baseline"]["pct_blocked"],
        "adaptive_all_cleared": summary["adaptive"]["all_cleared"],
        "adaptive_sim_end_s": summary["adaptive"]["sim_end_s"],
    }, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
