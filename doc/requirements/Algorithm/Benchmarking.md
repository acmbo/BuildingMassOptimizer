# Benchmarking – Building Mass Generation Performance

## Goal

Measure the wall-clock time of `Individuum.build()` under controlled conditions
so that performance can be tracked and compared across codebase iterations.

---

## Comparison Strategy

Every benchmark run produces a **JSON result file** stored in
`benchmarks/results/`. File names encode the git commit hash and date:

```
benchmarks/results/2026-03-10_abc1234.json
```

A lightweight **compare script** (`benchmarks/compare.py`) loads two result
files and prints a side-by-side delta table (absolute ms and %).

This means:
- You can run benchmarks before and after an optimisation and immediately see
  whether the change helped.
- Results are committed together with the code change that caused them, so the
  history is always traceable in git.
- No external tooling required — plain JSON + stdlib.

---

## Scenarios

### S1 – Fixed-seed single build

**Purpose:** Establish a stable, deterministic baseline that can be reproduced
on any machine.

- Seed: `42`
- Params: standard reference footprint (40 × 30 m rectangle), 3.5 m floor
  height, 10 floors, 3 vertical + 2 horizontal subtractors, 7.5 m span.
- Repetitions: 20 (take median to reduce OS noise).
- Reported metrics: `median_ms`, `min_ms`, `max_ms`, `stdev_ms`.

### S2 – Subtractor count sweep

**Purpose:** Quantify how build time scales with the number of subtractors
(each one adds alignment work and at least one OCC boolean cut per floor).

- Seed: `0` (fixed so every count level is comparable).
- Same reference footprint + floor params as S1.
- Vary `n_total = n_vertical + n_horizontal` from **0** to **12** in steps of 1
  (split evenly: `n_vertical = ceil(n/2)`, `n_horizontal = floor(n/2)`).
- Repetitions per level: 10 (take median).
- Reported metrics per level: `n_total`, `median_ms`.
- Output includes a simple text table; the JSON array is suitable for plotting.

### S3 – 100-individuum batch (reproducible)

**Purpose:** Simulate one generation of an EA population and give a realistic
average.

- The 100 genomes are generated from a **fixed seed sequence** (`seed=7`):
  `rng = random.Random(7)` — the same `rng` object is passed to all 100
  `Individuum.create_random()` calls in order, so the genome population is
  always identical.
- Same reference footprint + floor params as S1, but with 3 vertical +
  3 horizontal subtractors (a realistic population member).
- Reported metrics: `mean_ms`, `median_ms`, `p95_ms`, `total_s`.

---

## Reference Parameters (shared across scenarios)

```python
REFERENCE_POLYGON = [
    (0.0,  0.0,  0.0),
    (40.0, 0.0,  0.0),
    (40.0, 30.0, 0.0),
    (0.0,  30.0, 0.0),
]
FLOOR_HEIGHT  = 3.5
NUM_FLOORS    = 10
SPAN_X        = 7.5
SPAN_Y        = 7.5
```

---

## Output Format

Each run writes one JSON file:

```json
{
  "meta": {
    "date": "2026-03-10",
    "git_commit": "abc1234",
    "git_branch": "main",
    "python": "3.13.x",
    "platform": "linux"
  },
  "s1_fixed_seed": {
    "seed": 42,
    "n_vertical": 3,
    "n_horizontal": 2,
    "repetitions": 20,
    "median_ms": 0.0,
    "min_ms": 0.0,
    "max_ms": 0.0,
    "stdev_ms": 0.0
  },
  "s2_subtractor_sweep": [
    {"n_total": 0, "median_ms": 0.0},
    {"n_total": 1, "median_ms": 0.0},
    "..."
  ],
  "s3_batch_100": {
    "population_seed": 7,
    "n_vertical": 3,
    "n_horizontal": 3,
    "count": 100,
    "mean_ms": 0.0,
    "median_ms": 0.0,
    "p95_ms": 0.0,
    "total_s": 0.0
  }
}
```

---

## File Layout

```
benchmarks/
├── run_benchmarks.py     # main entry point — runs all scenarios, writes JSON
├── compare.py            # loads two JSON result files, prints delta table
└── results/              # committed result snapshots
    └── <date>_<hash>.json
```

---

## Running

```bash
# Run benchmarks and save result
/home/acmbo/anaconda3/bin/conda run -n pyoccEnv python benchmarks/run_benchmarks.py

# Compare two runs
/home/acmbo/anaconda3/bin/conda run -n pyoccEnv python benchmarks/compare.py \
    benchmarks/results/2026-03-10_abc1234.json \
    benchmarks/results/2026-03-11_def5678.json
```

---

## Implementation Notes

- Use `time.perf_counter()` for wall-clock measurement (not `time.time()`).
- Warm up OCC by running one build before timing starts (JIT-style import
  costs in pythonocc can inflate the first call).
- The benchmark scripts live in `benchmarks/` and are **not collected by
  pytest** (no `test_` prefix, not under `test/`).
- `run_benchmarks.py` calls `subprocess.run(["git", "rev-parse", "--short",
  "HEAD"])` to embed the commit hash automatically.
- Keep the reference params above in a single `PARAMS` constant so all
  scenarios use exactly the same geometry.
