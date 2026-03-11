"""
Unit tests for hbjson_exporter.

Run from project root:
    conda run -n pyoccEnv python -m pytest test/models/test_hbjson_exporter.py -v
"""
import sys
import os
import json
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from models import BuildingMass
from models.hbjson_exporter import export_to_hbjson, _sanitise_id


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

RECT_POLYGON = [(0, 0, 0), (4, 0, 0), (4, 6, 0), (0, 6, 0)]
FLOOR_HEIGHT = 3.0


def make_mass(num_floors: int = 3) -> BuildingMass:
    return BuildingMass.create(RECT_POLYGON, FLOOR_HEIGHT, num_floors)


def export_temp(mass: BuildingMass, **kwargs) -> tuple[dict, str]:
    """Export to a temp file and return (model_dict, path)."""
    with tempfile.NamedTemporaryFile(suffix=".hbjson", delete=False) as f:
        path = f.name
    model = export_to_hbjson(mass, path, **kwargs)
    return model, path


# ---------------------------------------------------------------------------
# Green tests
# ---------------------------------------------------------------------------

class TestRoomCount(unittest.TestCase):

    def test_single_floor_room_count(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass)
        os.unlink(path)
        self.assertEqual(len(model["rooms"]), 1)

    def test_multi_floor_room_count(self):
        n = 5
        mass = make_mass(num_floors=n)
        model, path = export_temp(mass)
        os.unlink(path)
        self.assertEqual(len(model["rooms"]), n)


class TestFaceCount(unittest.TestCase):

    def test_rectangular_box_has_six_faces(self):
        """A simple rectangular floor solid should produce exactly 6 faces."""
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass)
        os.unlink(path)
        self.assertEqual(len(model["rooms"][0]["faces"]), 6)

    def test_all_faces_have_at_least_three_vertices(self):
        mass = make_mass(num_floors=2)
        model, path = export_temp(mass)
        os.unlink(path)
        for room in model["rooms"]:
            for face in room["faces"]:
                self.assertGreaterEqual(
                    len(face["geometry"]["boundary"]), 3,
                    msg=f"Face {face['identifier']} has fewer than 3 vertices",
                )


class TestFaceTypeClassification(unittest.TestCase):

    def _get_faces_by_type(self, room: dict) -> dict:
        result = {"Floor": [], "RoofCeiling": [], "Wall": []}
        for face in room["faces"]:
            result[face["face_type"]].append(face)
        return result

    def test_one_floor_face_per_room(self):
        mass = make_mass(num_floors=2)
        model, path = export_temp(mass)
        os.unlink(path)
        for room in model["rooms"]:
            typed = self._get_faces_by_type(room)
            self.assertEqual(len(typed["Floor"]), 1,
                             msg=f"Room {room['identifier']} should have 1 Floor face")

    def test_one_ceiling_face_per_room(self):
        mass = make_mass(num_floors=2)
        model, path = export_temp(mass)
        os.unlink(path)
        for room in model["rooms"]:
            typed = self._get_faces_by_type(room)
            self.assertEqual(len(typed["RoofCeiling"]), 1,
                             msg=f"Room {room['identifier']} should have 1 RoofCeiling face")

    def test_four_wall_faces_for_rectangle(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass)
        os.unlink(path)
        typed = self._get_faces_by_type(model["rooms"][0])
        self.assertEqual(len(typed["Wall"]), 4)


class TestBoundaryConditions(unittest.TestCase):

    def _faces_by_type(self, room):
        result = {}
        for face in room["faces"]:
            result.setdefault(face["face_type"], []).append(face)
        return result

    def test_ground_floor_floor_face_is_ground(self):
        mass = make_mass(num_floors=2)
        model, path = export_temp(mass)
        os.unlink(path)
        ground_room = model["rooms"][0]
        floor_face = self._faces_by_type(ground_room)["Floor"][0]
        self.assertEqual(floor_face["boundary_condition"]["type"], "Ground")

    def test_top_floor_ceiling_is_outdoors(self):
        mass = make_mass(num_floors=3)
        model, path = export_temp(mass)
        os.unlink(path)
        top_room = model["rooms"][-1]
        ceiling_face = self._faces_by_type(top_room)["RoofCeiling"][0]
        self.assertEqual(ceiling_face["boundary_condition"]["type"], "Outdoors")

    def test_all_wall_faces_are_outdoors(self):
        mass = make_mass(num_floors=3)
        model, path = export_temp(mass)
        os.unlink(path)
        for room in model["rooms"]:
            for face in self._faces_by_type(room).get("Wall", []):
                self.assertEqual(
                    face["boundary_condition"]["type"], "Outdoors",
                    msg=f"Wall face {face['identifier']} should be Outdoors",
                )

    def test_outdoors_has_sun_and_wind_exposure(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass)
        os.unlink(path)
        for room in model["rooms"]:
            for face in room["faces"]:
                bc = face["boundary_condition"]
                if bc["type"] == "Outdoors":
                    self.assertIs(bc["sun_exposure"], True)
                    self.assertIs(bc["wind_exposure"], True)


