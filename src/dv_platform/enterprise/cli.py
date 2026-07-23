"""Command-line surface for configured enterprise adapters."""

from __future__ import annotations

import argparse
import json
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol, cast

from dv_platform.core.config import DEFAULT_CONFIG_FILENAME, default_config, load_config, normalize_config
from dv_platform.core.models import CLIConfig
from dv_platform.core.plugins import LoadedAdapterPlugin, load_adapter_plugins
from dv_platform.enterprise.adapters import EnterpriseCommandAdapter, EnterpriseInvocation
from dv_platform.enterprise.profiles import ENTERPRISE_TOOL_PROFILES, detect_enterprise_tools
from dv_platform.enterprise.qualification import (
    QUALIFICATION_LEVELS,
    create_vendor_qualification_bundle,
    import_vendor_attestation,
    qualify_contract,
    qualify_surrogate,
    set_qualification_policy,
)
from dv_platform.enterprise.store import (
    enterprise_status,
    persist_requirements_import,
    persist_semantic_import,
)

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class _SemanticImporter(Protocol):
    def import_semantics(self, path: Path, repo_root: Path, *, strict: bool = False): ...


class _RequirementsImporter(Protocol):
    def import_requirements(self, path: Path, *, strict: bool = False): ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dv-enterprise")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="json_output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    semantic = subparsers.add_parser("import-semantics")
    semantic.add_argument("--input", type=Path, required=True)
    semantic.add_argument("--adapter", default="semantic_manifest")
    semantic.add_argument("--strict", action="store_true")

    requirements = subparsers.add_parser("import-requirements")
    requirements.add_argument("--input", type=Path, required=True)
    requirements.add_argument("--adapter", default="requirements_manifest")
    requirements.add_argument("--strict", action="store_true")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--adapter", required=True)
    run_parser.add_argument("--family", choices=("simulator", "formal", "analyzer"), required=True)
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    run_parser.add_argument("--strict", action="store_true")
    run_parser.add_argument("tool_command", nargs=argparse.REMAINDER)

    status = subparsers.add_parser("status")
    status.add_argument("--policy", choices=("report", "ci"), default="report")
    qualify = subparsers.add_parser("qualify")
    qualify.add_argument("--profile", required=True)
    qualify.add_argument("--mode", choices=("fixture", "surrogate", "vendor"), required=True)
    qualify.add_argument("--probe", action="append", default=[])
    qualify.add_argument("--timeout-seconds", type=float, default=120.0)
    qualify.add_argument("--attestation", type=Path)
    qualify.add_argument("--signature-manifest", type=Path)
    qualify.add_argument("--trust-policy", type=Path)
    bundle = subparsers.add_parser("qualification-bundle")
    bundle.add_argument("--profile", required=True)
    bundle.add_argument("--output", type=Path, required=True)
    bundle.add_argument(
        "--generated-uvm",
        action="store_true",
        help="include deterministic Veriforge-generated UVM collateral and require its licensed execution",
    )
    policy = subparsers.add_parser("qualification-policy")
    policy.add_argument("--minimum-level", choices=QUALIFICATION_LEVELS, required=True)
    policy.add_argument("--profile")
    policy.add_argument("--max-age-days", type=int)
    subparsers.add_parser("profiles")
    benchmark = subparsers.add_parser("benchmark")
    benchmark.add_argument("--rtl", type=Path, required=True)
    benchmark.add_argument("--xml", type=Path, required=True)
    benchmark.add_argument("--pdf", type=Path, required=True)
    benchmark.add_argument("--output", type=Path, required=True)
    benchmark.add_argument("--profile", default="broad-ga-v2")
    benchmark.add_argument("--wheel", type=Path)
    external = subparsers.add_parser("qualify-external-design")
    external.add_argument("--design-id", required=True)
    external.add_argument("--repository", type=Path, required=True)
    external.add_argument("--source", type=Path, action="append", required=True)
    external.add_argument("--top", required=True)
    external.add_argument("--output", type=Path, required=True)
    external.add_argument("--verilator", default="verilator")
    external.add_argument("--slang", default="slang")
    external.add_argument("--surelog", default="surelog")
    verify = subparsers.add_parser("verify-evidence")
    verify.add_argument("--input", type=Path, required=True)
    verify_signature = subparsers.add_parser("verify-qualification-signature")
    verify_signature.add_argument("--attestation", type=Path, required=True)
    verify_signature.add_argument("--signature-manifest", type=Path, required=True)
    verify_signature.add_argument("--trust-policy", type=Path, required=True)
    signing_payload = subparsers.add_parser("qualification-signing-payload")
    signing_payload.add_argument("--attestation", type=Path, required=True)
    signing_payload.add_argument("--signed-at", required=True)
    signing_payload.add_argument("--output", type=Path, required=True)
    trace = subparsers.add_parser("verify-protocol-trace")
    trace.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _config(args.repo_root.resolve(), args.config)
    try:
        loaded = load_adapter_plugins(
            config.adapter_plugins,
            approved_publishers=config.approved_plugin_publishers,
        )
        if args.command == "import-semantics":
            semantic_adapter = cast(
                _SemanticImporter,
                _adapter(loaded, "semantic_importer", args.adapter),
            )
            result = semantic_adapter.import_semantics(args.input, config.repo_root, strict=args.strict)
            modules, summary, state = persist_semantic_import(config, result, args.input)
            return _emit(
                args,
                True,
                {
                    "modules": str(modules),
                    "summary": str(summary),
                    "state": str(state),
                    "module_count": len(result.modules),
                    "complete": result.complete,
                },
            )
        if args.command == "import-requirements":
            requirements_adapter = cast(
                _RequirementsImporter,
                _adapter(loaded, "requirements_importer", args.adapter),
            )
            result = requirements_adapter.import_requirements(args.input, strict=args.strict)
            path = persist_requirements_import(config, result, args.input)
            return _emit(
                args,
                True,
                {
                    "baseline": str(path),
                    "baseline_id": result.baseline_id,
                    "requirement_count": len(result.requirements),
                },
            )
        if args.command == "run":
            return _run(args, config, loaded)
        if args.command == "qualify":
            if args.mode == "fixture":
                data = qualify_contract(config, args.profile)
            elif args.mode == "surrogate":
                data = qualify_surrogate(
                    config,
                    args.profile,
                    probe_names=tuple(args.probe),
                    timeout_seconds=args.timeout_seconds,
                )
            else:
                if args.attestation is None:
                    raise ValueError("vendor qualification requires --attestation")
                data = import_vendor_attestation(
                    config,
                    args.profile,
                    args.attestation,
                    signature_manifest=args.signature_manifest,
                    trust_policy=args.trust_policy,
                )
            return _emit(args, True, data)
        if args.command == "qualification-bundle":
            return _emit(
                args,
                True,
                create_vendor_qualification_bundle(
                    args.profile,
                    args.output,
                    include_generated_uvm=args.generated_uvm,
                ),
            )
        if args.command == "qualification-policy":
            path, policy = set_qualification_policy(
                config,
                args.minimum_level,
                profile=args.profile,
                max_age_days=args.max_age_days,
            )
            return _emit(args, True, {"path": str(path), "policy": policy})
        if args.command == "status":
            data = enterprise_status(config)
            passed = bool(data["passed"]) or args.policy == "report"
            return _emit(args, passed, data)
        if args.command == "benchmark":
            from dv_platform.enterprise.benchmark import run_benchmark

            data = run_benchmark(
                repo_root=config.repo_root,
                rtl=args.rtl,
                xml=args.xml,
                pdf=args.pdf,
                output=args.output,
                profile=args.profile,
                wheel=args.wheel,
            )
            return _emit(args, True, {"output": str(args.output), "result": data})
        if args.command == "qualify-external-design":
            from dv_platform.enterprise.external_design import qualify_external_design

            data = qualify_external_design(
                design_id=args.design_id,
                repository=args.repository,
                sources=tuple(args.source),
                top=args.top,
                output=args.output,
                verilator=args.verilator,
                slang=args.slang,
                surelog=args.surelog,
            )
            return _emit(args, data.get("status") == "passed", data)
        if args.command == "verify-evidence":
            document = json.loads(args.input.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise ValueError("evidence document must be an object")
            if "design_id" in document:
                from dv_platform.enterprise.external_design import verify_external_design_evidence

                data = verify_external_design_evidence(args.input)
            elif "pilot_id" in document:
                from dv_platform.enterprise.evidence import verify_pilot_evidence

                data = verify_pilot_evidence(args.input)
            else:
                raise ValueError("unsupported evidence document type")
            return _emit(args, True, data)
        if args.command == "verify-qualification-signature":
            from dv_platform.enterprise.signatures import verify_qualification_signature

            data = verify_qualification_signature(
                args.attestation,
                args.signature_manifest,
                args.trust_policy,
            ).as_payload()
            return _emit(args, True, data)
        if args.command == "qualification-signing-payload":
            from dv_platform.enterprise.signatures import qualification_signing_payload

            payload = qualification_signing_payload(args.attestation, args.signed_at)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(payload)
            return _emit(
                args,
                True,
                {
                    "output": str(args.output),
                    "payload_sha256": sha256(payload).hexdigest(),
                },
            )
        if args.command == "verify-protocol-trace":
            from dv_platform.agent.transactions import validate_protocol_trace_file

            return _emit(args, True, validate_protocol_trace_file(args.input).as_dict())
        availability = {item.profile.name: item for item in detect_enterprise_tools()}
        profiles = [
            {
                "name": profile.name,
                "display_name": profile.display_name,
                "families": profile.families,
                "languages": profile.languages,
                "capabilities": profile.capabilities,
                "interchange_formats": profile.interchange_formats,
                "executable": availability[profile.name].executable,
                "license_environment_present": availability[profile.name].license_environment_present,
                "available": availability[profile.name].available,
            }
            for profile in ENTERPRISE_TOOL_PROFILES
        ]
        return _emit(args, True, {"profiles": profiles})
    except (LookupError, OSError, TypeError, ValueError) as exc:
        return _emit(args, False, {}, str(exc))


def _run(
    args: argparse.Namespace,
    config: CLIConfig,
    loaded: tuple[LoadedAdapterPlugin, ...],
) -> int:
    if not _RUN_ID.fullmatch(args.run_id):
        raise ValueError("run-id must be 1..128 safe filename characters")
    command = tuple(args.tool_command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ValueError("enterprise run requires a command after --")
    kind = f"{args.family}_runner"
    adapter = cast(EnterpriseCommandAdapter, _adapter(loaded, kind, args.adapter))
    root = config.work_dir / "enterprise-runs" / args.run_id
    result_path = root / "result.json"
    invocation = EnterpriseInvocation(
        adapter=args.adapter,
        family=args.family,
        command=command,
        cwd=root,
        result_path=result_path,
        summary_path=root / "summary.json",
        stdout_path=root / "stdout.log",
        stderr_path=root / "stderr.log",
        timeout_seconds=args.timeout_seconds,
        environment_names=("DV_PLATFORM_RESULT_PATH",),
        environment=(("DV_PLATFORM_RESULT_PATH", str(result_path)),),
        redact_patterns=config.redact_patterns,
    )
    result = adapter.execute(invocation, strict=args.strict)
    return _emit(
        args,
        result.passed,
        {
            "status": result.status,
            "summary": str(result.summary_path),
            "return_code": result.return_code,
            "traceability_complete": result.traceability_complete,
            "checks": len(result.checks),
        },
    )


def _config(repo_root: Path, config_path: Path | None) -> CLIConfig:
    path = config_path or repo_root / DEFAULT_CONFIG_FILENAME
    if path.is_file():
        return normalize_config(load_config(path), repo_root)
    return normalize_config(default_config(repo_root), repo_root)


def _adapter(loaded: tuple[LoadedAdapterPlugin, ...], kind: str, name: str) -> object:
    matches = [item.adapter for item in loaded if item.kind == kind and item.name == name]
    if len(matches) != 1:
        raise LookupError(f"configured adapter not found or ambiguous: {kind}/{name}")
    return matches[0]


def _emit(
    args: argparse.Namespace,
    ok: bool,
    data: dict[str, Any],
    error: str | None = None,
) -> int:
    payload = {"command": args.command, "ok": ok, "data": data}
    if error:
        payload["error"] = {"code": "enterprise_command_failed", "message": error}
    if args.json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif ok:
        for key, value in data.items():
            print(f"{key}={value}")
    else:
        print(f"error={error or 'enterprise policy failed'}", file=sys.stderr)
    return 0 if ok else 1
