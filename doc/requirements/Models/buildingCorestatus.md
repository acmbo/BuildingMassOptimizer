# BuildingCore — Implementation Status

## Done

### New files created
| File | Status |
|---|---|
| `src/models/building_core.py` | Done — `BuildingCore` dataclass with validation and derived edge properties |
| `src/models/building_core_engine.py` | Done — `find_building_cores()` with centroid-first placement loop, column-grid snapping, convergence guard |
| `test/models/test_building_core.py` | Done — 37/37 tests passing |
| `test/userInteraction/test_building_core.py` | Done — visual test written; not yet run visually |

### Modified existing files
| File | Change | Status |
|---|---|---|
| `src/models/floor_data.py` | Added `cores: list = field(default_factory=list)` | Done |
| `src/models/building_mass.py` | Added `cores: list = field(default_factory=list)` | Done |
| `src/models/column_grid.py` | Extended `align_subtractor(sub, cores=None)` + added `_snap_to_cores()` | Done |
| `src/models/__init__.py` | Exported `BuildingCore`, `find_building_cores` | Done |

---

## Verified

### Tests passing
All 37 unit tests pass (`conda run -n pyoccEnv python -m pytest test/ -v` → 178/178 total).

Fix applied: `building_core_engine.py` used `topods_Edge` (removed in pythonocc 7.9.x).
Use `from OCC.Core.TopoDS import Edge as topods_Edge` instead.

### Remaining spec items (not yet implemented)
| Item | Location | Notes |
|---|---|---|
| `core_generation_enabled` flag | `IndividuumParams` | Spec §8 — boolean toggle for the core step; not yet added to `IndividuumParams` |
| Core propagation in `Individuum.build()` | `src/models/individuum.py` | `find_building_cores()` not yet called inside `build()`; must happen after `apply_subtractions()` when flag is True |
| ARCHITECTURE.md update | `src/ARCHITECTURE.md` | New module entries for `building_core.py` / `building_core_engine.py` not yet added |

---

## Next Steps (in order)

1. **Run the test suite** — resolve conda path and execute `test/models/test_building_core.py`.
2. **Fix any failing tests** — likely candidates: OCC edge-vertex extraction API (`topexp_FirstVertex` / `topexp_LastVertex`), field ordering in dataclasses.
3. **Add `core_generation_enabled` to `IndividuumParams`** and wire `find_building_cores()` into `Individuum.build()`.
4. **Update `src/ARCHITECTURE.md`** with the two new modules.
5. **Run full test suite** (`pytest test/ -v`) to confirm no regressions in existing tests.
6. **Run visual test** (`test/userInteraction/test_building_core.py`) to confirm geometry looks correct.
