"""Feedback lines.

House style, and the reason this is its own module:

  * Nothing is ever "wrong". A card that didn't arrive is one you haven't
    finished learning *yet*, and the response to it is to teach, not to mark.
  * Never red. Red means error, and the learner made no error by not yet
    knowing something. Misses are shown in calm blue.
  * No running tally of misses, anywhere.
  * Effort is acknowledged separately from accuracy, because on a hard day
    they are not the same thing.

Lines rotate without immediate repeats so praise doesn't turn into wallpaper.
"""

from __future__ import annotations

import random

PERFECT = [
    "そう！ Instant.", "Straight out.", "No hesitation — that's solid.",
    "Locked in.", "That one's yours.", "Quick and clean.",
    "You didn't even pause.", "完璧 — perfect.",
]

GOOD = [
    "そうです！", "That's it.", "Correct.", "Yes — well held.",
    "Good.", "Right on.", "その通り — exactly.", "Nicely done.",
    "Got it.", "はい、正解です。",
]

TYPO = [
    "That's the one — just a slip of the fingers.",
    "You knew it; the keyboard didn't.",
    "Right answer, stray key. Counting it.",
    "That's it — spelling wobbled, knowledge didn't.",
    "Close enough to call it: you had it.",
]

# Deliberately framed as "here it is", never as a correction.
TEACH_OPENERS = [
    "Here's this one:", "Let's look at it:", "This one's still settling:",
    "Take a look:", "Here it is:", "Worth a second look:",
    "Not settled yet — here it is:", "Let's plant this one:",
]

TEACH_CLOSERS = [
    "It'll come back around shortly.",
    "You'll see it again in a minute.",
    "Back soon so it can stick.",
    "I'll bring it round again.",
    "Coming back shortly — no rush.",
]

# Shown when a card they'd previously missed comes back correct.
RECOVERED = [
    "There it is — that's the one you were chasing.",
    "Came back and got it. That's how it sticks.",
    "Second time around and it landed.",
    "That's the one from earlier — yours now.",
]

SESSION_OPEN = [
    "Let's get into it.", "Right — where were we.",
    "Good to see you back.", "Let's pick up the thread.",
]

# Effort-based, so a hard session still ends well.
SESSION_CLOSE_STRONG = [
    "Strong session. That's real ground covered.",
    "That was a good stretch of work.",
    "Excellent run — you kept the pace up.",
]
SESSION_CLOSE_STEADY = [
    "Steady work. This is the kind that adds up.",
    "Good session — consistency is the whole game.",
    "That's another one banked.",
]
SESSION_CLOSE_SHORT = [
    "Short and sharp — still counts, and the streak holds.",
    "Even a few minutes keeps it warm. Well done for showing up.",
    "Brief one today, and that's completely fine.",
]

_last: dict[int, str] = {}


def pick(pool: list[str]) -> str:
    """A random line, but never the same one twice running."""
    key = id(pool)
    if len(pool) > 1:
        choices = [p for p in pool if p != _last.get(key)]
    else:
        choices = pool
    line = random.choice(choices)
    _last[key] = line
    return line


def for_answer(correct: bool, typo: bool, fast: bool, recovered: bool = False) -> str:
    if not correct:
        return pick(TEACH_OPENERS)
    if typo:
        return pick(TYPO)
    if recovered:
        return pick(RECOVERED)
    return pick(PERFECT if fast else GOOD)


def closer() -> str:
    return pick(TEACH_CLOSERS)


def session_close(minutes: float, reviews: int) -> str:
    if minutes >= 20 or reviews >= 60:
        return pick(SESSION_CLOSE_STRONG)
    if minutes >= 7 or reviews >= 20:
        return pick(SESSION_CLOSE_STEADY)
    return pick(SESSION_CLOSE_SHORT)


def milestone(total_reviews: int) -> str | None:
    """Occasional, genuinely-earned markers. Returns None most of the time."""
    marks = {
        50: "50 reviews in. The habit is forming.",
        100: "100 reviews. That's a real foundation.",
        250: "250 reviews — you're well into this now.",
        500: "500 reviews. Serious mileage.",
        1000: "1,000 reviews. That is a lot of Japanese.",
        2500: "2,500 reviews. Genuinely impressive commitment.",
        5000: "5,000 reviews. You've built something here.",
    }
    return marks.get(total_reviews)
