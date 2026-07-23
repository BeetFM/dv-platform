import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.analysis.rtl import write_normalized_rtl_facts
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import RTLModule


class RegisterCliIntegrationTests(unittest.TestCase):
    def test_plan_consumes_explicit_register_map_and_persists_it(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = default_config(root)
            register_path = root / "registers.json"
            register_path.write_text(
                json.dumps(
                    {
                        "module": "top",
                        "registers": [
                            {
                                "name": "CONTROL",
                                "offset": "0x0",
                                "width": 32,
                                "fields": [{"name": "ENABLE", "msb": 0, "lsb": 0, "access": "rw"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            write_config(
                config.__class__(**{**config.__dict__, "register_map_paths": (register_path,)}),
                root / "dv-platform.toml",
            )
            write_normalized_rtl_facts(config, (RTLModule("top"),), "Verilator 5.0")
            self.assertEqual(main(["--repo-root", str(root), "plan"]), 0)
            plans = read_stored_plans(root / ".dv-platform" / "plans" / "plans.sqlite")
            self.assertEqual(plans[0].register_models[0].name, "CONTROL")
            self.assertEqual(plans[0].register_models[0].offset, 0)


if __name__ == "__main__":
    unittest.main()
