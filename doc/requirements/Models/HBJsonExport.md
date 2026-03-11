# HBJson Export – Requirements

## 1. Principle Summary

This feature adds an export pipeline that converts a `BuildingMass` into a
**Honeybee JSON (`.hbjson`)** file consumable by Ladybug Tools — specifically by
the Radiance-based daylight simulation workflow.

Each floor of the `BuildingMass` becomes one **Room** in the HBJson model.  The
six (or more, for non-convex solids) planar faces of each floor solid are
extracted from OCC topology, classified by outward-normal direction, and assigned
the correct `face_type` and `boundary_condition`.  Adjacent floor pairs share a
`Surface` boundary condition on their touching ceiling/floor face so that the
model is thermally and geometrically consistent.

The exporter produces a stand-alone file with no energy properties — only the
geometry and the radiance `type` stubs needed for a minimal valid Radiance model.
Optional per-room metadata (story identifier, display name) is written to support
downstream filtering.

---

## 2. Inputs

| Parameter | Type | Description |
|---|---|---|
| `mass` | `BuildingMass` | The building mass to export (may be subtracted). |
| `output_path` | `str` | File path for the output `.hbjson` file. |
| `identifier` | `str` | Model-level identifier (default: `"BuildingMass"`). |
| `display_name` | `str \| None` | Human-readable model name (default: `None` → omitted). |
| `tolerance` | `float` | Geometric tolerance in metres (default: `0.01`). |
| `units` | `str` | Unit system (default: `"Meters"`). |

### 2.1 Identifier sanitisation

Model, room, and face identifiers must match `^[.A-Za-z0-9_-]+$` (max 100
characters).  Any input string is sanitised by replacing illegal characters with
`_` and truncating to 100 characters before use.

---

## 3. Output Format — HBJson Schema

Schema package: `honeybee-schema` v2.0.4.  Only the fields required for a valid
Radiance model are written; all energy-only fields are omitted.

### 3.1 Top-level `Model`

```json
{
  "type": "Model",
  "identifier": "<identifier>",
  "display_name": "<display_name>",          // omitted if None
  "version": "0.0.0",
  "units": "Meters",
  "tolerance": 0.01,
  "angle_tolerance": 1.0,
  "rooms": [ ... ],
  "properties": {
    "type": "ModelProperties",
    "radiance": { "type": "ModelRadianceProperties" }
  }
}
```

### 3.2 `Room` (one per `FloorData`)

```json
{
  "type": "Room",
  "identifier": "<model_id>_floor_<index>",
  "display_name": "Floor <index>",
  "story": "floor_<index>",
  "multiplier": 1,
  "faces": [ ... ],
  "properties": {
    "type": "RoomPropertiesAbridged",
    "radiance": { "type": "RoomRadiancePropertiesAbridged" }
  }
}
```

`<index>` is the zero-based `FloorData.index` zero-padded to three digits
(e.g. `000`, `001`, …) so alphabetic sort equals numeric sort.

### 3.3 `Face` (one per planar face of the floor solid)

```json
{
  "type": "Face",
  "identifier": "<room_id>_face_<n>",
  "geometry": {
    "type": "Face3D",
    "boundary": [[x, y, z], ...]   // CCW when viewed from outside; metres
  },
  "face_type": "Wall | Floor | RoofCeiling",
  "boundary_condition": { ... },
  "properties": {
    "type": "FacePropertiesAbridged",
    "radiance": { "type": "FaceRadiancePropertiesAbridged" }
  }
}
```

#### Face type classification

The outward normal `n` of each face is computed from the vertex list using the
right-hand rule.  Classification uses the Z component of the unit normal:

| Condition | `face_type` |
|---|---|
| `n.z < -0.9` (mostly downward) | `"Floor"` |
| `n.z > +0.9` (mostly upward) | `"RoofCeiling"` |
| otherwise | `"Wall"` |

#### Boundary condition assignment

| Face | Condition |
|---|---|
| **Floor face of ground floor** (`index == 0`) | `{"type": "Ground"}` |
| **Ceiling face of top floor** | `{"type": "Outdoors", "sun_exposure": true, "wind_exposure": true}` |
| **Ceiling face of floor `i`** / **floor face of floor `i+1`** | `{"type": "Surface", "boundary_condition_objects": [adj_face_id, adj_room_id]}` |
| **All wall faces** | `{"type": "Outdoors", "sun_exposure": true, "wind_exposure": true}` |

Adjacency is **bidirectional**: the ceiling face of floor `i` references the
floor face of floor `i+1`, and vice versa.  Both faces must have the same vertex
sequence (one reversed relative to the other) so their normals are opposing.

#### Note on `sun_exposure` / `wind_exposure` field types

