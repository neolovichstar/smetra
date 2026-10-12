import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


class DataExportArchiveTests(unittest.TestCase):
    def test_browser_zip_is_valid_and_keeps_uploaded_names_inside_archive(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is needed for the browser ZIP fixture")
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "export.zip"
            subprocess.run(
                [node, str(root / "tests" / "data_export_zip.cjs"), str(archive)],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            with zipfile.ZipFile(archive) as result:
                self.assertEqual(result.testzip(), None)
                self.assertEqual(
                    result.namelist(),
                    ["README.txt", "manifest.json", "Данные/clients.json", "Файлы/file-1-.._.._brief.txt"],
                )
                self.assertEqual(json.loads(result.read("Данные/clients.json")), [{"id": "client-1", "name": "Fixture"}])
                self.assertEqual(result.read("Файлы/file-1-.._.._brief.txt"), b"verified export attachment")


if __name__ == "__main__":
    unittest.main()
