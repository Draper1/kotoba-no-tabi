"""The review loop.

Queue policy: cards that are due come first, new material is introduced in
small doses behind it, and anything that didn't land is re-inserted a few cards
later so it gets a second look while the teaching is still fresh — rather than
being pushed to tomorrow, which is when it would be forgotten.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field

from . import encourage, ui
from .content import Card, Course
from .kana import check
from .srs import GOT_IT, NOT_YET, grade_for
from .store import Store

# How many cards later a missed card reappears.
RELEARN_GAP = 5

QUIT = {":q", ":quit", ":x"}
SKIP = {"?", ":?", ":skip"}


@dataclass
class Tally:
    reviews: int = 0
    landed: int = 0
    taught: int = 0
    recovered: int = 0
    introduced: int = 0
    seconds: float = 0.0
    by_kind: dict[str, int] = field(default_factory=dict)

    def note(self, card: Card) -> None:
        self.by_kind[card.label] = self.by_kind.get(card.label, 0) + 1


class Session:
    def __init__(
        self,
        course: Course,
        store: Store,
        minutes: float = 20.0,
        new_limit: int = 12,
        kinds: tuple[str, ...] | None = None,
        units: tuple[int, ...] | None = None,
        tags: tuple[str, ...] | None = None,
        interlude=None,
    ):
        self.course = course
        self.store = store
        self.minutes = minutes
        self.new_limit = new_limit
        self.kinds = kinds
        self.units = units
        self.tags = tags
        # Optional callback(cards_done) used by the adventure to drop story
        # beats between cards. Review mode leaves it unset.
        self.interlude = interlude
        self.tally = Tally()
        self.missed_this_session: set[str] = set()

    # --- queue ------------------------------------------------------------
    def _eligible(self) -> list[Card]:
        cards = list(self.course.cards.values())
        if self.kinds:
            cards = [c for c in cards if c.kind in self.kinds]
        if self.units is not None:
            cards = [c for c in cards if c.unit in self.units]
        if self.tags:
            cards = [c for c in cards if any(t in c.tags for t in self.tags)]
        return cards

    def build_queue(self) -> list[str]:
        eligible = self._eligible()
        ids = [c.id for c in eligible]
        due = self.store.due_ids(ids)
        seen = self.store.seen_ids()

        fresh = [c for c in eligible if c.id not in seen]
        # Introduce in teaching order: earlier chapters first, and within a
        # chapter meet the vocabulary before the grammar that uses it.
        fresh.sort(key=lambda c: (c.unit, c.teach_rank, c.order, c.id))
        new_ids = [c.id for c in fresh[: self.new_limit]]

        random.shuffle(due)
        queue: list[str] = []
        # Interleave new material through the due pile rather than front-loading
        # it, so a session doesn't open with a wall of unfamiliar cards.
        if new_ids and due:
            step = max(1, len(due) // len(new_ids))
            n = iter(new_ids)
            for i, cid in enumerate(due):
                queue.append(cid)
                if i % step == step - 1:
                    nxt = next(n, None)
                    if nxt:
                        queue.append(nxt)
            queue.extend(n)
        else:
            queue = due + new_ids
        return queue

    # --- one card ---------------------------------------------------------
    def present(self, card: Card, position: str) -> bool:
        """Show one card. Returns False if the learner asked to stop."""
        seen_before = card.id in self.store.seen_ids()
        if not seen_before:
            ui.note("new — take a look, then answer", ui.ACCENT)
        ui.card(card.prompt, card.instruction, card.context, card.label, position)

        try:
            answer, elapsed = ui.ask()
        except (EOFError, KeyboardInterrupt):
            return False

        if answer.lower() in QUIT:
            return False

        asked_to_see = answer == "" or answer.lower() in SKIP
        if asked_to_see:
            match_ok, typo = False, False
        else:
            m = check(answer, card.answers, english=card.english,
                      vocabulary=self.course.vocabulary)
            match_ok, typo = m.ok, m.typo

        grade = grade_for(match_ok, typo, elapsed) if match_ok else NOT_YET
        recovered = match_ok and card.id in self.missed_this_session

        self.store.record(card.id, grade, ms=int(elapsed * 1000))
        self.tally.reviews += 1
        self.tally.note(card)
        if not seen_before:
            self.tally.introduced += 1

        if match_ok:
            self.tally.landed += 1
            if recovered:
                self.tally.recovered += 1
                self.missed_this_session.discard(card.id)
            detail = card.reveal if card.kind != "kana_read" else ""
            ui.landed(encourage.for_answer(True, typo, elapsed <= 6.0, recovered), detail)
        else:
            self.tally.taught += 1
            self.missed_this_session.add(card.id)
            opener = ("Here it is:" if asked_to_see
                      else encourage.for_answer(False, False, False))
            ui.teach(opener, card.reveal, card.teach, encourage.closer())

        mark = encourage.milestone(self.store.total_reviews())
        if mark:
            ui.milestone(mark)
        return True

    # --- run --------------------------------------------------------------
    def run(self) -> Tally:
        queue = self.build_queue()
        if not queue:
            ui.note("Nothing is due right now — everything is resting. "
                    "Try 'learn' to pick up new material.")
            return self.tally

        started = time.monotonic()
        deadline = started + self.minutes * 60 if self.minutes else None
        relearn: list[tuple[int, str]] = []
        i = 0
        served = 0

        while queue or relearn:
            if deadline and time.monotonic() > deadline:
                ui.note("That's the time you set — good place to stop.", ui.ACCENT)
                break

            cid = None
            if relearn and relearn[0][0] <= served:
                _, cid = relearn.pop(0)
            elif i < len(queue):
                cid = queue[i]
                i += 1
            elif relearn:
                _, cid = relearn.pop(0)
            if cid is None:
                break

            card = self.course.cards[cid]
            total = len(queue) + len(relearn)
            if not self.present(card, f"{served + 1}/{total}"):
                break
            served += 1
            if self.interlude:
                self.interlude(served)

            if cid in self.missed_this_session:
                relearn.append((served + RELEARN_GAP, cid))
                relearn.sort(key=lambda r: r[0])

        self.tally.seconds = time.monotonic() - started
        self.store.add_time(self.tally.seconds, learned=self.tally.introduced)
        return self.tally
