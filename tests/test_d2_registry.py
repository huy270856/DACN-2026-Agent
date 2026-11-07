"""Unit and acceptance tests for D2 - Tool Registry."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestrator.registry import (
    ToolRegistry,
    ToolUnknownError,
    ToolDisabledError,
    DuplicateToolError,
    ProviderMismatchError,
    ProviderUnavailableError,
    TargetUnsupportedError,
)
from d0.validate import ContractError


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / 'd0' / 'fixtures' / f'{name}.json').read_text(encoding='utf8'))


class TestD2ToolRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.spec = load_fixture('tool_spec')

    def test_01_register_and_lookup_valid_tool(self):
        registered = self.registry.register_tool(self.spec)
        self.assertEqual(registered['tool_id'], 'static.ember_features')
        self.assertEqual(registered['tool_version'], '0.1.0')

        # Lookup without version gets latest
        fetched = self.registry.get_tool('static.ember_features')
        self.assertEqual(fetched['tool_id'], 'static.ember_features')
        self.assertEqual(fetched['provider']['id'], 'ember_local')

        # Lookup with explicit version
        fetched_v = self.registry.get_tool('static.ember_features', '0.1.0')
        self.assertEqual(fetched_v['tool_version'], '0.1.0')

    def test_02_versioned_tools(self):
        self.registry.register_tool(self.spec)

        v2 = copy.deepcopy(self.spec)
        v2['tool_version'] = '0.2.0'
        v2['description'] = 'Version 2 with updated feature extraction'
        self.registry.register_tool(v2)

        # Lookup without version should return the latest registered (0.2.0)
        latest = self.registry.get_tool('static.ember_features')
        self.assertEqual(latest['tool_version'], '0.2.0')
        self.assertEqual(latest['description'], 'Version 2 with updated feature extraction')

        # Lookup v1 explicitly
        v1 = self.registry.get_tool('static.ember_features', '0.1.0')
        self.assertEqual(v1['tool_version'], '0.1.0')

    def test_03_reject_duplicate_registration(self):
        self.registry.register_tool(self.spec)
        with self.assertRaises(DuplicateToolError):
            self.registry.register_tool(self.spec)

    def test_04_reject_invalid_spec_schema(self):
        bad_spec = copy.deepcopy(self.spec)
        bad_spec['tool_id'] = '123_INVALID_UPPERCASE'  # violates regex ^[a-z][a-z0-9_.-]{1,80}$
        with self.assertRaises(ContractError):
            self.registry.register_tool(bad_spec)

    def test_05_unknown_tool_lookup(self):
        with self.assertRaises(ToolUnknownError):
            self.registry.get_tool('non_existent_tool')

        self.registry.register_tool(self.spec)
        with self.assertRaises(ToolUnknownError):
            self.registry.get_tool('static.ember_features', '9.9.9')

    def test_06_disabled_tool_handling(self):
        self.registry.register_tool(self.spec)
        self.registry.set_enabled('static.ember_features', False)

        # require_enabled=True (default) raises ToolDisabledError
        with self.assertRaises(ToolDisabledError):
            self.registry.get_tool('static.ember_features')

        # require_enabled=False succeeds
        spec = self.registry.get_tool('static.ember_features', require_enabled=False)
        self.assertFalse(spec['enabled'])

        # Re-enable
        self.registry.set_enabled('static.ember_features', True)
        spec_enabled = self.registry.get_tool('static.ember_features')
        self.assertTrue(spec_enabled['enabled'])

    def test_07_provider_binding_no_silent_fallback(self):
        self.registry.register_tool(self.spec)

        # Valid resolution matching pinned provider
        provider = self.registry.resolve_provider('static.ember_features', requested_provider_id='ember_local')
        self.assertEqual(provider['id'], 'ember_local')

        # Mismatched provider request must be rejected (ADR-005)
        with self.assertRaises(ProviderMismatchError):
            self.registry.resolve_provider('static.ember_features', requested_provider_id='rogue_provider')

    def test_08_provider_availability(self):
        self.registry.register_tool(self.spec)
        self.assertTrue(self.registry.is_provider_available('ember_local'))

        # Mark provider unavailable
        self.registry.set_provider_availability('ember_local', False)
        self.assertFalse(self.registry.is_provider_available('ember_local'))

        with self.assertRaises(ProviderUnavailableError):
            self.registry.resolve_provider('static.ember_features')

    def test_09_capability_discovery(self):
        self.registry.register_tool(self.spec)
        capabilities = self.registry.list_capabilities()
        self.assertIn('static.pe_features', capabilities)

        tools = self.registry.find_by_capability('static.pe_features')
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]['tool_id'], 'static.ember_features')

    def test_10_target_support_validation(self):
        self.registry.register_tool(self.spec)
        self.assertTrue(self.registry.validate_target_support('static.ember_features', 'FILE'))

        with self.assertRaises(TargetUnsupportedError):
            self.registry.validate_target_support('static.ember_features', 'PROCESS')


if __name__ == '__main__':
    unittest.main()
