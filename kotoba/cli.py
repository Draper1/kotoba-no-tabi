"""Entry point, menus, calibration and progress."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime

from . import encourage, ui
from .adventure import Adventure, report
from .content import Course
from .session import Session
from .srs import DAY, GOT_IT
from .store import DB_PATH, Store

# JLPT is held on the first Sunday of December.
DEFAULT_EXAM = "2026-12-06"
DEFAULT_GOAL_MINUTES = 85          # ~10 hours a week


# --- calibration ----------------------------------------------------------
def seed_known(store: Store, card_ids: list[str], reps: int = 4) -> None:
    """Give already-known cards a head start via backdated review events.

    Written into the event log rather than straight into card_state, so a
    rebuild (or a future sync) reproduces it exactly.
    """
    now = time.time()
    spacing = [30 * DAY, 14 * DAY, 5 * DAY, 1 * DAY, 0][-reps:]
    for cid in card_ids:
        for back in spacing:
            store.record(cid, GOT_IT, ms=0, now=now - back)


def calibrate(store: Store, course: Course) -> None:
    ui.clear()
    ui.console.print()
    ui.note("Before we start — a couple of questions so you're not drilled on "
            "things you already know.", ui.ACCENT)
    ui.console.print()

    for script, label in (("hiragana", "hiragana"), ("katakana", "katakana")):
        choice = ui.menu(
            f"How solid is your {label}?",
            [("a", "Solid", "I read it fluently, including dakuten and combos"),
             ("b", "Mostly there", "I know most of it but some are slow"),
             ("c", "From scratch", "start me at the beginning")],
        )
        cards = [c.id for c in course.by_tag(script)]
        if choice == "a":
            seed_known(store, cards, reps=4)
            ui.note(f"Good — {label} set aside as known. It'll still surface "
                    f"occasionally to stay warm.")
        elif choice == "b":
            seed_known(store, cards, reps=2)
            ui.note(f"Noted — {label} will come round sooner rather than from zero.")
        else:
            ui.note(f"We'll build {label} up from the start.")
        ui.console.print()

    store.set("calibrated", "1")
    store.set("exam_date", DEFAULT_EXAM)
    store.set("goal_minutes", str(DEFAULT_GOAL_MINUTES))
    ui.note("That's it. Everything else the game works out as you go.", ui.ACCENT)
    ui.console.print()
    input("  Press Enter to begin. ")


# --- progress -------------------------------------------------------------
def show_progress(store: Store, course: Course) -> None:
    ui.clear()
    states = store.all_states()
    ui.console.print()
    ui.note("PROGRESS", ui.ACCENT)
    ui.console.print()

    groups: dict[str, list] = {}
    for c in course.cards.values():
        groups.setdefault(c.label, []).append(c)

    table_rows = []
    for label, cards in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        seen = [c for c in cards if c.id in states]
        strength = sum(states[c.id].strength for c in seen) / len(cards) if cards else 0
        table_rows.append((label, strength, f"{len(seen)}/{len(cards)} met"))

    total_cards = len(course.cards)
    total_seen = len(states)
    overall = sum(s.strength for s in states.values()) / total_cards if total_cards else 0

    for label, strength, detail in table_rows:
        line = ui.Text(f"  {label:<16}", style="white")
        line.append_text(ui.bar(strength))
        line.append(f"  {strength:>4.0%}  {detail}", style=ui.DIM)
        ui.console.print(line)

    ui.console.print()
    line = ui.Text(f"  {'overall':<16}", style=f"bold white")
    line.append_text(ui.bar(overall, style=ui.ACCENT))
    line.append(f"  {overall:>4.0%}  {total_seen}/{total_cards} met", style=ui.DIM)
    ui.console.print(line)
    ui.console.print()

    # Exam pacing
    exam = store.get("exam_date", DEFAULT_EXAM)
    try:
        days_left = (datetime.strptime(exam, "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        days_left = None

    hist = store.history(14)
    mins = sum(h["seconds"] for h in hist) / 60
    goal = int(store.get("goal_minutes", str(DEFAULT_GOAL_MINUTES)))
    streak = store.streak()

    ui.note(f"Streak {streak} day{'s' if streak != 1 else ''}"
            f" · {store.total_reviews()} reviews all time"
            f" · {mins/max(1,len(hist)):.0f} min/day over the last {len(hist)} day(s)")
    if days_left is not None and days_left > 0:
        remaining = total_cards - total_seen
        ui.note(f"JLPT N5 on {exam}: {days_left} days away. "
                f"{remaining} cards not yet met — about {remaining/max(1,days_left):.0f} new a day "
                f"to have seen everything once.")
        ui.note(f"Target {goal} min/day ({goal*7/60:.0f} h/week).")
    ui.console.print()
    input("  Press Enter to go back. ")


def show_sync(store: Store) -> None:
    ui.clear()
    ui.console.print()
    ui.note("SAVE & SYNC", ui.ACCENT)
    ui.console.print()
    ui.note(f"Save file: {store.path}")
    ui.note(f"Device:    {store.get('device_id')}")
    ui.note(f"Reviews:   {store.total_reviews()}")
    ui.console.print()
    ui.note("Progress is stored as an append-only log of every review, so two")
    ui.note("machines can be merged without losing anything:")
    ui.console.print()
    ui.note("  kotoba export > save.json      # on machine A", "white")
    ui.note("  kotoba import save.json        # on machine B", "white")
    ui.console.print()
    ui.note("Remote sync isn't wired up yet — this is the seam it will use.")
    ui.console.print()
    input("  Press Enter to go back. ")


# --- menu -----------------------------------------------------------------
def main_menu(store: Store, course: Course) -> None:
    adv = Adventure(course, store)
    while True:
        ui.clear()
        due = len(store.due_ids(course.ids()))
        unit = adv.current_unit()
        meta = course.units[unit]
        ui.banner(store.streak(), due, store.day_stats()["seconds"] / 60,
                  int(store.get("goal_minutes", str(DEFAULT_GOAL_MINUTES))))

        choice = ui.menu("What would you like to do?", [
            ("j", "Continue the journey", f"Chapter {unit} · {meta['jp']} {meta['title']}"),
            ("r", "Review what's due", f"{due} waiting" if due else "nothing due — all rested"),
            ("k", "Katakana drill", "your weakest script"),
            ("g", "Grammar drill", "particles and verb forms"),
            ("v", "Vocabulary drill", "nouns and verbs"),
            ("p", "Progress", ""),
            ("s", "Save & sync", ""),
            ("q", "Quit", ""),
        ])

        if choice == "q":
            ui.console.print()
            ui.note("またね。See you soon.", ui.ACCENT)
            ui.console.print()
            return
        if choice == "p":
            show_progress(store, course); continue
        if choice == "s":
            show_sync(store); continue
        if choice == "j":
            adv.play(); pause(); continue

        kinds, tags, title = None, None, ""
        if choice == "r":
            title = "Review"
        elif choice == "k":
            kinds, tags, title = ("kana_read",), ("katakana",), "Katakana"
        elif choice == "g":
            kinds, title = ("grammar",), "Grammar"
        elif choice == "v":
            kinds = ("vocab_recognise", "vocab_produce", "verb_masu")
            title = "Vocabulary"

        ui.clear()
        ui.banner(store.streak(), due, store.day_stats()["seconds"] / 60,
                  int(store.get("goal_minutes", str(DEFAULT_GOAL_MINUTES))))
        ui.note(f"{title} — Enter on a card you don't know and it'll show you. "
                f":q to stop.", ui.ACCENT)
        ui.console.print()
        s = Session(course, store, minutes=20, new_limit=12, kinds=kinds, tags=tags)
        report(store, course, s.run())
        pause()


def pause() -> None:
    ui.console.print()
    try:
        input("  Press Enter to continue. ")
    except (EOFError, KeyboardInterrupt):
        pass


# --- argv -----------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kotoba", description="Learn Japanese to JLPT N5.")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("play", help="the main menu (default)")
    sub.add_parser("review", help="go straight into due reviews")
    sub.add_parser("progress", help="show progress and exam pacing")
    sub.add_parser("export", help="write the save to stdout as JSON")
    imp = sub.add_parser("import", help="merge a save file in")
    imp.add_argument("file")
    sub.add_parser("rebuild", help="replay the review log and rebuild state")
    args = p.parse_args(argv)

    store = Store(DB_PATH)
    course = Course()

    if args.cmd == "export":
        json.dump(store.export(), sys.stdout, ensure_ascii=False)
        return 0
    if args.cmd == "import":
        with open(args.file, encoding="utf-8") as f:
            result = store.import_(json.load(f))
        print(f"merged: +{result['added']} reviews, {result['cards']} cards rebuilt")
        return 0
    if args.cmd == "rebuild":
        print(f"rebuilt {store.rebuild()} cards from {store.total_reviews()} reviews")
        return 0

    if not store.get("calibrated"):
        calibrate(store, course)

    if args.cmd == "progress":
        show_progress(store, course)
        return 0
    if args.cmd == "review":
        s = Session(course, store, minutes=20, new_limit=12)
        report(store, course, s.run())
        return 0

    try:
        main_menu(store, course)
    except (KeyboardInterrupt, EOFError):
        ui.console.print()
        ui.note("Stopped — progress saved.", ui.ACCENT)
    finally:
        store.close()
    return 0
