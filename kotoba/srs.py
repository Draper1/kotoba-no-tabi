"""Spaced repetition scheduling.

An SM-2 variant, tuned for a 14-week exam run rather than for lifetime
retention: intervals are capped so nothing disappears past exam day, and a
missed card returns within the same session instead of tomorrow.

The four grades are deliberately not named after failure. Internally they are
just spacing signals; the player only ever sees encouragement.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

NOT_YET = 0   # didn't arrive - show it again shortly, and teach it
ALMOST = 1    # right idea, slight slip - nudge, don't punish
GOT_IT = 2    # correct
INSTANT = 3   # correct and fast - clearly solid, stretch the interval

MINUTE = 60
DAY = 86400

# Learning steps for a brand-new card, in seconds.
STEPS = (60, 600, DAY)

EASE_START = 2.5
EASE_MIN = 1.3
EASE_MAX = 3.0

MIN_INTERVAL = 60.0
MAX_INTERVAL = 120 * DAY

# How much of the displayed progress bar a single lapse can cost.
LAPSE_COST = 0.10


@dataclass(frozen=True)
class CardState:
    card_id: str
    due: float = 0.0
    interval: float = 0.0     # seconds
    ease: float = EASE_START
    reps: int = 0
    lapses: int = 0
    step: int = 0             # index into STEPS; -1 once graduated
    introduced: float = 0.0
    last_seen: float = 0.0
    peak: float = 0.0         # high-water mark of strength; see .strength

    @property
    def is_new(self) -> bool:
        return self.reps == 0

    @property
    def graduated(self) -> bool:
        return self.step < 0

    @property
    def raw_strength(self) -> float:
        """Strength implied by the current interval alone."""
        if self.reps == 0:
            return 0.0
        if not self.graduated:
            return 0.05 + 0.10 * (self.step / max(1, len(STEPS)))
        # 21 days of retained interval reads as "solid" for an N5 timeframe.
        return min(1.0, 0.15 + 0.85 * min(1.0, self.interval / (21 * DAY)))

    @property
    def strength(self) -> float:
        """0.0-1.0, for progress bars.

        Deliberately NOT the raw interval. One slip on a mature card drops the
        interval to a minute, and showing that as 100% -> 5% would tell the
        learner they had lost months of work for a single lapse. What they have
        actually lost is a little confidence in one card, so the displayed bar
        falls back only to just under its high-water mark and re-earns the rest.

        The mark itself erodes on each lapse, so a card that is repeatedly
        missed does drift down honestly rather than sitting at a flattering
        number forever. Encouraging is not the same as untrue.
        """
        return max(self.raw_strength, self.peak)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _fuzz(seconds: float) -> float:
    """Scatter due times slightly so cards don't arrive in clumps."""
    if seconds < DAY:
        return seconds
    return seconds * random.uniform(0.95, 1.05)


def schedule(state: CardState, grade: int, now: float) -> CardState:
    """Return the card's next state after a review."""
    ease = state.ease
    interval = state.interval
    step = state.step
    lapses = state.lapses

    if not state.graduated:
        # --- still in the learning phase ---
        if grade == NOT_YET:
            step = 0
        elif grade == ALMOST:
            step = max(0, step)          # repeat the current step
        elif grade == GOT_IT:
            step += 1
        else:                            # INSTANT - skip a step
            step += 2

        if step >= len(STEPS):
            step = -1                    # graduated
            interval = DAY if grade != INSTANT else 3 * DAY
        else:
            interval = STEPS[step]
    else:
        # --- graduated ---
        if grade == NOT_YET:
            lapses += 1
            ease -= 0.20
            step = 0                     # brief relearning, back in this session
            interval = STEPS[0]
        elif grade == ALMOST:
            ease -= 0.05
            interval = max(interval * 1.2, DAY)
        elif grade == GOT_IT:
            interval = max(interval * ease, DAY)
        else:
            ease += 0.05
            interval = max(interval * ease * 1.3, 2 * DAY)

    peak = max(0.0, state.peak - LAPSE_COST) if grade == NOT_YET else state.peak
    ease = _clamp(ease, EASE_MIN, EASE_MAX)
    interval = _clamp(interval, MIN_INTERVAL, MAX_INTERVAL)

    nxt = replace(
        state,
        due=now + _fuzz(interval),
        interval=interval,
        ease=ease,
        reps=state.reps + 1,
        lapses=lapses,
        step=step,
        introduced=state.introduced or now,
        last_seen=now,
    )
    return replace(nxt, peak=max(peak, nxt.raw_strength))


def grade_for(correct: bool, typo: bool, elapsed: float, fast: float = 6.0) -> int:
    """Map an answer to a spacing signal.

    Speed is treated as evidence of strength, never of worth: a slow correct
    answer is still correct, it just comes back sooner.
    """
    if not correct:
        return NOT_YET
    if typo:
        return ALMOST
    return INSTANT if elapsed <= fast else GOT_IT
