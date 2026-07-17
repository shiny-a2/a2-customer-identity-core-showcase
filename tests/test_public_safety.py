from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "public_safety",
    ROOT / "scripts/check_public_safety.py",
)

if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load public safety scanner.")

PUBLIC_SAFETY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLIC_SAFETY)


class PublicSafetyTest(unittest.TestCase):
    def test_current_showcase_is_safe(self) -> None:
        self.assertEqual([], PUBLIC_SAFETY.current_failures(ROOT))

    def test_safe_public_copy_is_accepted(self) -> None:
        content = b"A reviewed foundation with no deployment or customer data."
        self.assertEqual([], PUBLIC_SAFETY.content_failures("README.md", content))

    def test_credentials_are_rejected_without_echoing_values(self) -> None:
        label = "api_" + "key"
        private_value = "demo" + "-private-value-1234567890"
        content = f"{label} = {private_value}".encode("utf-8")
        failures = PUBLIC_SAFETY.content_failures("README.md", content)

        self.assertIn("secret-assignment", failures)
        self.assertNotIn(private_value, " ".join(failures))

    def test_private_keys_are_rejected(self) -> None:
        marker = "-----BEGIN " + "PRIVATE KEY-----"
        failures = PUBLIC_SAFETY.content_failures("README.md", marker.encode("utf-8"))
        self.assertIn("private-key", failures)

    def test_certificates_and_embedded_private_source_are_rejected(self) -> None:
        certificate = "-----BEGIN " + "CERTIFICATE-----"
        source = "<" + "?php"
        failures = PUBLIC_SAFETY.content_failures(
            "README.md",
            f"{certificate}\n{source}".encode("utf-8"),
        )

        self.assertIn("certificate", failures)
        self.assertIn("embedded-source", failures)

    def test_customer_and_infrastructure_identifiers_are_rejected_from_docs(self) -> None:
        address = ".".join(("192", "0", "2", "10"))
        email = "person" + "@" + "example.invalid"
        mobile = "+98" + "9123456789"
        content = f"{address} {email} {mobile}".encode("utf-8")
        failures = PUBLIC_SAFETY.content_failures("CHANGELOG.md", content)

        self.assertIn("network-address", failures)
        self.assertIn("email-address", failures)
        self.assertIn("mobile-number", failures)

    def test_unapproved_paths_are_redacted(self) -> None:
        sensitive_path = "customer-" + "name-export.csv"
        label = PUBLIC_SAFETY.safe_path_label(sensitive_path)

        self.assertNotIn(sensitive_path, label)
        self.assertRegex(label, r"\Aunapproved-path-[0-9a-f]{12}\Z")


if __name__ == "__main__":
    unittest.main()