These two fields on the `Outdoors` boundary condition are **booleans** (`true` /
`false`) in `honeybee-schema` v2.x.  Older v1.x files used string enums
(`"SunExposed"` / `"NoSun"` and `"WindExposed"` / `"NoWind"`).

This exporter targets v2.x and always writes booleans:

```json
{ "type": "Outdoors", "sun_exposure": true, "wind_exposure": true }
```

All exterior walls and the top-floor ceiling are sun- and wind-exposed (`true`).
There is no case in a building mass where an outdoor face would be shaded or
sheltered at this stage of the pipeline — glazing and solar shading are out of
scope (see §9).

---

## 4. Algorithm

### 4.1 Face extraction from OCC solid

For each `FloorData.solid` (a `TopoDS_Shape`):

```
0. Compute the solid's bbox centroid (used for outward-normal verification).

1. Use TopExp_Explorer(solid, TopAbs_FACE) to iterate over all faces.
2. For each OCC face:
   a. Cast to TopoDS_Face via topods.Face().
   b. Obtain the outer wire via breptools.OuterWire(face).
   c. Extract ordered vertices using BRepTools_WireExplorer.
      → list of (x, y, z) tuples.
   d. Compute a trial normal using the cross-product of the first triangle:
        v0 = pts[1] - pts[0],  v1 = pts[2] - pts[0]
        n = normalise(cross(v0, v1))
   e. Check outward direction:
        to_face = face_centroid - solid_centroid
        if dot(n, to_face) < 0:
            pts = reversed(pts)
            n = recompute_normal(pts)
   f. Classify face_type from n.z (§3.3).
3. Collect all extracted faces as list[_RawFace(vertices, normal, face_type)].
```

> **Why centroid-based instead of `face.Orientation()`:**  The OCC orientation
> flag (`TopAbs_FORWARD` / `TopAbs_REVERSED`) depends on how the shell was
> internally assembled by `BRepPrimAPI_MakePrism` and `BRepAlgoAPI_Cut`.  In
> practice both the top and bottom faces of a prism share the same orientation
> flag, making the flag unreliable for distinguishing inward from outward
> normals.  The centroid dot-product test is topology-agnostic and correct for
> any closed solid.

### 4.2 Adjacency pairing

For a building with `N` floors:

```
For i in range(N - 1):
    ceiling_faces_i   = [f for f in raw_faces[i]   if f.face_type == "RoofCeiling"]
    floor_faces_i1    = [f for f in raw_faces[i+1]  if f.face_type == "Floor"]

    # Match by centroid proximity (within tolerance)
    for cf in ceiling_faces_i:
        for ff in floor_faces_i1:
            if distance(centroid(cf), centroid(ff)) < tolerance:
                mark cf as Surface → ff (in room i+1)
                mark ff as Surface → cf (in room i)
```

Because the floor solid of floor `i+1` is stacked directly on top of floor `i`,
each ceiling face of floor `i` has an exact geometric twin as the floor face of
floor `i+1`.  Centroid matching is used as a robust proxy for identity.

For subtracted masses, some ceiling/floor pairs may not exist (void above or
below).  Any unmatched ceiling-of-non-top-floor retains `"Outdoors"` as a safe
fallback (the void has already been cut by OCC, so no geometry is present).

### 4.3 Identifier assignment

```
model_id   = sanitise(identifier)
room_id    = f"{model_id}_floor_{index:03d}"
face_id    = f"{room_id}_face_{n:03d}"
```

All identifiers are sanitised before use (see §2.1).

### 4.4 Serialisation

```python
def export_to_hbjson(
    mass: BuildingMass,
    output_path: str,
    *,
    identifier: str = "BuildingMass",
    display_name: str | None = None,
    tolerance: float = 0.01,
    units: str = "Meters",
) -> dict:
    ...
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(model_dict, f, indent=2)
    return model_dict
```

The function returns the serialised `dict` so callers can inspect or further
modify it without re-reading the file.

---

## 5. APIs and Libraries Used

| Purpose | API / Module |
|---|---|
| Iterate over solid faces | `TopExp_Explorer(solid, TopAbs_FACE)` |
| Get outer wire of a face | `BRepTools.OuterWire(face)` |
| Extract ordered vertices | `wire_utils.extract_wire_loops(wire)` (existing) |
| Check face orientation | `face.Orientation()` → `TopAbs_FORWARD` or `TopAbs_REVERSED` |
| JSON serialisation | `json` (stdlib) |
| No external honeybee-schema dependency | Output is plain `dict` → `json.dump` |

> **No `honeybee-schema` Python package dependency is introduced.**  The exporter
> produces the JSON structure by hand from a `dict`, keeping the environment
> light and avoiding version-pinning issues.

---

## 6. Data Model — Internal

