"""
Benchmark: Building Mass Generation Performance
===============================================

Runs three scenarios and writes a JSON result file to benchmarks/results/.

Usage:
    /home/acmbo/anaconda3/bin/conda run -n pyoccEnv python benchmarks/run_benchmarks.py
"""

from __future__ import annotations

import json
import math
import random
import statistics
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow imports from src/
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from models.individuum import Individuum, IndividuumParams  # noqa: E402

# ---------------------------------------------------------------------------
# Reference parameters (shared across all scenarios)
# ---------------------------------------------------------------------------

REFERENCE_POLYGON = [
    (0.0,  0.0,  0.0),
    (40.0, 0.0,  0.0),
    (40.0, 30.0, 0.0),
    (0.0,  30.0, 0.0),
]

BASE_PARAMS = dict(
    polygon_points=REFERENCE_POLYGON,
    floor_height=3.5,
    num_floors=10,
    span_x=7.5,
    span_y=7.5,
)


def make_params(n_vertical: int, n_horizontal: int) -> IndividuumParams:
    return IndividuumParams(n_vertical=n_vertical, n_horizontal=n_horizontal, **BASE_PARAMS)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def time_build(ind: Individuum) -> float:
    """Return wall-clock ms for one ind.build() call."""
    t0 = time.perf_counter()
    ind.build()
    return (time.perf_counter() - t0) * 1000.0


def warmup() -> None:
    """One throwaway build to let pythonocc finish its lazy initialisation."""
    print("  warming up OCC...", end=" ", flush=True)
    ind = Individuum.create_random(make_params(1, 1), rng=random.Random(0))
    ind.build()
    print("done")


def git_info() -> tuple[str, str]:
    """Return (short_hash, branch). Falls back to 'unknown' on error."""
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True,
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL, text=True,
        ).strip()
    except Exception:
        sha, branch = "unknown", "unknown"
    return sha, branch


# ---------------------------------------------------------------------------
# S1 – Fixed-seed single build
# ---------------------------------------------------------------------------

def run_s1(reps: int = 20) -> dict:
    print(f"\n[S1] Fixed-seed single build  (seed=42, reps={reps})")
    params = make_params(n_vertical=3, n_horizontal=2)
    rng = random.Random(42)
    ind = Individuum.create_random(params, rng=rng)

    times: list[float] = []
    for i in range(reps):
        ms = time_build(ind)
        times.append(ms)
        print(f"  rep {i+1:>2}/{reps}  {ms:.1f} ms")

    result = {
        "seed": 42,
        "n_vertical": 3,
        "n_horizontal": 2,
        "repetitions": reps,
        "median_ms": round(statistics.median(times), 3),
        "min_ms":    round(min(times), 3),
        "max_ms":    round(max(times), 3),
        "stdev_ms":  round(statistics.stdev(times), 3),
    }
    print(f"  -> median {result['median_ms']} ms  "
          f"(min {result['min_ms']}, max {result['max_ms']}, "
          f"stdev {result['stdev_ms']})")
    return result


# ---------------------------------------------------------------------------
# S2 – Subtractor count sweep
# ---------------------------------------------------------------------------

def run_s2(max_n: int = 12, reps_per_level: int = 10) -> list[dict]:
    print(f"\n[S2] Subtractor count sweep  (n=0..{max_n}, reps/level={reps_per_level})")
    rows: list[dict] = []
    for n in range(max_n + 1):
        n_v = math.ceil(n / 2)
        n_h = math.floor(n / 2)
        params = make_params(n_vertical=n_v, n_horizontal=n_h)
        rng = random.Random(0)
        ind = Individuum.create_random(params, rng=rng)

        times: list[float] = []
        for _ in range(reps_per_level):
            times.append(time_build(ind))

        median_ms = round(statistics.median(times), 3)
        rows.append({"n_total": n, "n_vertical": n_v, "n_horizontal": n_h, "median_ms": median_ms})
        print(f"  n={n:>2}  (v={n_v}, h={n_h})  median={median_ms:.1f} ms")

    return rows


# ---------------------------------------------------------------------------
# S3 – 100-individuum batch (reproducible)
# ---------------------------------------------------------------------------

def run_s3(count: int = 100) -> dict:
    print(f"\n[S3] Batch of {count} random individuums  (population_seed=7)")
    params = make_params(n_vertical=3, n_horizontal=3)
    # Single rng for the whole population — same genome sequence every run
    rng = random.Random(7)

    individuals = [Individuum.create_random(params, rng=rng) for _ in range(count)]

    times: list[float] = []
    for i, ind in enumerate(individuals):
        ms = time_build(ind)
        times.append(ms)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{count}  last={ms:.1f} ms  running_mean={statistics.mean(times):.1f} ms")

    sorted_times = sorted(times)
    p95_idx = int(math.ceil(0.95 * count)) - 1
    result = {
        "population_seed": 7,
        "n_vertical": 3,
        "n_horizontal": 3,
        "count": count,
        "mean_ms":   round(statistics.mean(times), 3),
        "median_ms": round(statistics.median(times), 3),
        "p95_ms":    round(sorted_times[p95_idx], 3),
        "total_s":   round(sum(times) / 1000.0, 3),
    }
    print(f"  -> mean {result['mean_ms']} ms  median {result['median_ms']} ms  "
          f"p95 {result['p95_ms']} ms  total {result['total_s']} s")
    return result


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    sha, branch = git_info()
    today = date.today().isoformat()
    print(f"BuildingMassOptimizer – performance benchmark")
    print(f"  date={today}  commit={sha}  branch={branch}")

    warmup()

    s1 = run_s1()
    s2 = run_s2()
    s3 = run_s3()

    payload = {
        "meta": {
            "date": today,
            "git_commit": sha,
            "git_branch": branch,
            "python": sys.version.split()[0],
            "platform": sys.platform,
        },
        "s1_fixed_seed": s1,
        "s2_subtractor_sweep": s2,
        "s3_batch_100": s3,
    }

    out_dir = ROOT / "benchmarks" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today}_{sha}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults saved → {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
