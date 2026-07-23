from unittest import TestCase

from scripts.check_repository_contracts import (
    check_capability_matrix,
    check_cli_examples,
    check_internal_links,
    check_schema_versions,
)


class RepositoryContractTests(TestCase):
    def test_documentation_and_schema_contracts(self) -> None:
        self.assertEqual(check_internal_links(), [])
        self.assertEqual(check_cli_examples(), [])
        self.assertEqual(check_schema_versions(), [])
        self.assertEqual(check_capability_matrix(), [])
