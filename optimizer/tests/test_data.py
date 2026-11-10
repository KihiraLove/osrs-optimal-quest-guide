import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from quest_optimizer.cli import main
from quest_optimizer.data import Contracts, DataError, load_catalog, read_json

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "synthetic"


class DataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = Contracts(ROOT / "schemas")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "catalog"
        shutil.copytree(EXAMPLE, self.directory)
        self.manifest = self.directory / "manifest.json"

    def edit(self, filename, change):
        path = self.directory / filename
        value = read_json(path)
        change(value)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_draft_and_synthetic_catalogs_validate_without_network(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            self.assertEqual(load_catalog(ROOT / "data/manifest.json", self.contracts)["actions"], [])
            self.assertEqual(len(load_catalog(self.manifest, self.contracts)["actions"]), 1)

    def test_examples_conform_to_document_contracts(self):
        for name in ("profile", "solution"):
            self.contracts.validate(name, read_json(EXAMPLE / f"{name}.json"))

    def test_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for content in ('{"id":1,"id":2}', '{"number":NaN}', '{"number":Infinity}', '{"number":1e999}'):
            self.manifest.write_text(content, encoding="utf-8")
            with self.assertRaises(DataError):
                read_json(self.manifest)

    def test_manifest_cannot_escape_its_directory_or_load_urls(self):
        original = read_json(self.manifest)
        for name in ("../outside.json", "https://example.com/data.json", "C:/outside.json", "..\\outside.json"):
            value = json.loads(json.dumps(original))
            value["collections"]["skills"] = [name]
            self.manifest.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(DataError, "Collection path"):
                load_catalog(self.manifest, self.contracts)

    def test_duplicate_entities_are_rejected(self):
        self.edit("actions.json", lambda values: values.append(values[0]))
        with self.assertRaisesRegex(DataError, "Duplicate entity ID"):
            load_catalog(self.manifest, self.contracts)

    def test_unknown_provenance_is_rejected(self):
        self.edit("skills.json", lambda values: values[0]["evidence"].update(source_ids=["source.missing"]))
        with self.assertRaisesRegex(DataError, "unknown provenance"):
            load_catalog(self.manifest, self.contracts)

    def test_release_gate_fails_even_if_review_metadata_is_forged(self):
        with self.assertRaisesRegex(DataError, "Release blocked"):
            load_catalog(self.manifest, self.contracts, release=True)
        self.edit("manifest.json", lambda value: value.update(status="reviewed", coverage_status="complete"))
        with self.assertRaisesRegex(DataError, "semantic validation"):
            load_catalog(self.manifest, self.contracts, release=True)

    def test_training_steps_cannot_prescribe_methods(self):
        value = read_json(EXAMPLE / "solution.json")
        value["steps"][0]["method"] = "choose-this-method"
        with self.assertRaises(DataError):
            self.contracts.validate("solution", value)

    def test_unexpected_fields_and_unsupported_versions_are_rejected(self):
        self.edit("manifest.json", lambda value: value.update(schema_version="99.0.0", remote_url="https://example.com"))
        with self.assertRaises(DataError):
            load_catalog(self.manifest, self.contracts)

    def test_missing_file_produces_nonzero_cli_status(self):
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = main(["--schemas", str(ROOT / "schemas"), "validate-data", str(self.directory / "missing.json")])
        self.assertEqual(result, 2)
        self.assertIn("missing.json", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
