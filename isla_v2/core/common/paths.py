from pathlib import Path

BASE_DIR = Path("/home/ai/ai-agents")
ISLA_V2_DIR = BASE_DIR / "isla_v2"

DATA_DIR = ISLA_V2_DIR / "data"
EVENTS_DIR = DATA_DIR / "events"
LOGS_DIR = DATA_DIR / "logs"
DOCS_DIR = DATA_DIR / "docs"
PROCEDURES_DIR = DATA_DIR / "procedures"
PROCEDURE_LOCKS_DIR = PROCEDURES_DIR / "locks"
PROCEDURE_RUNS_DIR = EVENTS_DIR / "procedure_runs"
PROCEDURE_HISTORY_FILE = EVENTS_DIR / "procedure_history.jsonl"

FACTS_DB = DATA_DIR / "facts.db"
NOTES_DB = DATA_DIR / "notes.db"


def ensure_dirs() -> None:
    for p in [
        ISLA_V2_DIR,
        DATA_DIR,
        EVENTS_DIR,
        LOGS_DIR,
        DOCS_DIR,
        PROCEDURES_DIR,
        PROCEDURE_LOCKS_DIR,
        PROCEDURE_RUNS_DIR,
    ]:
        p.mkdir(parents=True, exist_ok=True)
