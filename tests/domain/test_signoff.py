from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from dv_platform.physical_design import file_digest, load_physical_project, write_document
from dv_platform.release import approval_identity, build_release, import_approval, verify_release
from dv_platform.signoff import load_requirements, read_document, requirements_gaps, verify_role
from tests.support.signoff import authorities, passing_checks, project_v2, run_fixture, sign


class SignoffContractTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path, self.project, self.policy = project_v2(self.root / "project")
        technology = read_document(self.path.parent / "technology-lock.json")
        pin = patch("dv_platform.signoff._pinned_sky130_files", return_value=technology["files"])
        pin.start()
        self.addCleanup(pin.stop)

    def test_nine_view_project_is_required_and_draft_gaps_remain_explicit(self):
        project = load_physical_project(self.path)
        self.assertEqual(len(project["scenarios"]), 9)
        policy = load_requirements(self.path.parent / "requirements.json", project)
        self.assertIn("area_max_um2", requirements_gaps(policy, project))
        self.assertIn("boundary_constraints", requirements_gaps(policy, project))
        for mutate in (lambda p: p["scenarios"].pop(), lambda p: p["scenarios"].append(deepcopy(p["scenarios"][0]))):
            project = deepcopy(self.project)
            mutate(project)
            write_document(self.path, project)
            with self.assertRaises(ValueError):
                load_physical_project(self.path)

    def test_corrupt_technology_and_unbound_timing_inputs_are_rejected(self):
        (self.path.parent / "technology/tech.lef").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "digest"):
            load_physical_project(self.path)
        (self.path.parent / "technology/tech.lef").write_text("test\n")
        self.project["scenarios"][0]["libraries"] = ["undeclared.lib"]
        write_document(self.path, self.project)
        with self.assertRaisesRegex(ValueError, "undeclared"):
            load_physical_project(self.path)

    def test_json_duplicates_nonfinite_limits_and_constraint_changes_fail(self):
        path = self.root / "bad.json"
        for text in ('{"a":1,"a":2}', '{"a":NaN}', "[]"):
            path.write_text(text)
            with self.assertRaises(ValueError):
                read_document(path)
        self.policy["limits"]["area_max_um2"] = -1
        write_document(self.path.parent / "requirements.json", self.policy)
        with self.assertRaises(ValueError):
            load_requirements(self.path.parent / "requirements.json", self.project)
        self.policy["limits"]["area_max_um2"] = 10**400
        write_document(self.path.parent / "requirements.json", self.policy)
        with self.assertRaisesRegex(ValueError, "finite"):
            load_requirements(self.path.parent / "requirements.json", self.project)
        self.policy["limits"]["area_max_um2"] = 100
        self.policy["boundary"]["constraints_sha256"]["functional.sdc"] = "0" * 64
        write_document(self.path.parent / "requirements.json", self.policy)
        with self.assertRaisesRegex(ValueError, "constraints"):
            load_requirements(self.path.parent / "requirements.json", self.project)

    def test_role_trust_is_independent_revocable_and_time_bounded(self):
        trust, keys = authorities(self.root / "authorities")
        path = self.path.parent / "requirements.json"
        sign(self.policy, path, *keys["engineering"])
        verify_role(self.policy, path, trust, "engineering")
        with self.assertRaisesRegex(ValueError, "not authorized"):
            verify_role(self.policy, path, trust, "manufacturing")
        data = read_document(trust)
        data["revoked_certificate_sha256"] = [self.policy["signature"]["certificate_sha256"]]
        write_document(trust, data)
        with self.assertRaises(ValueError):
            verify_role(self.policy, path, trust, "engineering")
        data["revoked_certificate_sha256"] = []
        write_document(trust, data)
        with self.assertRaisesRegex(ValueError, "expired"):
            verify_role(self.policy, path, trust, "engineering", now=datetime.now(UTC) + timedelta(days=3))

    def ready_release(self):
        trust, keys = authorities(self.root / "authorities")
        self.project["activity"] = {"file": "activity.vcd", "scope": "tb/dut", "workload": "synthetic"}
        self.project["inputs"].append("activity.vcd")
        (self.path.parent / "activity.vcd").write_text("synthetic\n")
        self.project["inputs"].append("sources.loc")
        (self.path.parent / "sources.loc").write_text("synthetic\n")
        self.policy["limits"] = {key: 1 for key in self.policy["limits"]}
        self.policy["boundary"]["complete"] = True
        self.policy["supplies"] = {
            net: {"voltage": voltage, "sources": "sources.loc"} for net, voltage in (("VPWR", 1.8), ("VGND", 0))
        }
        self.policy["metal_thickness_um"] = {"met4": 1}
        cert = sign(self.policy, self.path.parent / "requirements.json", *keys["engineering"])
        self.project["inputs"].append(cert)
        write_document(self.path, self.project)
        run = run_fixture(self.root, self.path, self.project)
        release = build_release(self.path, run, passing_checks(), self.root / "release")
        return release, trust, keys

    def approval(self, release, role, key, cert, *, waivers=None):
        current = datetime.now(UTC)
        document = {
            "schema_version": 1,
            "role": role,
            "release_sha256": file_digest(release),
            "technology_sha256": file_digest(self.path.parent / "technology-lock.json"),
            "policy_sha256": file_digest(self.path.parent / "requirements.json"),
            "reviewer": "fixture reviewer",
            "generated_at": current.isoformat(),
            "expires_at": (current + timedelta(hours=1)).isoformat(),
            "signature": None,
            "waivers": waivers or [],
            "engineering_approval_sha256": (
                approval_identity(read_document(release.parent / "approvals/engineering.json"))
                if role == "manufacturing" and (release.parent / "approvals/engineering.json").exists()
                else "0" * 64
                if role == "manufacturing"
                else None
            ),
        }
        path = self.root / f"{role}.json"
        sign(document, path, key, cert)
        return path

    def test_production_approval_requires_both_authorities_for_exact_release(self):
        release, trust, keys = self.ready_release()
        status = verify_release(release, trust)
        self.assertTrue(status["engineering_ready"], status["requirements_gaps"])
        self.assertFalse(status["signoff_approved"])
        manufacturing = self.approval(release, "manufacturing", *keys["manufacturing"])
        with self.assertRaisesRegex(ValueError, "engineering approval"):
            import_approval(release, manufacturing, trust)
        engineering = self.approval(release, "engineering", *keys["engineering"])
        self.assertFalse(import_approval(release, engineering, trust)["signoff_approved"])
        manufacturing = self.approval(release, "manufacturing", *keys["manufacturing"])
        self.assertTrue(import_approval(release, manufacturing, trust)["signoff_approved"])
        self.assertFalse(verify_release(release, trust, now=datetime.now(UTC) + timedelta(hours=2))["signoff_approved"])
        tampered = read_document(engineering)
        tampered["release_sha256"] = "0" * 64
        write_document(engineering, tampered)
        with self.assertRaises(ValueError):
            import_approval(release, engineering, trust)
        self.assertTrue(verify_release(release, trust)["signoff_approved"])

    def test_artifact_tamper_invalidates_previous_approval(self):
        release, trust, _ = self.ready_release()
        (release.parent / "artifacts/pd-export.v").write_text("changed")
        with self.assertRaisesRegex(ValueError, "digest"):
            verify_release(release, trust)

    def test_missing_deliverables_and_unbound_sources_cannot_be_approved(self):
        release, trust, _ = self.ready_release()
        manifest = read_document(release)
        manifest["artifacts"].pop("artifacts/results/design.gds")
        write_document(release, manifest)
        self.assertIn("missing deliverable: gds", verify_release(release, trust)["requirements_gaps"])
        manifest["artifacts"].pop("project/reference.v")
        write_document(release, manifest)
        with self.assertRaisesRegex(ValueError, "bound source"):
            verify_release(release, trust)

    def test_manufacturing_cannot_reuse_an_engineering_key_with_a_different_certificate(self):
        import subprocess

        release, trust, keys = self.ready_release()
        engineering = self.approval(release, "engineering", *keys["engineering"])
        import_approval(release, engineering, trust)
        alternate = self.root / "authorities/manufacturing/alternate.pem"
        subprocess.run(
            (
                "openssl",
                "req",
                "-new",
                "-x509",
                "-key",
                str(keys["engineering"][0]),
                "-days",
                "1",
                "-subj",
                "/CN=Different certificate same engineering key",
                "-out",
                str(alternate),
            ),
            check=True,
            capture_output=True,
            timeout=30,
        )
        policy = read_document(trust)
        policy["roles"]["manufacturing"] = {
            "trust_root": alternate.relative_to(trust.parent).as_posix(),
            "certificate_sha256": [file_digest(alternate)],
        }
        write_document(trust, policy)
        manufacturing = self.approval(release, "manufacturing", keys["engineering"][0], alternate)
        with self.assertRaisesRegex(ValueError, "distinct signing keys"):
            import_approval(release, manufacturing, trust)

    def test_signed_waivers_bind_counted_findings_and_manufacturing_accepts_that_exact_decision(self):
        release, trust, keys = self.ready_release()
        data = read_document(release)
        artifact = "verification/synthetic/magic.json"
        report = release.parent / "artifacts" / artifact
        report.parent.mkdir(parents=True)
        write_document(report, {"complete": True, "drc_violations": 2, "antenna_violations": 0})
        data["artifacts"]["artifacts/" + artifact] = file_digest(report)
        data["checks"]["drc_magic"].update(
            status="failed", reason="2 findings", artifacts=[artifact], metrics={"drc_violations": 2}
        )
        write_document(release, data)
        self.assertFalse(verify_release(release, trust)["engineering_ready"])
        expiry = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
        waiver = {
            "waiver_id": "accepted-density-edge",
            "check_id": "drc_magic",
            "artifact": artifact,
            "report_sha256": file_digest(report),
            "finding_count": 2,
            "reason": "synthetic fixture tests explicit report-specific acceptance",
            "expires_at": expiry,
        }
        engineering = self.approval(release, "engineering", *keys["engineering"], waivers=[waiver])
        status = import_approval(release, engineering, trust)
        self.assertTrue(status["engineering_ready"])
        self.assertEqual(status["waived_checks"], ["drc_magic"])
        manufacturing = self.approval(release, "manufacturing", *keys["manufacturing"])
        self.assertTrue(import_approval(release, manufacturing, trust)["signoff_approved"])
        self.assertFalse(
            verify_release(release, trust, now=datetime.now(UTC) + timedelta(minutes=40))["signoff_approved"]
        )
        waiver["reason"] = "changed engineering decision"
        engineering = self.approval(release, "engineering", *keys["engineering"], waivers=[waiver])
        status = import_approval(release, engineering, trust)
        self.assertFalse(status["signoff_approved"])
        self.assertIn("manufacturing", status["approval_errors"])

    def test_authorized_waiver_cannot_bypass_incomplete_analysis(self):
        release, trust, keys = self.ready_release()
        waiver = {
            "waiver_id": "invalid",
            "check_id": "equivalence_final",
            "artifact": "native.log",
            "report_sha256": file_digest(release.parent / "artifacts/native.log"),
            "finding_count": 1,
            "reason": "must never waive equivalence",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
        approval = self.approval(release, "engineering", *keys["engineering"], waivers=[waiver])
        with self.assertRaisesRegex(ValueError, "non-waivable"):
            import_approval(release, approval, trust)

    def test_unsigned_or_incomplete_requirements_cannot_be_approved(self):
        run = run_fixture(self.root, self.path, self.project)
        release = build_release(self.path, run, passing_checks(), self.root / "release")
        status = verify_release(release)
        self.assertFalse(status["engineering_ready"])
        self.assertIn("boundary_constraints", status["requirements_gaps"])

    @skipUnless(
        (Path(__file__).resolve().parents[2] / "schemas/signoff").is_dir(), "private sign-off schemas unavailable"
    )
    def test_private_schemas_match_generated_documents_and_reject_unknown_fields(self):
        from jsonschema import Draft202012Validator, FormatChecker, ValidationError

        release, trust, keys = self.ready_release()
        approval = self.approval(release, "engineering", *keys["engineering"])
        rtl = self.root / "rtl-project.json"
        write_document(
            rtl,
            {
                "schema_version": 1,
                "design": "cpu_top",
                "sources": ["rtl/top.sv"],
                "documents": ["docs/design.md"],
                "physical_project": "physical/project.json",
                "netlist": "mapped.v",
                "mapping_library": "technology/lib/tt_025C_1v80.lib",
                "objective": "area_um2",
            },
        )
        documents = {
            "rtl-project-v1": rtl,
            "physical-project-v2": self.path,
            "technology-lock-v1": self.path.parent / "technology-lock.json",
            "requirements-v1": self.path.parent / "requirements.json",
            "release-v1": release,
            "approval-v1": approval,
            "trust-v1": trust,
        }
        root = Path(__file__).resolve().parents[2] / "schemas/signoff"
        self.assertEqual(len(list(root.glob("*.schema.json"))), len(documents))
        for name, path in documents.items():
            schema = read_document(root / (name + ".schema.json"))
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
            document = read_document(path)
            with self.subTest(schema=name):
                validator.validate(document)
                with self.assertRaises(ValidationError):
                    validator.validate({**document, "unexpected": True})
