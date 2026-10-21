"""The journey.

A thin narrative wrapper over the review engine. The story is there to give the
session a shape and a reason to come back; it deliberately never blocks study,
and the drilling underneath is the same engine `review` uses.
"""

from __future__ import annotations

import json
import os

from . import ui
from .content import CONTENT_DIR, Course
from .session import Session
from .store import Store

# A unit is "held" once most of its cards have been met and are holding.
INTRODUCED_TARGET = 0.85
STRENGTH_TARGET = 0.35
HELD_FRACTION = 0.60


def load_story() -> dict:
    with open(os.path.join(CONTENT_DIR, "story.json"), encoding="utf-8") as f:
        return json.load(f)


class Adventure:
    def __init__(self, course: Course, store: Store):
        self.course = course
        self.store = store
        self.story = load_story()

    # --- progress ---------------------------------------------------------
    def current_unit(self) -> int:
        return int(self.store.get("unit", "1"))

    def unit_progress(self, unit: int) -> tuple[float, float]:
        """(fraction introduced, fraction holding) for a unit's cards."""
        cards = self.course.by_unit(unit)
        if not cards:
            return 0.0, 0.0
        states = self.store.all_states()
        introduced = [c for c in cards if c.id in states]
        holding = [c for c in introduced if states[c.id].strength >= STRENGTH_TARGET]
        return len(introduced) / len(cards), len(holding) / len(cards)

    def unit_complete(self, unit: int) -> bool:
        intro, held = self.unit_progress(unit)
        return intro >= INTRODUCED_TARGET and held >= HELD_FRACTION

    def advance_if_ready(self) -> int | None:
        unit = self.current_unit()
        if unit < 8 and self.unit_complete(unit):
            self.store.set("unit", str(unit + 1))
            return unit + 1
        return None

    # --- play -------------------------------------------------------------
    def play(self, minutes: float = 20.0, new_limit: int = 12) -> None:
        unit = self.current_unit()
        meta = self.course.units[unit]
        scene = self.story["scenes"][str(unit)]

        ui.clear()
        ui.banner(self.store.streak(),
                  len(self.store.due_ids(self.course.ids())),
                  self.store.day_stats()["seconds"] / 60,
                  int(self.store.get("goal_minutes", "85")))
        ui.scene(meta["title"], meta["jp"], scene["arrive"])
        ui.note(f"Chapter {unit} of 8 — {meta['blurb']}")
        ui.note("Press Enter on a card you don't know and it'll simply show you. "
                "Type :q to stop.")
        ui.console.print()

        voices = list(scene["voices"])
        spoken: list[int] = []

        def interlude(done: int) -> None:
            # Drop a line of dialogue every few cards, while any remain.
            if voices and done % 6 == 0:
                v = voices.pop(0)
                ui.speech(v["who"], v["jp"], v["en"])
                ui.console.print()
                spoken.append(done)

        session = Session(self.course, self.store, minutes=minutes,
                          new_limit=new_limit, units=(unit,), interlude=interlude)
        tally = session.run()

        if tally.reviews:
            ui.console.print()
            ui.scene(meta["title"], meta["jp"], scene["leave"])
        report(self.store, self.course, tally)

        nxt = self.advance_if_ready()
        if nxt:
            nxt_meta = self.course.units[nxt]
            ui.milestone(f"Chapter {unit} held. {nxt_meta['jp']} {nxt_meta['title']} "
                         f"is open to you.")
        elif tally.reviews:
            intro, held = self.unit_progress(unit)
            ui.note(f"Chapter {unit}: {intro:.0%} met, {held:.0%} holding "
                    f"(needs {INTRODUCED_TARGET:.0%} and {HELD_FRACTION:.0%} to move on).")


def report(store: Store, course: Course, tally) -> None:
    """End-of-session summary: what grew, never what was missed."""
    if not tally.reviews:
        return
    minutes = tally.seconds / 60
    span = f"{minutes:.0f} minutes" if minutes >= 1.5 else "under a minute"
    states = store.all_states()

    rows = []
    for label in sorted(tally.by_kind, key=lambda k: -tally.by_kind[k]):
        cards = [c for c in course.cards.values() if c.label == label]
        seen = [c for c in cards if c.id in states]
        strength = (sum(states[c.id].strength for c in seen) / len(cards)) if cards else 0
        rows.append((label, strength,
                     f"+{tally.by_kind[label]} this session · {len(seen)}/{len(cards)} met"))

    from . import encourage
    headline = f"{tally.reviews} reviews in {span}."
    if tally.introduced:
        headline += f"  {tally.introduced} new."
    if tally.recovered:
        headline += f"  {tally.recovered} came back and stuck."

    streak = store.streak()
    footer = encourage.session_close(minutes, tally.reviews)
    footer += f"   Streak: {streak} day{'s' if streak != 1 else ''}."
    ui.console.print()
    ui.summary(rows, headline, footer)
