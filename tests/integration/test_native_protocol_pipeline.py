import json
import shutil
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import SimulatorConfig, VerificationTarget
from tests.support.paths import FIXTURES_ROOT

FIXTURES = FIXTURES_ROOT / "mutations" / "protocol"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("vvp"),
    "requires Verilator and Icarus",
)
class NativeProtocolPipelineTests(unittest.TestCase):
    PROFILES = {
        "apb4_qualified_slave": {
            "registers": "apb4_registers.json",
            "mutants": range(1, 10),
        },
        "axi4_lite_qualified_slave": {
            "registers": "axi4_lite_registers.json",
            "mutants": range(1, 11),
        },
    }

    def test_native_protocol_good_duts_close_with_exact_results(self) -> None:
        for module, profile in self.PROFILES.items():
            for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG):
                with self.subTest(module=module, target=target), TemporaryDirectory() as directory:
                    root = Path(directory)
                    config = self._configure(root, module, str(profile["registers"]), target, 0)
                    self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                    self.assertEqual(self._cli(root, "plan", "--target", target.value), 0)
                    plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                    self.assertTrue(plan.scenarios)
                    self.assertTrue(all(scenario.executable for scenario in plan.scenarios))
                    self.assertEqual(self._cli(root, "generate", "--target", target.value), 0)
                    generated = config.output_dir / "simulation" / target.value / "modules" / module
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", target.value), 0)
                    self.assertEqual(self._snapshot(generated), first)
                    run_result = self._cli(root, "run", "--target", target.value, "--module", module)
                    run_dir = config.work_dir / "runs" / "simulation" / target.value / module
                    diagnostics = "\n".join(
                        path.read_text(encoding="utf-8", errors="replace")
                        for path in (run_dir / "stdout.log", run_dir / "stderr.log")
                        if path.is_file()
                    )
                    self.assertEqual(run_result, 0, diagnostics)
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                    summary = json.loads(
                        (config.work_dir / "runs" / "simulation" / target.value / module / "summary.json").read_text(
                            encoding="utf-8"
                        )
                    )
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    self.assertTrue(summary["verification_coverage"]["closure_complete"])

    def test_native_protocol_mutation_matrices_fail_closed(self) -> None:
        for module, profile in self.PROFILES.items():
            for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG):
                for mutant in profile["mutants"]:
                    with self.subTest(module=module, target=target, mutant=mutant), TemporaryDirectory() as directory:
                        root = Path(directory)
                        config = self._configure(root, module, str(profile["registers"]), target, int(mutant))
                        self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                        self.assertEqual(self._cli(root, "plan", "--target", target.value), 0)
                        self.assertEqual(self._cli(root, "generate", "--target", target.value), 0)
                        self.assertNotEqual(
                            self._cli(root, "run", "--target", target.value, "--module", module),
                            0,
                            f"native {target.value} collateral did not kill mutant {mutant}",
                        )
                        summary = json.loads(
                            (
                                config.work_dir / "runs" / "simulation" / target.value / module / "summary.json"
                            ).read_text(encoding="utf-8")
                        )
                        self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _configure(
        root: Path,
        module: str,
        register_file: str,
        target: VerificationTarget,
        mutant: int,
    ):
        rtl = root / "rtl"
        rtl.mkdir()
        source = f"{module}.sv"
        shutil.copy2(FIXTURES / source, rtl / source)
        shutil.copy2(FIXTURES / register_file, root / register_file)
        (rtl / "files.f").write_text(source + "\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=(module,),
            parameter_overrides=(f"MUTANT={mutant}",),
            register_map_paths=(root / register_file,),
            simulators=(SimulatorConfig(target, "icarus", "iverilog"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config

    @staticmethod
    def _cli(root: Path, *arguments: str) -> int:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--repo-root", str(root), *arguments])
        if result != 0 and arguments[0] in {"analyze-rtl", "plan", "generate"}:
            raise AssertionError(output.getvalue())
        return result

    @staticmethod
    def _snapshot(directory: Path) -> dict[str, bytes]:
        return {
            path.relative_to(directory).as_posix(): path.read_bytes()
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
