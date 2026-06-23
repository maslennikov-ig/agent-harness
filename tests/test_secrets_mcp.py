import json
import tempfile
import unittest
from pathlib import Path

from harness_core.mcp import merge_mcp_config
from harness_core.secrets import SecretVault, SecretVaultError


class SecretsMcpTests(unittest.TestCase):
    def test_secret_vault_roundtrip_hides_plaintext_and_rejects_wrong_passphrase(self):
        vault = SecretVault()
        payload = {"OPENAI_API_KEY": "sk-test-value", "MCP_TOKEN": "token-value"}

        encrypted = vault.encrypt_json(payload, passphrase="correct horse battery staple")

        self.assertNotIn("sk-test-value", encrypted)
        self.assertEqual(vault.decrypt_json(encrypted, passphrase="correct horse battery staple"), payload)
        with self.assertRaises(SecretVaultError):
            vault.decrypt_json(encrypted, passphrase="wrong")

    def test_mcp_merge_adds_templates_without_overwriting_unknown_existing_servers(self):
        existing = {
            "mcpServers": {
                "custom": {"command": "custom-cli", "args": ["serve"], "env": {"KEEP": "1"}},
                "context7": {"command": "old-context7", "args": []},
            },
            "otherSetting": True,
        }
        template = {
            "mcpServers": {
                "context7": {"command": "context7", "args": ["mcp"]},
                "playwright": {"command": "npx", "args": ["@playwright/mcp"]},
            }
        }

        merged = merge_mcp_config(existing, template)

        self.assertEqual(merged["mcpServers"]["custom"], existing["mcpServers"]["custom"])
        self.assertEqual(merged["mcpServers"]["context7"], existing["mcpServers"]["context7"])
        self.assertEqual(merged["mcpServers"]["playwright"], template["mcpServers"]["playwright"])
        self.assertTrue(merged["otherSetting"])

    def test_secret_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "secrets.enc"
            vault = SecretVault()
            vault.write_encrypted(path, {"A": "B"}, passphrase="pw")

            self.assertTrue(path.read_text(encoding="utf-8").startswith("{"))
            self.assertEqual(vault.read_encrypted(path, passphrase="pw"), {"A": "B"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["format"], "harness-v1")


if __name__ == "__main__":
    unittest.main()