```
_RawFace  (internal, not exported)
├── vertices  : list[tuple[float, float, float]]
├── normal    : tuple[float, float, float]
└── face_type : str   ("Wall" | "Floor" | "RoofCeiling")

_PendingFace  (internal, not exported)
├── raw        : _RawFace
├── room_id    : str
├── face_id    : str
└── adj_face_id : str | None   (set during adjacency pairing)
    adj_room_id : str | None
```

---

## 7. File Layout

```
src/
└── models/
    └── hbjson_exporter.py        – export_to_hbjson(), _sanitise_id(),
                                    _extract_faces(), _pair_adjacencies(),
                                    _build_room_dict(), _build_model_dict()

test/
└── models/
    └── test_hbjson_exporter.py   – unit tests (see §8)

test/userInteraction/
└── test_hbjson_export.py         – manual test: build mass → export → print
                                    room/face counts and open file in editor
```

---

## 8. Complete Worked Example

The example below shows the **full HBJson output** for a minimal 2-floor building
with a 4 × 6 m rectangular footprint and 3 m floor height.

```
Footprint:  (0,0) → (4,0) → (4,6) → (0,6)   (XY plane)
Floor 0:    z = 0 … 3 m
Floor 1:    z = 3 … 6 m
```

Each floor solid is a rectangular box with 6 faces:
- 1 floor face (bottom, normal −Z)
- 1 ceiling face (top, normal +Z)
- 4 wall faces (normals ±X, ±Y)

Face identifiers follow the scheme `<model_id>_floor_<NNN>_face_<NNN>`.

```json
{
  "type": "Model",
  "identifier": "BuildingMass",
  "display_name": "2-floor example",
  "version": "0.0.0",
  "units": "Meters",
  "tolerance": 0.01,
  "angle_tolerance": 1.0,
  "properties": {
    "type": "ModelProperties",
    "radiance": { "type": "ModelRadianceProperties" }
  },
  "rooms": [

    {
      "type": "Room",
      "identifier": "BuildingMass_floor_000",
      "display_name": "Floor 0",
      "story": "floor_000",
      "multiplier": 1,
      "properties": {
        "type": "RoomPropertiesAbridged",
        "radiance": { "type": "RoomRadiancePropertiesAbridged" }
      },
      "faces": [

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_000_face_000",
          "face_type": "Floor",
          "boundary_condition": { "type": "Ground" },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,0,0],[0,6,0],[4,6,0],[4,0,0]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_000_face_001",
          "face_type": "RoofCeiling",
          "boundary_condition": {
            "type": "Surface",
            "boundary_condition_objects": [
              "BuildingMass_floor_001_face_000",
              "BuildingMass_floor_001"
            ]
          },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,0,3],[4,0,3],[4,6,3],[0,6,3]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_000_face_002",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,0,0],[4,0,0],[4,0,3],[0,0,3]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_000_face_003",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[4,0,0],[4,6,0],[4,6,3],[4,0,3]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_000_face_004",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[4,6,0],[0,6,0],[0,6,3],[4,6,3]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_000_face_005",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,6,0],[0,0,0],[0,0,3],[0,6,3]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        }

      ]
    },

    {
      "type": "Room",
      "identifier": "BuildingMass_floor_001",
      "display_name": "Floor 1",
      "story": "floor_001",
      "multiplier": 1,
      "properties": {
        "type": "RoomPropertiesAbridged",
        "radiance": { "type": "RoomRadiancePropertiesAbridged" }
      },
      "faces": [

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_001_face_000",
          "face_type": "Floor",
          "boundary_condition": {
            "type": "Surface",
            "boundary_condition_objects": [
              "BuildingMass_floor_000_face_001",
              "BuildingMass_floor_000"
            ]
          },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,0,3],[4,0,3],[4,6,3],[0,6,3]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_001_face_001",
          "face_type": "RoofCeiling",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,0,6],[0,6,6],[4,6,6],[4,0,6]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_001_face_002",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,0,3],[4,0,3],[4,0,6],[0,0,6]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_001_face_003",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[4,0,3],[4,6,3],[4,6,6],[4,0,6]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_001_face_004",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[4,6,3],[0,6,3],[0,6,6],[4,6,6]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        },

        {
          "type": "Face",
          "identifier": "BuildingMass_floor_001_face_005",
          "face_type": "Wall",
          "boundary_condition": { "type": "Outdoors", "sun_exposure": true, "wind_exposure": true },
          "geometry": {
            "type": "Face3D",
            "boundary": [[0,6,3],[0,0,3],[0,0,6],[0,6,6]]
          },
          "properties": {
            "type": "FacePropertiesAbridged",
            "radiance": { "type": "FaceRadiancePropertiesAbridged" }
          }
        }

      ]
    }

  ]
}
```

**Key adjacency observations from the example:**

