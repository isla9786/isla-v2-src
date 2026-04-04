from pathlib import Path

from isla_v2.core.memory import fact_store, note_store


def configure_memory_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(fact_store, "FACTS_DB", tmp_path / "facts.db")
    monkeypatch.setattr(note_store, "NOTES_DB", tmp_path / "notes.db")
    monkeypatch.setattr(fact_store, "ensure_dirs", lambda: None)
    monkeypatch.setattr(note_store, "ensure_dirs", lambda: None)


def test_fact_store_search_history_and_expiry(monkeypatch, tmp_path: Path):
    configure_memory_paths(monkeypatch, tmp_path)

    fact_store.set_fact("system", "bridge_canary", "green", source="test")
    fact_store.set_fact("system", "temporary_flag", "stale", source="test", ttl_seconds=-1)

    assert fact_store.get_fact("system", "bridge_canary") == "green"

    active_rows = fact_store.search_facts("bridge")
    assert active_rows and active_rows[0]["state"] == "active"

    expired_row = fact_store.get_fact_record("system", "temporary_flag")
    assert expired_row is not None
    assert expired_row["state"] == "expired"

    history = fact_store.get_fact_history("system", "bridge_canary")
    assert history and history[0]["operation"] == "set"


def test_fact_delete_and_note_store_are_separate(monkeypatch, tmp_path: Path):
    configure_memory_paths(monkeypatch, tmp_path)

    fact_store.set_fact("system", "bridge_canary", "green", source="test")
    assert fact_store.delete_fact("system", "bridge_canary") is True

    history = fact_store.get_fact_history("system", "bridge_canary")
    assert history[0]["operation"] == "delete"
    assert history[1]["operation"] == "set"

    note_id = note_store.add_note("project", "gateway timeout observed", source="test", kind="note")
    assert note_id >= 1

    recent = note_store.recent_notes("project")
    assert recent and recent[0]["body"] == "gateway timeout observed"

    matches = note_store.search_notes("timeout")
    assert matches and matches[0]["namespace"] == "project"
