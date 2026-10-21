"""Terminal presentation.

Colour rules follow from the positive-only brief: green for landed, blue for
still-settling, gold for milestones. Red is never used for anything the
learner did — it reads as an error, and not yet knowing something isn't one.
"""

from __future__ import annotations

import shutil
import time

from rich.align import Align
from rich.box import HEAVY, ROUNDED
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(highlight=False)

ACCENT = "bright_cyan"
GOOD = "bright_green"
TEACH = "bright_blue"      # deliberately not red
DIM = "grey58"
GOLD = "yellow"
JP = "bold white"


def width() -> int:
    return min(shutil.get_terminal_size((80, 24)).columns, 84)


def clear() -> None:
    console.clear()


def rule(text: str = "") -> None:
    console.rule(Text(text, style=DIM) if text else "", style=DIM)


def banner(streak: int, due: int, minutes_today: float, goal: int) -> None:
    left = Text("言葉の旅 ", style=f"bold {ACCENT}")
    left.append("Kotoba no Tabi", style=DIM)
    bits = []
    if streak:
        bits.append(f"🔥 {streak} day{'s' if streak != 1 else ''}")
    bits.append(f"{due} waiting" if due else "all caught up")
    bits.append(f"{minutes_today:.0f}/{goal} min today")
    right = Text("   ".join(bits), style=DIM)
    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="right")
    grid.add_row(left, right)
    console.print(grid, width=width())
    console.print()


def scene(title: str, jp_title: str, body: str) -> None:
    head = Text(f"{jp_title}  ", style=f"bold {ACCENT}")
    head.append(title, style="bold white")
    console.print(Panel(
        Text(body, style="white"), title=head, title_align="left",
        border_style=ACCENT, box=ROUNDED, padding=(1, 3), width=width(),
    ))
    console.print()


def speech(who: str, jp: str, en: str = "") -> None:
    body = Text(jp, style=JP)
    if en:
        body.append(f"\n{en}", style=DIM)
    console.print(Panel(
        body, title=Text(who, style=ACCENT), title_align="left",
        border_style=DIM, box=ROUNDED, padding=(0, 2), width=width(),
    ))


def card(prompt: str, instruction: str, context: str, label: str, number: str) -> None:
    """The question itself: the Japanese large and centred, everything else quiet."""
    inner = [Align.center(Text(prompt, style=f"bold {ACCENT}"))]
    if context:
        inner.append(Align.center(Text(context, style=DIM)))
    console.print(Panel(
        Group(*inner),
        title=Text(f" {label} ", style=DIM), title_align="left",
        subtitle=Text(f" {number} ", style=DIM), subtitle_align="right",
        border_style=DIM, box=HEAVY, padding=(1, 2), width=width(),
    ))
    console.print(Text(f"  {instruction}", style=DIM))


def ask(hint: str = "") -> tuple[str, float]:
    """Read an answer, returning it with how long it took."""
    console.print(Text("  › ", style=ACCENT), end="")
    start = time.monotonic()
    try:
        answer = input()
    except (EOFError, KeyboardInterrupt):
        raise
    return answer.strip(), time.monotonic() - start


def landed(message: str, detail: str = "") -> None:
    line = Text("  ✓ ", style=GOOD)
    line.append(message, style=GOOD)
    console.print(line)
    if detail:
        console.print(Text(f"    {detail}", style=DIM))
    console.print()


def teach(opener: str, reveal: str, note: str, closer: str) -> None:
    """The 'not yet' path. Warm, informative, and never marked as a failure."""
    console.print(Text(f"  {opener}", style=TEACH))
    console.print(Text(f"    {reveal}", style=f"bold {TEACH}"))
    if note:
        for chunk in _wrap(note, width() - 6):
            console.print(Text(f"    {chunk}", style=DIM))
    console.print(Text(f"    {closer}", style=DIM))
    console.print()


def note(text: str, style: str = DIM) -> None:
    console.print(Text(f"  {text}", style=style))


def milestone(text: str) -> None:
    console.print()
    console.print(Panel(
        Align.center(Text(text, style=f"bold {GOLD}")),
        border_style=GOLD, box=ROUNDED, padding=(0, 2), width=width(),
    ))
    console.print()


def bar(value: float, size: int = 24, style: str = GOOD) -> Text:
    filled = int(round(value * size))
    t = Text("█" * filled, style=style)
    t.append("░" * (size - filled), style=DIM)
    return t


def summary(rows: list[tuple[str, float, str]], headline: str, footer: str) -> None:
    """End-of-session panel. Reports what grew; never what was missed."""
    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left", style="white", min_width=16)
    table.add_column(justify="left")
    table.add_column(justify="left", style=DIM)
    for name, value, detail in rows:
        table.add_row(name, bar(value), detail)
    body = Group(Text(headline, style=f"bold {GOOD}"), Text(""), table,
                 Text(""), Text(footer, style=DIM))
    console.print(Panel(body, border_style=GOOD, box=ROUNDED,
                        padding=(1, 3), width=width()))


def menu(title: str, options: list[tuple[str, str, str]]) -> str:
    """options: (key, label, detail). Returns the chosen key."""
    console.print(Text(title, style=f"bold {ACCENT}"))
    console.print()
    for key, label, detail in options:
        line = Text(f"  {key}", style=f"bold {ACCENT}")
        line.append(f"  {label}", style="white")
        if detail:
            line.append(f"   {detail}", style=DIM)
        console.print(line)
    console.print()
    valid = {k.lower() for k, _, _ in options}
    while True:
        console.print(Text("  › ", style=ACCENT), end="")
        try:
            choice = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "q"
        if choice in valid:
            return choice
        note("Pick one of the letters above.", DIM)


def _wrap(text: str, w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        if _w(cur) + _w(word) + 1 > w and cur:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def _w(s: str) -> int:
    """Display width, counting CJK characters as two cells."""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