class TestAdjacency(unittest.TestCase):

    def _faces_by_type(self, room):
        result = {}
        for face in room["faces"]:
            result.setdefault(face["face_type"], []).append(face)
        return result

    def _face_by_id(self, model, face_id):
        for room in model["rooms"]:
            for face in room["faces"]:
                if face["identifier"] == face_id:
                    return face
        return None

    def test_intermediate_floor_ceiling_is_surface(self):
        """Ceiling of floor 0 in a 3-floor building must be Surface."""
        mass = make_mass(num_floors=3)
        model, path = export_temp(mass)
        os.unlink(path)
        room_0 = model["rooms"][0]
        ceiling = self._faces_by_type(room_0)["RoofCeiling"][0]
        self.assertEqual(ceiling["boundary_condition"]["type"], "Surface")

    def test_intermediate_floor_face_of_upper_room_is_surface(self):
        """Floor face of floor 1 in a 3-floor building must be Surface."""
        mass = make_mass(num_floors=3)
        model, path = export_temp(mass)
        os.unlink(path)
        room_1 = model["rooms"][1]
        floor_face = self._faces_by_type(room_1)["Floor"][0]
        self.assertEqual(floor_face["boundary_condition"]["type"], "Surface")

    def test_adjacency_cross_reference_is_consistent(self):
        """
        Ceiling of floor i and floor face of floor i+1 must reference each other:
        - ceiling.boundary_condition_objects[0] == floor_above face id
        - floor_above.boundary_condition_objects[0] == ceiling face id
        """
        mass = make_mass(num_floors=2)
        model, path = export_temp(mass)
        os.unlink(path)

        room_0, room_1 = model["rooms"][0], model["rooms"][1]
        ceiling = self._faces_by_type(room_0)["RoofCeiling"][0]
        floor_above = self._faces_by_type(room_1)["Floor"][0]

        c_bc_objects = ceiling["boundary_condition"]["boundary_condition_objects"]
        f_bc_objects = floor_above["boundary_condition"]["boundary_condition_objects"]

        # Ceiling references floor_above face as first element
        self.assertEqual(c_bc_objects[0], floor_above["identifier"])
        # Ceiling references floor_above room as second element
        self.assertEqual(c_bc_objects[1], room_1["identifier"])

        # Floor_above references ceiling face as first element
        self.assertEqual(f_bc_objects[0], ceiling["identifier"])
        # Floor_above references ceiling room as second element
        self.assertEqual(f_bc_objects[1], room_0["identifier"])

    def test_upper_floor_floor_face_not_ground(self):
        """Floor face of floor 1+ must not be Ground."""
        mass = make_mass(num_floors=2)
        model, path = export_temp(mass)
        os.unlink(path)
        room_1 = model["rooms"][1]
        for face in room_1["faces"]:
            if face["face_type"] == "Floor":
                self.assertNotEqual(face["boundary_condition"]["type"], "Ground")


class TestIdentifiers(unittest.TestCase):

    def test_model_identifier_in_output(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass, identifier="MyBuilding")
        os.unlink(path)
        self.assertEqual(model["identifier"], "MyBuilding")

    def test_illegal_chars_in_identifier_are_sanitised(self):
        model, path = export_temp(make_mass(1), identifier="My Building/Test")
        os.unlink(path)
        self.assertNotIn(" ", model["identifier"])
        self.assertNotIn("/", model["identifier"])

    def test_sanitise_id_replaces_spaces(self):
        self.assertEqual(_sanitise_id("hello world"), "hello_world")

    def test_sanitise_id_replaces_slash(self):
        self.assertEqual(_sanitise_id("a/b"), "a_b")

    def test_sanitise_id_truncates_to_100(self):
        long_id = "a" * 200
        self.assertEqual(len(_sanitise_id(long_id)), 100)

    def test_room_identifier_format(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass, identifier="Bldg")
        os.unlink(path)
        self.assertEqual(model["rooms"][0]["identifier"], "Bldg_floor_000")

    def test_face_identifier_format(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass, identifier="Bldg")
        os.unlink(path)
        face_ids = [f["identifier"] for f in model["rooms"][0]["faces"]]
        self.assertTrue(
            all(fid.startswith("Bldg_floor_000_face_") for fid in face_ids),
            msg=f"Unexpected face identifiers: {face_ids}",
        )


