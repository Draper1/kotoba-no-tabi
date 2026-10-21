"""Persistence.

Reviews are stored as an append-only event log; scheduling state is *derived*
from it and can be rebuilt at any time. That costs almost nothing now and is
what makes cross-machine sync a small job later: merging two devices is a union
of their review logs plus a replay, with no conflict resolution to invent.
Every review carries a UUID and a device id so a union dedupes cleanly.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import asdict, fields
from datetime import date, datetime, timedelta

from .srs import CardState, schedule

SCHEMA_VERSION = 1

DATA_HOME = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
DB_PATH = os.path.join(DATA_HOME, "kotoba", "save.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id       TEXT PRIMARY KEY,
    card_id  TEXT NOT NULL,
    ts       REAL NOT NULL,
    grade    INTEGER NOT NULL,
    ms       INTEGER,
    device   TEXT
);
CREATE INDEX IF NOT EXISTS reviews_card ON reviews(card_id, ts);
CREATE INDEX IF NOT EXISTS reviews_ts   ON reviews(ts);

CREATE TABLE IF NOT EXISTS card_state (
    card_id    TEXT PRIMARY KEY,
    due        REAL, interval REAL, ease REAL,
    reps       INTEGER, lapses INTEGER, step INTEGER,
    introduced REAL, last_seen REAL, peak REAL
);
CREATE INDEX IF NOT EXISTS card_due ON card_state(due);

CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);

CREATE TABLE IF NOT EXISTS days (
    day      TEXT PRIMARY KEY,
    seconds  REAL DEFAULT 0,
    reviews  INTEGER DEFAULT 0,
    learned  INTEGER DEFAULT 0
);
"""

_STATE_FIELDS = [f.name for f in fields(CardState)]


