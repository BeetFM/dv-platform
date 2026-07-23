import json
from pathlib import Path
from unittest import TestCase

from dv_platform.enterprise.adapters import ENTERPRISE_RESULT_SCHEMA_VERSION
from dv_platform.enterprise.qualification import QUALIFICATION_SCHEMA_VERSION
from dv_platform.enterprise.requirements import REQUIREMENTS_SCHEMA_VERSION
from dv_platform.enterprise.semantics import (
    SEMANTIC_CATEGORIES,
    SEMANTIC_MANIFEST_SCHEMA_VERSION,
)
from dv_platform.enterprise.signatures import (
    SIGNATURE_MANIFEST_SCHEMA_VERSION,
    SIGNATURE_TRUST_POLICY_SCHEMA_VERSION,
)


class EnterpriseSchemaTests(TestCase):
    def test_checked_in_schemas_match_runtime_contracts(self) -> None:
        root = Path(__file__).resolve().parents[2] / "schemas"
        semantic = json.loads((root / "rtl" / "dvsem-v2.schema.json").read_text(encoding="utf-8"))
        result = json.loads((root / "enterprise" / "enterprise-result-v1.schema.json").read_text(encoding="utf-8"))
        requirements = json.loads((root / "verification" / "requirements-v1.schema.json").read_text(encoding="utf-8"))
        qualification_root = root / "qualification"
        qualification = json.loads((qualification_root / "qualification-v1.schema.json").read_text(encoding="utf-8"))
        signature = json.loads(
            (qualification_root / "qualification-signature-v1.schema.json").read_text(encoding="utf-8")
        )
        trust_policy = json.loads(
            (qualification_root / "qualification-trust-policy-v1.schema.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            semantic["properties"]["schema_version"]["const"],
            SEMANTIC_MANIFEST_SCHEMA_VERSION,
        )
        self.assertEqual(
            set(semantic["$defs"]["completeness"]["required"]),
            set(SEMANTIC_CATEGORIES),
        )
        self.assertEqual(
            result["properties"]["schema_version"]["const"],
            ENTERPRISE_RESULT_SCHEMA_VERSION,
        )
        self.assertEqual(
            requirements["properties"]["schema_version"]["const"],
            REQUIREMENTS_SCHEMA_VERSION,
        )
        self.assertEqual(
            qualification["properties"]["schema_version"]["const"],
            QUALIFICATION_SCHEMA_VERSION,
        )
        self.assertEqual(
            signature["properties"]["schema_version"]["const"],
            SIGNATURE_MANIFEST_SCHEMA_VERSION,
        )
        self.assertEqual(
            trust_policy["properties"]["schema_version"]["const"],
            SIGNATURE_TRUST_POLICY_SCHEMA_VERSION,
        )
