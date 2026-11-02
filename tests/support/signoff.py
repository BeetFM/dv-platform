"""Small synthetic release documents; these never assert native qualification."""

import base64
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dv_platform.physical_design import file_digest, write_document
from dv_platform.signing import canonical_signed_document
from dv_platform.signoff import LIMIT_FIELDS, PVT_CORNERS, RC_CORNERS, REQUIRED_CHECKS, SKY130_REVISION
from tests.support.entitlements import issue_test_entitlement


def project_v2(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    files = {
        "flow.tcl": "# synthetic test\n",
        "reference.v": "module cpu_top; endmodule\n",
        "functional.sdc": "create_clock -period 100 [get_ports clk]\n",
        "technology/tech.lef": "test\n",
    }
    files.update({f"technology/lib/{pvt}.lib": "test\n" for pvt in PVT_CORNERS})
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text(content)
    technology = {
        "schema_version": 1,
        "pdk": "sky130A",
        "library": "sky130_fd_sc_hd",
        "revision": SKY130_REVISION,
        "files": {name: file_digest(root / name) for name in files if name.startswith("technology/")},
        "tools": {name: {"version": "synthetic", "sha256": "0" * 64} for name in ("openroad", "sta", "yosys")},
    }
    write_document(root / "technology-lock.json", technology)
    project = {
        "schema_version": 2,
        "design": "cpu_top",
        "flow": "flow.tcl",
        "inputs": [*files, "technology-lock.json", "requirements.json"],
        "constraints": ["functional.sdc"],
        "libraries": [f"technology/lib/{pvt}.lib" for pvt in PVT_CORNERS],
        "parasitics": "results/nom.spef",
        "technology_lock": "technology-lock.json",
        "reference_netlist": "reference.v",
        "signoff_policy": "requirements.json",
        "activity": None,
        "deliverables": {
            "gds": "results/design.gds",
            "netlist": "pd-export.v",
            "def": "pd-final.def",
            "odb": "pd-final.odb",
        },
        "scenarios": [
            {
                "name": f"functional_{pvt}_{rc}",
                "mode": "functional",
                "pvt": pvt,
                "rc": rc,
                "libraries": [f"technology/lib/{pvt}.lib"],
                "constraints": ["functional.sdc"],
                "parasitics": f"results/{rc}.spef",
            }
            for pvt in PVT_CORNERS
            for rc in RC_CORNERS
        ],
    }
    current = datetime.now(UTC)
    policy = {
        "schema_version": 1,
        "design": "cpu_top",
        "technology_sha256": file_digest(root / "technology-lock.json"),
        "scenarios": [s["name"] for s in project["scenarios"]],
        "limits": {name: None for name in LIMIT_FIELDS},
        "boundary": {
            "complete": False,
            "constraints_sha256": {"functional.sdc": file_digest(root / "functional.sdc")},
            "assumptions": ["synthetic"],
        },
        "supplies": {},
        "activity_min_coverage_percent": 95,
        "metal_thickness_um": {},
        "required_checks": list(REQUIRED_CHECKS),
        "generated_at": current.isoformat(),
        "expires_at": (current + timedelta(days=1)).isoformat(),
        "signature": None,
    }
    write_document(root / "requirements.json", policy)
    write_document(root / "project.json", project)
    return root / "project.json", project, policy


def authorities(root: Path):
    paths = {}
    roles = {}
    for role in ("engineering", "manufacturing"):
        product = issue_test_entitlement(root / role, ("adapter.enterprise",))
        directory = product.entitlement_path.parent
        cert = directory / "issuer-certificate.pem"
        paths[role] = (directory / "issuer-key.pem", cert)
        roles[role] = {"trust_root": cert.relative_to(root).as_posix(), "certificate_sha256": [file_digest(cert)]}
    path = root / "trust.json"
    write_document(path, {"schema_version": 1, "roles": roles, "revoked_certificate_sha256": []})
    return path, paths


def sign(document: dict, path: Path, key: Path, certificate: Path):
    cert_name = certificate.parent.parent.name + "-" + certificate.name
    shutil.copyfile(certificate, path.parent / cert_name)
    payload, signature = path.parent / "payload.bin", path.parent / "signature.bin"
    payload.write_bytes(canonical_signed_document(document))
    subprocess.run(
        ("openssl", "dgst", "-sha256", "-sign", str(key), "-out", str(signature), str(payload)),
        check=True,
        capture_output=True,
        timeout=30,
    )
    document["signature"] = {
        "certificate_file": cert_name,
        "certificate_sha256": file_digest(certificate),
        "value": base64.b64encode(signature.read_bytes()).decode(),
    }
    write_document(path, document)
    payload.unlink()
    signature.unlink()
    return cert_name


def passing_checks():
    return {
        name: {
            "status": "passed",
            "tool": "synthetic-test-only",
            "reason": "synthetic test evidence",
            "artifacts": [] if name == "requirements" else ["native.log"],
            "metrics": {},
        }
        for name in REQUIRED_CHECKS
    }


def run_fixture(root: Path, project_path: Path, project: dict):
    directory = root / "run"
    case = directory / "baseline"
    case.mkdir(parents=True)
    workflow = directory / "workflow/fixture.py"
    workflow.parent.mkdir()
    workflow.write_text("# synthetic workflow contract fixture\n")
    for name in project["inputs"]:
        target = case / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_path.parent / name, target)
    for name in (*project["deliverables"].values(), "native.log"):
        path = case / name
        path.parent.mkdir(exist_ok=True, parents=True)
        path.write_text("synthetic test artifact\n")
    write_document(case / "analysis.json", {"artifacts": {"native.log": file_digest(case / "native.log")}})
    write_document(
        directory / "run.json",
        {
            "selected": "baseline",
            "status": "timing_closed",
            "project_sha256": file_digest(project_path),
            "source_inputs": {name: file_digest(project_path.parent / name) for name in project["inputs"]},
            "workflow_files": {"fixture.py": file_digest(workflow)},
        },
    )
    return directory / "run.json"
