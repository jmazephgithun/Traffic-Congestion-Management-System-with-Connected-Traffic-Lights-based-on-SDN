#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merge mobility (SUMO) + network (iperf) JSONs into a Markdown report.

Inputs:
  --sumo-baseline sumo_baseline.json
  --sumo-adaptive sumo_adaptive.json
  --ctrl-noqos    ctrl_noqos.json
  --ctrl-qos      ctrl_qos.json
Output:
  --out report.md
"""

import argparse, json

def loadj(p):
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)

def pct_delta(old, new):
    if old in (None, 0) or new is None: return None
    return (new - old) * 100.0 / old

def fmt(v, nd=3, unit=""):
    if v is None: return "—"
    if isinstance(v, float):
        s = f"{v:.{nd}f}"
    else:
        s = str(v)
    return s + (unit if unit else "")

def section(title):
    return f"# {title}\n\n"

def table(rows):
    # rows: list of [col1, col2, ...]
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    def line(r):
        return "| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(r))) + " |"
    sep = "| " + " | ".join("-"*widths[i] for i in range(len(widths))) + " |"
    out = [line(rows[0]), sep]
    out += [line(r) for r in rows[1:]]
    return "\n".join(out) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sumo-baseline", required=True)
    ap.add_argument("--sumo-adaptive", required=True)
    ap.add_argument("--ctrl-noqos", required=True)
    ap.add_argument("--ctrl-qos", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    sb = loadj(args.sumo_baseline)["summary"]
    sa = loadj(args.sumo_adaptive)["summary"]
    nb = loadj(args.ctrl_noqos)
    na = loadj(args.ctrl_qos)

    nb_sum = nb.get("summary", {})
    na_sum = na.get("summary", {})

    # --------- Mobility table ---------
    rows_m = [
        ["Metric", "Baseline", "Adaptive", "Δ% (Adaptive vs Baseline)"],
        ["Trips completed", fmt(sb.get("total_vehicles")), fmt(sa.get("total_vehicles")), "—"],
        ["Mean duration (s)", fmt(sb.get("duration_s_mean")), fmt(sa.get("duration_s_mean")), fmt(pct_delta(sb.get("duration_s_mean"), sa.get("duration_s_mean")), 2, "%")],
        ["P95 duration (s)", fmt(sb.get("duration_s_p95")), fmt(sa.get("duration_s_p95")), fmt(pct_delta(sb.get("duration_s_p95"), sa.get("duration_s_p95")), 2, "%")],
        ["Mean time loss (s)", fmt(sb.get("timeloss_s_mean")), fmt(sa.get("timeloss_s_mean")), fmt(pct_delta(sb.get("timeloss_s_mean"), sa.get("timeloss_s_mean")), 2, "%")],
        ["P95 time loss (s)", fmt(sb.get("timeloss_s_p95")), fmt(sa.get("timeloss_s_p95")), fmt(pct_delta(sb.get("timeloss_s_p95"), sa.get("timeloss_s_p95")), 2, "%")],
        ["Mean waiting (s)", fmt(sb.get("waiting_s_mean")), fmt(sa.get("waiting_s_mean")), fmt(pct_delta(sb.get("waiting_s_mean"), sa.get("waiting_s_mean")), 2, "%")],
        ["Throughput (veh/h)", fmt(sb.get("throughput_vph")), fmt(sa.get("throughput_vph")), fmt(pct_delta(sb.get("throughput_vph"), sa.get("throughput_vph")), 2, "%")],
        ["Mean speed (m/s)", fmt(sb.get("mean_speed_mps")), fmt(sa.get("mean_speed_mps")), fmt(pct_delta(sb.get("mean_speed_mps"), sa.get("mean_speed_mps")), 2, "%")],
    ]

    # --------- Network table (control flow) ---------
    rows_n = [
        ["Metric (UDP:9999, server)", "No QoS", "QoS", "Δ% (QoS vs No QoS)"],
        ["Mean jitter (ms)", fmt(nb_sum.get("jitter_ms_mean")), fmt(na_sum.get("jitter_ms_mean")), fmt(pct_delta(nb_sum.get("jitter_ms_mean"), na_sum.get("jitter_ms_mean")), 2, "%")],
        ["P95 jitter (ms)",  fmt(nb_sum.get("jitter_ms_p95")), fmt(na_sum.get("jitter_ms_p95")), fmt(pct_delta(nb_sum.get("jitter_ms_p95"), na_sum.get("jitter_ms_p95")), 2, "%")],
        ["Mean loss (%)",    fmt(nb_sum.get("loss_pct_mean")), fmt(na_sum.get("loss_pct_mean")), fmt(pct_delta(nb_sum.get("loss_pct_mean"), na_sum.get("loss_pct_mean")), 2, "%")],
        ["P95 loss (%)",     fmt(nb_sum.get("loss_pct_p95")),  fmt(na_sum.get("loss_pct_p95")),  fmt(pct_delta(nb_sum.get("loss_pct_p95"),  na_sum.get("loss_pct_p95")), 2, "%")],
        ["Mean bw (Mb/s)",   fmt(nb_sum.get("bw_mbps_mean")),  fmt(na_sum.get("bw_mbps_mean")),  fmt(pct_delta(nb_sum.get("bw_mbps_mean"),  na_sum.get("bw_mbps_mean")), 2, "%")],
    ]

    # notes if client logs were used
    notes = []
    if nb_sum.get("role_hint") == "client" or na_sum.get("role_hint") == "client":
        notes.append("Note: iperf2 prints UDP jitter & loss on the **server**. If you used client logs, jitter/loss will be null.")

    md = []
    md.append(section("Adaptive SDN Traffic-Light Control — Results Summary"))
    md.append("This report compares **Baseline (no orchestrator / no QoS)** vs **Adaptive (orchestrator + Ryu QoS)** on mobility and network KPIs.\n")
    md.append("## Mobility (SUMO — `tripinfo.xml`)\n")
    md.append(table(rows_m))
    md.append("\n## Network (Mininet/Ryu — control stream UDP:9999)\n")
    md.append(table(rows_n))
    if notes:
        md.append("\n> " + "\n> ".join(notes) + "\n")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    print(f"[merge_report] Wrote {args.out}")

if __name__ == "__main__":
    main()
