import argparse
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.cli_handlers.parser import build_parser
from dv_platform.configuration.serialization import write_config
from dv_platform.core.config import default_config, load_config
from dv_platform.domain.models import AdapterPluginConfig
from dv_platform.enterprise.cli import build_parser as build_enterprise_parser
from dv_platform.entitlement_leases import acquire_capability_lease
from dv_platform.infrastructure.plugins import load_adapter_plugins
from dv_platform.product import (
    FREE_CAPABILITIES,
    OPERATION_CAPABILITIES,
    CapabilityDeniedError,
    require_capability,
    resolve_configured_product_plan,
)
from tests.support.entitlements import issue_test_entitlement


class _EntryPoint:
    group = "dv_platform.semantic_importer"
    name = "semantic_manifest"
    distribution_name = "dv-platform"

    def __init__(self) -> None:
        self.loaded = False

    def load(self):
        self.loaded = True
        raise AssertionError("denied plugin must not import")


class ProductEntitlementTests(unittest.TestCase):
    def test_every_cli_command_is_in_closed_operation_registry(self) -> None:
        for prefix, parser in (
            ("cli.public", build_parser()),
            ("cli.enterprise", build_enterprise_parser()),
        ):
            commands = next(
                action.choices for action in parser._actions if isinstance(action, argparse._SubParsersAction)
            )
            self.assertEqual(
                set(commands),
                {
                    operation.removeprefix(prefix + ".")
                    for operation in OPERATION_CAPABILITIES
                    if operation.startswith(prefix + ".") and operation.count(".") == 2
                },
            )

    def test_valid_grant_round_trips_through_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            product = issue_test_entitlement(root, ("cli.enterprise", "evidence.enterprise.import"))
            config = replace(default_config(root), product=product)
            path = root / "dv-platform.toml"
            write_config(config, path)

            loaded = load_config(path)
            plan = resolve_configured_product_plan(loaded, fail_invalid=True)

            self.assertEqual(plan.entitlement_state, "valid")
            self.assertIn("cli.enterprise", plan.capabilities)
            self.assertEqual(loaded.product.organization, "test-organization")

    def test_expired_grant_enters_grace_and_blocks_publication(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            now = datetime.now(UTC).replace(microsecond=0)
            product = issue_test_entitlement(root, ("cli.enterprise", "release.enterprise.publish"), now=now)
            entitlement = json.loads(product.entitlement_path.read_text(encoding="utf-8"))
            entitlement["issued_at"] = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            entitlement["not_before"] = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            entitlement["expires_at"] = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            # Reissue so the changed canonical payload is signed.
            product = issue_test_entitlement(
                root / "grace", tuple(entitlement["capabilities"]), now=now - timedelta(days=1)
            )
            document = json.loads(product.entitlement_path.read_text(encoding="utf-8"))
            plan = resolve_configured_product_plan(
                replace(default_config(root), product=product),
                now=datetime.fromisoformat(document["expires_at"].replace("Z", "+00:00")) + timedelta(hours=1),
                fail_invalid=True,
            )
            self.assertEqual(plan.entitlement_state, "grace")
            with self.assertRaises(CapabilityDeniedError):
                require_capability(plan, "release.enterprise.publish", publication=True)

    def test_invalid_entitlement_preserves_free_and_denies_enterprise(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            product = issue_test_entitlement(root, ("cli.enterprise",))
            document = json.loads(product.entitlement_path.read_text(encoding="utf-8"))
            document["organization"] = "tampered"
            product.entitlement_path.write_text(json.dumps(document), encoding="utf-8")
            plan = resolve_configured_product_plan(
                replace(default_config(root), product=replace(product, require_enterprise=False))
            )
            self.assertEqual(plan.entitlement_state, "invalid")
            self.assertEqual(plan.capabilities, FREE_CAPABILITIES)
            with self.assertRaises(CapabilityDeniedError):
                require_capability(plan, "cli.enterprise")

    def test_plugin_gate_runs_before_entry_point_load(self) -> None:
        entry_point = _EntryPoint()
        plan = resolve_configured_product_plan(default_config(Path.cwd()))
        with self.assertRaises(CapabilityDeniedError):
            load_adapter_plugins(
                (AdapterPluginConfig(kind="semantic_importer", name="semantic_manifest"),),
                entry_points=(entry_point,),
                product_plan=plan,
            )
        self.assertFalse(entry_point.loaded)

    def test_concurrency_bound_is_enforced_and_released(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            plan = resolve_configured_product_plan(
                replace(
                    default_config(root),
                    product=issue_test_entitlement(root, ("cli.enterprise",)),
                ),
                fail_invalid=True,
            )
            plan = replace(plan, concurrency_limit=1)
            lease = acquire_capability_lease(plan, root, "cli.dv-enterprise")
            try:
                with self.assertRaises(CapabilityDeniedError):
                    acquire_capability_lease(plan, root, "cli.dv-enterprise")
            finally:
                lease.release()
            acquire_capability_lease(plan, root, "cli.dv-enterprise").release()


if __name__ == "__main__":
    unittest.main()
