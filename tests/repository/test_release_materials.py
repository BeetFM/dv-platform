import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.release.checksums import generate_checksums
from scripts.release.verify_materials import ReleaseVerificationError, verify_release_materials


class ReleaseMaterialTests(TestCase):
    def test_complete_release_materials_verify_and_tampering_fails(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dv_platform-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
            (root / "dv_platform-0.1.0.tar.gz").write_bytes(b"sdist")
            (root / "sbom.spdx.json").write_text(
                json.dumps(
                    {
                        "spdxVersion": "SPDX-2.3",
                        "SPDXID": "SPDXRef-DOCUMENT",
                        "packages": [
                            {
                                "SPDXID": "SPDXRef-Package-dv-platform",
                                "name": "dv-platform",
                                "licenseDeclared": "Apache-2.0",
                                "licenseConcluded": "Apache-2.0",
                                "comment": "dependency-scopes=root",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            checksum_subjects = tuple(sorted(path for path in root.iterdir() if path.is_file()))
            (root / "SHA256SUMS").write_text(
                "".join(f"{self._digest(path)}  {path.name}\n" for path in checksum_subjects), encoding="utf-8"
            )
            provenance_subjects = tuple(sorted(path for path in root.iterdir() if path.is_file()))
            (root / "provenance.intoto.json").write_text(
                json.dumps(
                    {
                        "_type": "https://in-toto.io/Statement/v1",
                        "predicateType": "https://slsa.dev/provenance/v1",
                        "predicate": {
                            "buildDefinition": {
                                "buildType": "https://veriforge.dev/build-types/python-wheel/v1",
                                "internalParameters": {"lockfileSha256": "a" * 64},
                                "resolvedDependencies": [
                                    {"uri": "git+https://example.invalid/repo", "digest": {"gitCommit": "b" * 40}}
                                ],
                            }
                        },
                        "subject": [
                            {"name": path.name, "digest": {"sha256": self._digest(path)}}
                            for path in provenance_subjects
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                verify_release_materials(root),
                tuple(sorted(path.name for path in provenance_subjects)),
            )
            (root / "dv_platform-0.1.0-py3-none-any.whl").write_bytes(b"tampered")
            with self.assertRaisesRegex(ReleaseVerificationError, "checksum mismatch"):
                verify_release_materials(root)

    def test_rejects_checksum_path_traversal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sbom.spdx.json").write_text("{}", encoding="utf-8")
            (root / "provenance.intoto.json").write_text("{}", encoding="utf-8")
            (root / "SHA256SUMS").write_text(f"{'0' * 64}  ../outside\n", encoding="utf-8")
            with self.assertRaisesRegex(ReleaseVerificationError, "unsafe or duplicate"):
                verify_release_materials(root)

    def test_checksum_generator_uses_sorted_basenames_and_excludes_provenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.whl").write_bytes(b"b")
            (root / "a.tar.gz").write_bytes(b"a")
            (root / ".gitignore").write_text("*", encoding="utf-8")
            (root / "provenance.intoto.json").write_text("{}", encoding="utf-8")
            output = root / "SHA256SUMS"
            self.assertEqual(generate_checksums(root, output), ("a.tar.gz", "b.whl"))
            names = [line.split()[1] for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(names, ["a.tar.gz", "b.whl"])

    @staticmethod
    def _digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
