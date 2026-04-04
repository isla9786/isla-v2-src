from isla_v2.core.tools.ops_catalog import (
    canonicalize_ops_text,
    help_lines,
    is_known_ops_command,
    known_ops_names,
)


def test_help_lines_are_unique_and_prefixed():
    lines = help_lines()
    assert len(lines) == len(set(lines))
    assert all(line.startswith("/ops ") for line in lines)


def test_aliases_canonicalize_to_single_command():
    assert canonicalize_ops_text("audit logs") == "audit trail"
    assert canonicalize_ops_text("restart isla v2 bot service") == "restart v2"
    assert canonicalize_ops_text("confirm restart ollama") == "confirm force restart ollama"


def test_known_ops_names_match_catalog_queries():
    names = set(known_ops_names())
    assert "restart gateway" in names
    assert "ollama logs" in names
    assert is_known_ops_command("restart gateway")
    assert is_known_ops_command("crew sidecar logs")
    assert not is_known_ops_command("totally unsupported ops command")