class Store:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()
        if not self.get("device_id"):
            self.set("device_id", f"{os.uname().nodename}-{uuid.uuid4().hex[:6]}")
        if not self.get("schema"):
            self.set("schema", str(SCHEMA_VERSION))
        if not self.get("created"):
            self.set("created", str(time.time()))

    # --- key/value -------------------------------------------------------
    def get(self, k: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return row["v"] if row else default

    def set(self, k: str, v: str) -> None:
        self.db.execute(
            "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (k, str(v)),
        )
        self.db.commit()

    def get_json(self, k: str, default):
        raw = self.get(k)
        return json.loads(raw) if raw else default

    def set_json(self, k: str, value) -> None:
        self.set(k, json.dumps(value, ensure_ascii=False))

    # --- card state ------------------------------------------------------
    def state(self, card_id: str) -> CardState:
        row = self.db.execute(
            "SELECT * FROM card_state WHERE card_id=?", (card_id,)
        ).fetchone()
        if not row:
            return CardState(card_id=card_id)
        return CardState(**{f: row[f] for f in _STATE_FIELDS})

    def all_states(self) -> dict[str, CardState]:
        rows = self.db.execute("SELECT * FROM card_state").fetchall()
        return {
            r["card_id"]: CardState(**{f: r[f] for f in _STATE_FIELDS}) for r in rows
        }

    def _save_state(self, st: CardState) -> None:
        d = asdict(st)
        cols = ",".join(d)
        marks = ",".join("?" for _ in d)
        updates = ",".join(f"{c}=excluded.{c}" for c in d if c != "card_id")
        self.db.execute(
            f"INSERT INTO card_state({cols}) VALUES({marks}) "
            f"ON CONFLICT(card_id) DO UPDATE SET {updates}",
            tuple(d.values()),
        )

    # --- reviews ---------------------------------------------------------
    def record(self, card_id: str, grade: int, ms: int = 0, now: float | None = None) -> CardState:
        """Append a review event and advance the card's derived state."""
        now = now if now is not None else time.time()
        self.db.execute(
            "INSERT INTO reviews(id,card_id,ts,grade,ms,device) VALUES(?,?,?,?,?,?)",
            (uuid.uuid4().hex, card_id, now, grade, int(ms), self.get("device_id")),
        )
        st = schedule(self.state(card_id), grade, now)
        self._save_state(st)
        self._bump_day(reviews=1)
        self.db.commit()
        return st

    def rebuild(self) -> int:
        """Recompute all scheduling state by replaying the review log.

        This is the safety net: card_state is a cache, and the log is truth.
        It is also exactly the operation a future sync runs after a merge.
        """
        rows = self.db.execute(
            "SELECT card_id, ts, grade FROM reviews ORDER BY ts ASC"
        ).fetchall()
        states: dict[str, CardState] = {}
        for r in rows:
            cid = r["card_id"]
            states[cid] = schedule(states.get(cid) or CardState(cid), r["grade"], r["ts"])
        self.db.execute("DELETE FROM card_state")
        for st in states.values():
            self._save_state(st)
        self.db.commit()
        return len(states)

    # --- queues ----------------------------------------------------------
    def due_ids(self, known: list[str], now: float | None = None, limit: int = 0) -> list[str]:
        """Cards that are due, soonest first. Only ids present in `known`."""
        now = now if now is not None else time.time()
        placeholders = ",".join("?" for _ in known)
        if not known:
            return []
        rows = self.db.execute(
            f"SELECT card_id FROM card_state WHERE due<=? AND card_id IN ({placeholders}) "
            f"ORDER BY due ASC" + (f" LIMIT {int(limit)}" if limit else ""),
            (now, *known),
        ).fetchall()
        return [r["card_id"] for r in rows]

    def seen_ids(self) -> set[str]:
        return {
            r["card_id"]
            for r in self.db.execute("SELECT card_id FROM card_state").fetchall()
        }

    # --- daily log / streak ---------------------------------------------
    def _bump_day(self, seconds: float = 0.0, reviews: int = 0, learned: int = 0) -> None:
        today = date.today().isoformat()
        self.db.execute("INSERT OR IGNORE INTO days(day) VALUES(?)", (today,))
        self.db.execute(
            "UPDATE days SET seconds=seconds+?, reviews=reviews+?, learned=learned+? WHERE day=?",
            (seconds, reviews, learned, today),
        )

    def add_time(self, seconds: float, learned: int = 0) -> None:
        self._bump_day(seconds=seconds, learned=learned)
        self.db.commit()

    def day_stats(self, day: str | None = None) -> dict:
        day = day or date.today().isoformat()
        row = self.db.execute("SELECT * FROM days WHERE day=?", (day,)).fetchone()
        return dict(row) if row else {"day": day, "seconds": 0, "reviews": 0, "learned": 0}

    def streak(self) -> int:
        """Consecutive days studied, counting back from today.

        Counts days you showed up, not days you were correct - and today not
        being done yet never breaks it.
        """
        rows = self.db.execute(
            "SELECT day FROM days WHERE reviews>0 ORDER BY day DESC"
        ).fetchall()
        days = {r["day"] for r in rows}
        if not days:
            return 0
        today = date.today()
        start = today if today.isoformat() in days else today - timedelta(days=1)
        n = 0
        cur = start
        while cur.isoformat() in days:
            n += 1
            cur -= timedelta(days=1)
        return n

    def history(self, limit: int = 60) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM days ORDER BY day DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows][::-1]

    def total_reviews(self) -> int:
        return self.db.execute("SELECT COUNT(*) c FROM reviews").fetchone()["c"]

    # --- the sync seam ---------------------------------------------------
    def export(self) -> dict:
        """The complete, portable save. Derived state is intentionally omitted."""
        return {
            "format": "kotoba-save",
            "version": SCHEMA_VERSION,
            "exported": time.time(),
            "device": self.get("device_id"),
            "kv": {
                r["k"]: r["v"]
                for r in self.db.execute("SELECT k,v FROM kv").fetchall()
                if r["k"] != "device_id"
            },
            "reviews": [
                dict(r) for r in self.db.execute("SELECT * FROM reviews").fetchall()
            ],
            "days": [dict(r) for r in self.db.execute("SELECT * FROM days").fetchall()],
        }

    def import_(self, blob: dict) -> dict:
        """Merge another device's save in. Idempotent: re-importing changes nothing.

        Reviews union by UUID; day totals take the max per day (so the same day
        studied on two machines doesn't double-count); kv is filled in only
        where this device has no value.
        """
        if blob.get("format") != "kotoba-save":
            raise ValueError("not a kotoba save file")

        before = self.total_reviews()
        self.db.executemany(
            "INSERT OR IGNORE INTO reviews(id,card_id,ts,grade,ms,device) VALUES(?,?,?,?,?,?)",
            [
                (r["id"], r["card_id"], r["ts"], r["grade"], r.get("ms"), r.get("device"))
                for r in blob.get("reviews", [])
            ],
        )
        for d in blob.get("days", []):
            self.db.execute("INSERT OR IGNORE INTO days(day) VALUES(?)", (d["day"],))
            self.db.execute(
                "UPDATE days SET seconds=MAX(seconds,?), reviews=MAX(reviews,?), "
                "learned=MAX(learned,?) WHERE day=?",
                (d.get("seconds", 0), d.get("reviews", 0), d.get("learned", 0), d["day"]),
            )
        for k, v in blob.get("kv", {}).items():
            self.db.execute("INSERT OR IGNORE INTO kv(k,v) VALUES(?,?)", (k, v))
        self.db.commit()

        added = self.total_reviews() - before
        cards = self.rebuild()
        return {"added": added, "cards": cards}

    def close(self) -> None:
        self.db.close()
