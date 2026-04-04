import re
from pathlib import Path


BUNDLE_SCRIPT = Path("/home/ai/bin/isla-v2-bundle")
RESTORE_SCRIPT = Path("/home/ai/bin/isla-v2-restore")

INTENTIONALLY_EXCLUDED_FROM_AUTOMATIC_RESTORE = {"isla-v2-restore"}
OPTIONAL_PRIVILEGED_FILES = {"isla-rootctl", "isla-rootctl.sudoers"}


def bundle_runtime_names() -> set[str]:
    text = BUNDLE_SCRIPT.read_text(encoding="utf-8")
    names = set(re.findall(r'copy_if_exists "\$[^"]+" "\$out/([^"]+)"', text))
    names |= set(re.findall(r'copy_with_optional_sudo [^\n]* "\$out/([^"]+)"', text))
    return names


def restore_runtime_names() -> set[str]:
    text = RESTORE_SCRIPT.read_text(encoding="utf-8")
    return set(re.findall(r'\$backup_dir/([^"]+)', text))


def test_bundle_runtime_files_are_restored_or_explicitly_excluded():
    bundle_names = bundle_runtime_names()
    restore_names = restore_runtime_names()

    missing = sorted((bundle_names - INTENTIONALLY_EXCLUDED_FROM_AUTOMATIC_RESTORE) - restore_names)
    assert not missing, (
        "bundle/restore parity mismatch for runtime-relevant files\n"
        f"missing_from_restore={missing}"
    )


def test_only_expected_runtime_file_is_excluded_from_automatic_restore():
    bundle_names = bundle_runtime_names()
    restore_names = restore_runtime_names()

    excluded = sorted(bundle_names - restore_names)
    assert excluded == sorted(INTENTIONALLY_EXCLUDED_FROM_AUTOMATIC_RESTORE), (
        "unexpected bundle files are not covered by automatic restore\n"
        f"excluded={excluded}"
    )


def test_optional_privileged_files_are_handled_explicitly():
    bundle_names = bundle_runtime_names()
    restore_names = restore_runtime_names()

    for name in OPTIONAL_PRIVILEGED_FILES:
        assert name in bundle_names, f"optional privileged file missing from bundle coverage: {name}"
        assert name in restore_names, f"optional privileged file missing from restore handling: {name}"
