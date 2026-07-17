#!/usr/bin/env python3
"""Fail closed if the docs-only showcase contains private material."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple


APPROVED_PATHS = frozenset(
    {
        ".github/workflows/public-safety.yml",
        ".gitignore",
        "CHANGELOG.md",
        "README.md",
        "VERSION",
        "scripts/check_public_safety.py",
        "tests/test_public_safety.py",
    }
)
PUBLIC_DOCUMENTS = frozenset({"CHANGELOG.md", "README.md", "VERSION"})
MAX_FILE_BYTES = 256 * 1024
EXPECTED_VERSION = "0.2.0"
EXPECTED_CHECKOUT = "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"

SECRET_PATTERNS: Tuple[Tuple[str, re.Pattern[bytes]], ...] = (
    ("private-key", re.compile(br"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")),
    ("certificate", re.compile(br"-----BEGIN " br"CERTIFICATE-----")),
    ("pgp-private-key", re.compile(br"-----BEGIN PGP " br"PRIVATE KEY BLOCK-----")),
    ("aws-access-key", re.compile(br"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(br"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("generic-secret", re.compile(br"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("bearer-token", re.compile(br"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._~-]{20,}")),
    (
        "secret-assignment",
        re.compile(
            br"(?i)\b(?:password|passwd|client_secret|api[_-]?key|access[_-]?token)"
            br"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{12,}"
        ),
    ),
)

IPV4_PATTERN = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
MOBILE_PATTERN = re.compile(r"(?<![0-9])(?:\+98|0098|0)?9[0-9]{9}(?![0-9])")
DOCUMENT_SOURCE_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("embedded-source", re.compile(r"<\?php|\bwp_ajax_", re.IGNORECASE)),
    ("database-dump", re.compile(r"\b(?:INSERT\s+INTO|CREATE\s+TABLE|COPY\s+.+\s+FROM\s+stdin)\b", re.IGNORECASE)),
)


def content_failures(relative_path: str, data: bytes) -> List[str]:
    """Return stable failure categories without returning sensitive content."""
    failures: List[str] = []

    if len(data) > MAX_FILE_BYTES:
        failures.append("file-too-large")
        return failures

    if b"\x00" in data:
        failures.append("binary-content")
        return failures

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        failures.append("invalid-utf8")
        return failures

    for rule_name, pattern in SECRET_PATTERNS:
        if pattern.search(data) is not None:
            failures.append(rule_name)

    if relative_path in PUBLIC_DOCUMENTS:
        for candidate in IPV4_PATTERN.findall(text):
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                continue
            failures.append("network-address")
            break

        if EMAIL_PATTERN.search(text) is not None:
            failures.append("email-address")

        if MOBILE_PATTERN.search(text) is not None:
            failures.append("mobile-number")

        for rule_name, pattern in DOCUMENT_SOURCE_PATTERNS:
            if pattern.search(text) is not None:
                failures.append(rule_name)

    return failures


def repository_files(root: Path) -> Set[str]:
    files: Set[str] = set()

    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts

        if ".git" in relative_parts or "__pycache__" in relative_parts:
            continue

        if path.is_symlink():
            files.add(path.relative_to(root).as_posix())
            continue

        if path.is_file() and path.suffix not in {".pyc", ".pyo"}:
            files.add(path.relative_to(root).as_posix())

    return files


def safe_path_label(relative_path: str) -> str:
    if relative_path in APPROVED_PATHS:
        return relative_path

    fingerprint = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:12]
    return f"unapproved-path-{fingerprint}"


def current_failures(root: Path) -> List[str]:
    failures: List[str] = []
    found = repository_files(root)

    for relative_path in sorted(found - APPROVED_PATHS):
        failures.append(f"{safe_path_label(relative_path)}:unapproved-file")

    for relative_path in sorted(APPROVED_PATHS - found):
        failures.append(f"{relative_path}:missing-file")

    for relative_path in sorted(found & APPROVED_PATHS):
        path = root / relative_path

        if path.is_symlink():
            failures.append(f"{relative_path}:symlink")
            continue

        for category in content_failures(relative_path, path.read_bytes()):
            failures.append(f"{relative_path}:{category}")

    if APPROVED_PATHS.issubset(found):
        failures.extend(metadata_failures(root))

    return failures


def metadata_failures(root: Path) -> List[str]:
    failures: List[str] = []
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    readme = (root / "README.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/public-safety.yml").read_text(encoding="utf-8")

    if version != EXPECTED_VERSION:
        failures.append("VERSION:release-version-mismatch")

    if EXPECTED_VERSION not in readme or f"[{EXPECTED_VERSION}]" not in changelog:
        failures.append("release-metadata:incomplete")

    action_references = re.findall(r"^\s*uses:\s*([^\s#]+)", workflow, re.MULTILINE)

    if action_references != [EXPECTED_CHECKOUT]:
        failures.append("workflow:unapproved-action")

    required_fragments = ("permissions:\n  contents: read", "persist-credentials: false", "fetch-depth: 0")

    if any(fragment not in workflow for fragment in required_fragments):
        failures.append("workflow:read-only-contract")

    forbidden_fragments = ("pull_request_target", "${{ secrets.", "curl ", "wget ")

    if any(fragment in workflow for fragment in forbidden_fragments):
        failures.append("workflow:unsafe-trigger-or-command")

    return failures


def git_output(root: Path, arguments: Sequence[str]) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(root),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise RuntimeError("Git history inspection failed safely.")

    return result.stdout


def historical_blobs(root: Path) -> Iterable[Tuple[str, str, str]]:
    commits = git_output(root, ["rev-list", "--all"]).decode("ascii").splitlines()
    seen: Set[Tuple[str, str, str]] = set()

    for commit in commits:
        entries = git_output(root, ["ls-tree", "-r", "-z", commit]).split(b"\x00")

        for entry in entries:
            if not entry:
                continue

            metadata, raw_path = entry.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ")
            relative_path = raw_path.decode("utf-8")

            if object_type != "blob":
                continue

            entry_key = (object_id, relative_path, mode)

            if entry_key not in seen:
                seen.add(entry_key)
                yield entry_key


def history_failures(root: Path) -> List[str]:
    failures: List[str] = []

    for object_id, relative_path, mode in historical_blobs(root):
        if relative_path not in APPROVED_PATHS:
            failures.append(f"{safe_path_label(relative_path)}:historical-unapproved-file")
            continue

        if mode == "120000":
            failures.append(f"{relative_path}:historical-symlink")
            continue

        data = git_output(root, ["cat-file", "blob", object_id])

        for category in content_failures(relative_path, data):
            failures.append(f"{relative_path}:historical-{category}")

    return failures


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--history", action="store_true")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    root = arguments.root.resolve()
    failures = current_failures(root)

    if arguments.history:
        failures.extend(history_failures(root))

    if failures:
        for failure in sorted(set(failures)):
            print(failure, file=sys.stderr)
        return 1

    print("public showcase safety scan: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
