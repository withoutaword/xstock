import json
import sqlite3
from pathlib import Path


def _json_default(value):
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    symbols_total INTEGER DEFAULT 0,
    symbols_succeeded INTEGER DEFAULT 0,
    error_summary TEXT,
    UNIQUE(scan_date, mode)
);
CREATE TABLE IF NOT EXISTS screening_results (
    scan_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    long_score REAL NOT NULL,
    short_score REAL NOT NULL,
    net_score REAL NOT NULL,
    long_count INTEGER NOT NULL,
    short_count INTEGER NOT NULL,
    close REAL NOT NULL,
    entry_low REAL,
    entry_high REAL,
    stop_price REAL,
    target_price REAL,
    risk_reward REAL,
    PRIMARY KEY(scan_date, symbol)
);
CREATE TABLE IF NOT EXISTS edge_results (
    scan_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    edge_code TEXT NOT NULL,
    name TEXT NOT NULL,
    direction TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL,
    strength REAL NOT NULL,
    score REAL NOT NULL,
    explanation TEXT NOT NULL,
    raw_values TEXT NOT NULL,
    markers TEXT NOT NULL,
    PRIMARY KEY(scan_date, symbol, edge_code)
);
"""


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self):
        self.connection.close()

    def start_run(self, scan_date, mode, symbols_total):
        self.connection.execute(
            "INSERT INTO scan_runs(scan_date, mode, status, symbols_total) VALUES(?, ?, 'RUNNING', ?) "
            "ON CONFLICT(scan_date, mode) DO UPDATE SET started_at=CURRENT_TIMESTAMP, finished_at=NULL, "
            "status='RUNNING', symbols_total=excluded.symbols_total, symbols_succeeded=0, error_summary=NULL",
            (scan_date, mode, symbols_total),
        )
        self.connection.commit()

    def finish_run(self, scan_date, mode, succeeded, errors):
        self.connection.execute(
            "UPDATE scan_runs SET finished_at=CURRENT_TIMESTAMP, status=?, symbols_succeeded=?, error_summary=? "
            "WHERE scan_date=? AND mode=?",
            ("SUCCESS" if not errors else "PARTIAL", succeeded, "\n".join(errors), scan_date, mode),
        )
        self.connection.commit()

    def clear_scan_date(self, scan_date):
        """Remove a daily snapshot before a full refresh.

        This prevents removed symbols or failed downloads from silently showing
        stale results left by an earlier run for the same trading date.
        """
        self.connection.execute("DELETE FROM edge_results WHERE scan_date=?", (scan_date,))
        self.connection.execute("DELETE FROM screening_results WHERE scan_date=?", (scan_date,))
        self.connection.commit()

    def save_result(self, result):
        values = (
            result.scan_date, result.symbol, result.status, result.long_score, result.short_score,
            result.net_score, result.long_count, result.short_count, result.close, result.entry_low,
            result.entry_high, result.stop_price, result.target_price, result.risk_reward,
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO screening_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values
        )
        self.connection.execute(
            "DELETE FROM edge_results WHERE scan_date=? AND symbol=?", (result.scan_date, result.symbol)
        )
        for edge in result.edges:
            payload = edge.to_dict()
            self.connection.execute(
                "INSERT INTO edge_results VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    result.scan_date, result.symbol, edge.code, edge.name, edge.direction,
                    edge.category, edge.status, edge.strength, edge.score, edge.explanation,
                    json.dumps(payload["raw_values"], ensure_ascii=False, default=_json_default),
                    json.dumps(payload["markers"], ensure_ascii=False, default=_json_default),
                ),
            )
        self.connection.commit()

    def latest_date(self):
        row = self.connection.execute("SELECT MAX(scan_date) AS value FROM screening_results").fetchone()
        return row["value"] if row else None

    def results(self, scan_date=None):
        scan_date = scan_date or self.latest_date()
        if not scan_date:
            return []
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM screening_results WHERE scan_date=? ORDER BY ABS(net_score) DESC", (scan_date,)
        )]

    def available_dates(self):
        return [row["scan_date"] for row in self.connection.execute(
            "SELECT DISTINCT scan_date FROM screening_results ORDER BY scan_date DESC"
        )]

    def edges(self, symbol, scan_date=None):
        scan_date = scan_date or self.latest_date()
        return [dict(row) for row in self.connection.execute(
            "SELECT * FROM edge_results WHERE scan_date=? AND symbol=? ORDER BY direction, score DESC",
            (scan_date, symbol),
        )]

    def latest_run(self):
        row = self.connection.execute("SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None