- `floor_000_face_001` (ceiling of floor 0) references `floor_001_face_000` and room `floor_001`.
- `floor_001_face_000` (floor of floor 1) references `floor_000_face_001` and room `floor_000`.
- The two adjacent faces share the same Z=3 plane but have **opposing vertex orders**:
  - Ceiling of floor 0: `[0,0,3] → [4,0,3] → [4,6,3] → [0,6,3]`  (normal +Z from floor 0's perspective)
  - Floor of floor 1:   `[0,0,3] → [4,0,3] → [4,6,3] → [0,6,3]`  (identical vertices; normal −Z from floor 1's perspective — OCC returns the bottom face of floor 1 already wound downward)
- The `boundary_condition_objects` array is always `[adjacent_face_id, adjacent_room_id]` — **face first, room second**.

---

## 9. Testing Strategy

### 8.1 Unit tests  (`test/models/test_hbjson_exporter.py`)

**Green tests**

| Test | Checks |
|---|---|
| `test_single_floor_room_count` | 1-floor mass → model has exactly 1 room |
| `test_multi_floor_room_count` | N-floor mass → model has exactly N rooms |
| `test_room_face_count` | Each room of a box-shaped floor has exactly 6 faces |
| `test_face_type_classification` | Bottom face → `"Floor"`, top face → `"RoofCeiling"`, side faces → `"Wall"` |
| `test_ground_floor_bc` | Floor face of room `index=0` → `boundary_condition.type == "Ground"` |
| `test_top_floor_ceiling_bc` | Ceiling face of top room → `boundary_condition.type == "Outdoors"` |
| `test_adjacent_floor_ceiling_bc` | Ceiling of floor `i` → `Surface`; floor of floor `i+1` → `Surface`; identifiers cross-reference correctly |
| `test_wall_faces_outdoors` | All wall faces → `boundary_condition.type == "Outdoors"` |
| `test_identifier_sanitisation` | Spaces and slashes in identifier are replaced with `_` |
| `test_output_file_written` | After call, file exists and is valid JSON |
| `test_return_value_equals_file_content` | Returned `dict` matches parsed file content |
| `test_subtracted_mass_export` | Subtracted mass exports without error; room count == num_floors |
| `test_vertex_count_per_face` | Each Face3D boundary has ≥ 3 vertices |
| `test_model_type_field` | Top-level `"type"` == `"Model"` |
| `test_room_story_field` | Each room carries a `"story"` key of the form `"floor_NNN"` |

**Red tests**

| Test | Checks |
|---|---|
| `test_empty_mass_raises` | `BuildingMass` with 0 floors raises `ValueError` |
| `test_invalid_output_path_raises` | Non-existent parent directory raises `OSError` |

### 8.2 Visual / manual test  (`test/userInteraction/test_hbjson_export.py`)

Builds a default building mass (e.g. 20 × 30 m rectangle, 5 floors, 3.5 m
height), exports to `/tmp/test_building.hbjson`, and prints:
- total room count
- face count per room
- boundary condition summary (Outdoors / Ground / Surface counts)
- file path for manual inspection in a text editor or Grasshopper

---

## 9. Constraints and Assumptions

| Topic | Decision |
|---|---|
| **Convexity** | All floor solids produced by `BuildingMass.create()` are convex extruded prisms; subtractions via `BRepAlgoAPI_Cut` may produce non-convex solids. The extractor handles any number of planar faces. |
| **Curved faces** | OCC may produce small non-planar faces on Boolean-cut edges. These are skipped (face with < 3 vertices after extraction is discarded with a warning). |
| **Units** | All coordinates are in metres (OCC model units = metres). The HBJson `"units"` field is set to `"Meters"`. |
| **No windows** | No `Aperture` objects are generated. The building mass has no glazing data. |
| **No HVAC / energy** | Only radiance stubs are written; all energy properties are omitted. |
| **Floors with voids** | Subtracted floors may have multiple wire loops (outer + inner holes). Inner-loop faces are treated identically to outer-loop faces (classified and exported normally). |
| **Identifier length** | Room and face identifiers including padding will not exceed 100 characters for buildings with ≤ 999 floors and ≤ 999 faces per room. |

---

## 10. Open Questions / Future Extensions

| Topic | Note |
|---|---|
| **Window generation** | Apertures could be derived from the wall area and a window-to-wall ratio parameter. Not in scope here. |
| **Per-zone program type** | HBJson `RoomEnergyPropertiesAbridged.program_type` could map to building type (office, residential). Future extension. |
| **IDA ICE / EnergyPlus export** | The same face-extraction pipeline can drive an IFC or OSM export. The `_extract_faces()` helper is designed to be reused. |
| **Curved / sloped geometry** | If the mass ever includes sloped floors or arched elements, non-planar face handling (triangulation via `BRepMesh_IncrementalMesh`) will be required. |
| **Modifier sets** | Radiance modifier sets (glass, opaque material) can be assigned per room via `RoomRadiancePropertiesAbridged.modifier_set` once a material catalogue is defined. |
