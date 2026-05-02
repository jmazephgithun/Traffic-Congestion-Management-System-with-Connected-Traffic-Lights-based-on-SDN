#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze iperf2 UDP logs (client or server).

Outputs JSON with:
- Bandwidth (Mb/s): mean, p95, p5, std
- Jitter (ms) & Loss (%): if present (server logs); null for client logs
- role_hint: "server" when jitter/loss detected, else "client"
Optionally writes per-interval CSV.

Usage:
  python3 analyze_iperf.py --log ctrl_server_noqos.log --out ctrl_noqos.json --csv ctrl_noqos.csv
  python3 analyze_iperf.py --log ctrl_server_qos.log  --out ctrl_qos.json   --csv ctrl_qos.csv
"""

import argparse, json, re, statistics, math, csv

PREFIX_RE = re.compile(
    r'^\s*\[\s*\d+\s*\]\s*'
    r'(?P<t0>\d+\.?\d*)\s*-\s*(?P<t1>\d+\.?\d*)\s*sec\s+'
    r'(?P<tx>\d+\.?\d*)\s*(?P<tx_unit>[KMG]?Bytes)\s+'
    r'(?P<bw>\d+\.?\d*)\s*(?P<bw_unit>[KMG]?bits/sec)'
    r'(?P<rest>.*)$'
)

BIT_FACT  = {"bits/sec":1, "Kbits/sec":1e3, "Mbits/sec":1e6, "Gbits/sec":1e9}

def to_mbps(bw, unit):
    f = BIT_FACT.get(unit)
    return (bw * f) / 1e6 if f else None

def parse_file(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        text = f.read()

    intervals, saw_j_or_l = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('[') and 'local ' in line and 'connected with' in line:
            continue
        if line.startswith('[ ID]') or line.startswith('-----') or 'Server listening on UDP port' in line:
            continue

        m = PREFIX_RE.match(line)
        if not m:
            continue

        g = m.groupdict()
        t0 = float(g['t0']); t1 = float(g['t1'])
        bw = float(g['bw']); bw_unit = g['bw_unit']
        bw_mbps = to_mbps(bw, bw_unit)
        rest = g['rest']

        # loss (X/Y (Z%))
        loss_pct = None
        m_loss = re.search(r'(\d+)\s*/\s*(\d+)\s*\(([\d\.]+)%\)', rest)
        if m_loss:
            loss_pct = float(m_loss.group(3))
            saw_j_or_l = True

        # jitter (with or without 'Jitter' label; tolerate order)
        jitter_ms = None
        m_j1 = re.search(r'(?i)\bjitter\b\s*([\d\.]+)\s*ms', rest)
        m_j2 = re.search(r'(^|\s)([\d\.]+)\s*ms(\s|$)', rest)
        if m_j1:
            jitter_ms = float(m_j1.group(1)); saw_j_or_l = True
        elif m_j2 and ('Bytes' not in rest and 'bits/sec' not in rest):  # avoid false positives
            jitter_ms = float(m_j2.group(2)); saw_j_or_l = True

        intervals.append({
            "t0": t0, "t1": t1,
            "bw_mbps": bw_mbps,
            "jitter_ms": jitter_ms,
            "loss_pct": loss_pct
        })

    role_hint = "server" if saw_j_or_l else "client"
    return {"intervals": intervals, "role_hint": role_hint}

def pctl(arr, p):
    if not arr: return None
    a = sorted(arr)
    k = (len(a)-1) * (p/100.0)
    f, c = math.floor(k), math.ceil(k)
    return a[int(k)] if f == c else a[f]*(c-k) + a[c]*(k-f)

def summarize(intervals):
    bw  = [i["bw_mbps"]   for i in intervals if i.get("bw_mbps")   is not None]
    jit = [i["jitter_ms"] for i in intervals if i.get("jitter_ms") is not None]
    los = [i["loss_pct"]  for i in intervals if i.get("loss_pct")  is not None]

    return {
        "samples": len(intervals),
        "duration_s": (intervals[-1]["t1"] - intervals[0]["t0"]) if intervals else 0.0,
        "bw_mbps_mean": statistics.mean(bw) if bw else None,
        "bw_mbps_p95":  pctl(bw, 95) if bw else None,
        "bw_mbps_p5":   pctl(bw, 5)  if bw else None,
        "bw_mbps_std":  statistics.pstdev(bw) if len(bw) > 1 else (0.0 if bw else None),
        "jitter_ms_mean": statistics.mean(jit) if jit else None,
        "jitter_ms_p95":  pctl(jit, 95) if jit else None,
        "loss_pct_mean":  statistics.mean(los) if los else None,
        "loss_pct_p95":   pctl(los, 95) if los else None,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--csv")
    args = ap.parse_args()

    parsed = parse_file(args.log)
    intervals = parsed["intervals"]
    role_hint = parsed["role_hint"]

    summary = summarize(intervals)
    summary["role_hint"] = role_hint
    summary["note"] = None
    if role_hint == "client" and (summary["jitter_ms_mean"] is None or summary["loss_pct_mean"] is None):
        summary["note"] = ("Client log detected: iperf2 prints UDP jitter & loss on the server side. "
                           "Throughput stats are valid; jitter/loss are null. "
                           "Use the server output to compute those KPIs.")

    out = {"summary": summary, "intervals": intervals}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as cf:
            w = csv.DictWriter(cf, fieldnames=["t0","t1","bw_mbps","jitter_ms","loss_pct"])
            w.writeheader()
            w.writerows(intervals)

    print(f"[analyze_iperf] Parsed {len(intervals)} intervals as {role_hint}. Wrote {args.out}")
    if args.csv: print(f"[analyze_iperf] CSV -> {args.csv}")
    if summary.get("note"): print("[analyze_iperf] NOTE:", summary["note"])

if __name__ == "__main__":
    main()