class TestRoomMetadata(unittest.TestCase):

    def test_room_story_field_format(self):
        mass = make_mass(num_floors=3)
        model, path = export_temp(mass)
        os.unlink(path)
        for i, room in enumerate(model["rooms"]):
            self.assertEqual(room["story"], f"floor_{i:03d}")

    def test_room_display_name(self):
        mass = make_mass(num_floors=2)
        model, path = export_temp(mass)
        os.unlink(path)
        self.assertEqual(model["rooms"][0]["display_name"], "Floor 0")
        self.assertEqual(model["rooms"][1]["display_name"], "Floor 1")


class TestOutputFile(unittest.TestCase):

    def test_file_is_written(self):
        mass = make_mass(num_floors=1)
        _, path = export_temp(mass)
        try:
            self.assertTrue(os.path.isfile(path))
        finally:
            os.unlink(path)

    def test_file_is_valid_json(self):
        mass = make_mass(num_floors=1)
        _, path = export_temp(mass)
        try:
            with open(path, encoding="utf-8") as f:
                parsed = json.load(f)
            self.assertIsInstance(parsed, dict)
        finally:
            os.unlink(path)

    def test_return_value_equals_file_content(self):
        mass = make_mass(num_floors=2)
        model_dict, path = export_temp(mass)
        try:
            with open(path, encoding="utf-8") as f:
                from_file = json.load(f)
            self.assertEqual(model_dict, from_file)
        finally:
            os.unlink(path)

    def test_display_name_in_output(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass, display_name="My Test Building")
        os.unlink(path)
        self.assertEqual(model["display_name"], "My Test Building")

    def test_display_name_omitted_when_none(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass, display_name=None)
        os.unlink(path)
        self.assertNotIn("display_name", model)


class TestModelStructure(unittest.TestCase):

    def test_type_field_is_model(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass)
        os.unlink(path)
        self.assertEqual(model["type"], "Model")

    def test_properties_has_radiance_stub(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass)
        os.unlink(path)
        self.assertEqual(model["properties"]["type"], "ModelProperties")
        self.assertEqual(
            model["properties"]["radiance"]["type"], "ModelRadianceProperties"
        )

    def test_units_written(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass, units="Meters")
        os.unlink(path)
        self.assertEqual(model["units"], "Meters")

    def test_tolerance_written(self):
        mass = make_mass(num_floors=1)
        model, path = export_temp(mass, tolerance=0.05)
        os.unlink(path)
        self.assertAlmostEqual(model["tolerance"], 0.05)


class TestSubtractedMass(unittest.TestCase):

    def test_subtracted_mass_exports_without_error(self):
        """A subtracted mass should export cleanly; room count == num_floors."""
        from models.subtractor import Subtractor, SubtractorType, SubtractionConfig
        from models.subtraction_engine import apply_subtractions

        mass = make_mass(num_floors=4)
        # Vertical subtractor: a courtyard
        sub = Subtractor(
            x=1.0, y=1.0, width=1.5, depth=2.0,
            z_bottom=0.0, z_top=12.0,
            subtractor_type=SubtractorType.VERTICAL,
        )
        config = SubtractionConfig(
            vertical_subtractors=[sub],
            horizontal_subtractors=[],
            min_plan_size=0.5,
            max_plan_size=3.0,
        )
        subtracted = apply_subtractions(mass, config)
        model, path = export_temp(subtracted)
        os.unlink(path)
        self.assertEqual(len(model["rooms"]), mass.num_floors)


# ---------------------------------------------------------------------------
# Red tests
# ---------------------------------------------------------------------------

class TestRedCases(unittest.TestCase):

    def test_invalid_output_path_raises_oserror(self):
        mass = make_mass(num_floors=1)
        with self.assertRaises(OSError):
            export_to_hbjson(mass, "/nonexistent_directory/out.hbjson")


if __name__ == "__main__":
    unittest.main()
