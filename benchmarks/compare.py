"""
Benchmark Comparison
====================

Loads two JSON result files and prints a side-by-side delta table.

Usage:
    python benchmarks/compare.py benchmarks/results/A.json benchmarks/results/B.json

The second file is treated as "new" — positive delta means regression,
negative delta means improvement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def pct(old: float, new: float) -> str:
    if old == 0:
        return "  n/a"
    delta = (new - old) / old * 100
    return f"{delta:+.1f}%"


def arrow(old: float, new: float) -> str:
    if old == 0:
        return " "
    delta = (new - old) / old * 100
    if abs(delta) < 2:
        return "~"
    return "▲" if delta > 0 else "▼"  # ▲ = slower (regression), ▼ = faster


def row(label: str, old: float, new: float, unit: str = "ms") -> None:
    print(f"  {label:<30s}  {old:>9.2f} {unit}  {new:>9.2f} {unit}  "
          f"{pct(old, new):>8s}  {arrow(old, new)}")


def header(title: str) -> None:
    print(f"\n{'─' * 65}")
    print(f"  {title}")
    print(f"{'─' * 65}")
    print(f"  {'Metric':<30s}  {'OLD':>10s}  {'NEW':>10s}  {'DELTA':>8s}  ")
    print(f"{'─' * 65}")


def main(path_a: str, path_b: str) -> None:
    a = load(path_a)
    b = load(path_b)

    ma, mb = a["meta"], b["meta"]
    print(f"\nOLD  {ma['date']}  {ma['git_commit']}  ({ma['git_branch']})")
    print(f"NEW  {mb['date']}  {mb['git_commit']}  ({mb['git_branch']})")

    # S1
    s1a, s1b = a["s1_fixed_seed"], b["s1_fixed_seed"]
    header("S1 – Fixed-seed single build")
    row("median", s1a["median_ms"], s1b["median_ms"])
    row("min",    s1a["min_ms"],    s1b["min_ms"])
    row("max",    s1a["max_ms"],    s1b["max_ms"])
    row("stdev",  s1a["stdev_ms"],  s1b["stdev_ms"])

    # S2 – print each n_total level
    s2a = {r["n_total"]: r for r in a["s2_subtractor_sweep"]}
    s2b = {r["n_total"]: r for r in b["s2_subtractor_sweep"]}
    all_n = sorted(set(s2a) | set(s2b))
    header("S2 – Subtractor count sweep  (median ms per level)")
    for n in all_n:
        if n in s2a and n in s2b:
            row(f"n={n}", s2a[n]["median_ms"], s2b[n]["median_ms"])
        elif n in s2a:
            print(f"  n={n:<29}  {s2a[n]['median_ms']:>9.2f} ms  {'(missing)':>10s}")
        else:
            print(f"  n={n:<29}  {'(missing)':>10s}  {s2b[n]['median_ms']:>9.2f} ms")

    # S3
    s3a, s3b = a["s3_batch_100"], b["s3_batch_100"]
    header("S3 – 100-individuum batch")
    row("mean",    s3a["mean_ms"],   s3b["mean_ms"])
    row("median",  s3a["median_ms"], s3b["median_ms"])
    row("p95",     s3a["p95_ms"],    s3b["p95_ms"])
    row("total",   s3a["total_s"],   s3b["total_s"], unit=" s")

    print(f"\n{'─' * 65}")
    print("  ▲ = slower (regression)   ▼ = faster (improvement)   ~ = <2% change")
    print()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python benchmarks/compare.py <old.json> <new.json>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
