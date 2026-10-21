"""Loads the content packs and expands them into review cards.

One source item becomes several cards, because recognising a word and
producing it are genuinely different skills. Card ids are stable strings so
that scheduling state survives content edits: adding a word never disturbs
what you already know.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .kana import normalize

CONTENT_DIR = os.path.join(os.path.dirname(__file__), "content")

# The order a chapter introduces its material: meet a word, learn to write and
# read it, then produce it, then use it in a sentence. Grammar drills come last
# because they lean on vocabulary the learner should already have met.
KIND_ORDER = {
    "kana_read": 0,
    "vocab_recognise": 1,
    "kanji_meaning": 2,
    "kanji_reading": 3,
    "vocab_produce": 4,
    "verb_masu": 5,
    "grammar": 6,
}

# Card kinds, and how they are described in the UI.
KIND_LABEL = {
    "kana_read": "kana",
    "vocab_recognise": "vocabulary",
    "vocab_produce": "vocabulary",
    "verb_masu": "verb form",
    "kanji_meaning": "kanji",
    "kanji_reading": "kanji reading",
    "grammar": "grammar",
}


# A handful of verbs whose kanji hides a stem vowel change, so the rule below
# cannot derive them.
_MASU_EXCEPTIONS = {"来る": "来ます"}


def _kanji_masu(jp: str, kana: str, masu: str) -> str | None:
    """Write the ます-form using the same kanji the dictionary form uses.

    たべる/たべます share the stem たべ, so 食べる loses る and gains ます.
    Without this, an IME user typing 食べます would be told "not yet" for an
    answer that is completely correct.
    """
    if jp == kana:
        return None
    if jp in _MASU_EXCEPTIONS:
        return _MASU_EXCEPTIONS[jp]
    n = 0
    while n < min(len(kana), len(masu)) and kana[n] == masu[n]:
        n += 1
    tail, masu_tail = kana[n:], masu[n:]
    if tail and jp.endswith(tail):
        return jp[: -len(tail)] + masu_tail
    return None


@dataclass
class Card:
    id: str
    kind: str
    unit: int
    prompt: str                       # the big line the learner reads
    instruction: str                  # what to do with it
    answers: list[str]
    english: bool = False             # compare as English rather than kana?
    context: str = ""                 # smaller line under the prompt
    reveal: str = ""                  # the full answer, shown when teaching
    teach: str = ""                   # mnemonic / rule / contrast
    tags: list[str] = field(default_factory=list)
    order: int = 0                    # teaching order within a unit

    @property
    def label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def teach_rank(self) -> int:
        return KIND_ORDER.get(self.kind, 99)


class Course:
    def __init__(self, directory: str = CONTENT_DIR):
        self.dir = directory
        self.kana = self._load("kana.json")
        self.vocab = self._load("vocab.json")
        self.kanji = self._load("kanji.json")
        self.grammar = self._load("grammar.json")
        self.units = {int(k): v for k, v in self.vocab["units"].items()}
        self.cards: dict[str, Card] = {}
        self._build()
        # Every Japanese string the course could ever expect as an answer --
        # dictionary forms, ます-forms, kanji spellings, kana, particles.
        #
        # The answer checker uses this to tell a typo apart from a genuine
        # mix-up: "kimasu" is one edit from いきます, but it is also 来ます, a real
        # word, so it must not be waved through as a slip. Building this from
        # the card answers (rather than a hand-kept list) means every form the
        # game can ask for is automatically protected.
        self.vocabulary = frozenset(
            n for card in self.cards.values() if not card.english
            for a in card.answers
            if (n := normalize(a))
        )

    def _load(self, name: str) -> dict:
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return json.load(f)

    def _add(self, card: Card) -> None:
        if card.id in self.cards:
            raise ValueError(f"duplicate card id: {card.id}")
        self.cards[card.id] = card

    # --- card construction ------------------------------------------------
    def _build(self) -> None:
        self._build_kana()
        self._build_vocab()
        self._build_kanji()
        self._build_grammar()

    def _build_kana(self) -> None:
        for script in ("hiragana", "katakana"):
            for it in self.kana[script]:
                self._add(Card(
                    id=f"{it['id']}:read",
                    kind="kana_read",
                    unit=0,
                    prompt=it["char"],
                    instruction=f"Read this {script} character",
                    answers=[it["romaji"]],
                    context="",
                    reveal=f"{it['char']}  =  {it['romaji']}",
                    teach=it.get("mnemonic", ""),
                    tags=[script, f"tier{it['tier']}"],
                    order=it["order"],
                ))

    def _build_vocab(self) -> None:
        for it in self.vocab["items"]:
            jp, kana, en = it["jp"], it["kana"], it["en"]
            written = jp if jp != kana else kana
            reading_note = f"{kana}" if jp != kana else ""
            # Recognition: see the Japanese, give the meaning.
            self._add(Card(
                id=f"{it['id']}:r",
                kind="vocab_recognise",
                unit=it["unit"],
                prompt=written,
                instruction="What does this mean?",
                answers=en,
                english=True,
                context=reading_note,
                reveal=f"{written}  ({kana})  —  {'; '.join(en)}",
                teach=f"{it['pos_name']}",
                tags=[it["pos_name"]],
                order=it["seq"],
            ))
            # Production: see the meaning, give the Japanese.
            self._add(Card(
                id=f"{it['id']}:p",
                kind="vocab_produce",
                unit=it["unit"],
                prompt="; ".join(en),
                instruction="How do you say this in Japanese?",
                answers=[kana, jp] if jp != kana else [kana],
                context=f"({it['pos_name']})",
                order=it["seq"],
                reveal=f"{written}  ({kana})  —  {'; '.join(en)}",
                teach="",
                tags=[it["pos_name"]],
            ))
            # Verbs also drill the polite form, which N5 leans on heavily.
            if it.get("masu"):
                cls = {"u": "う-verb", "ru": "る-verb", "irr": "irregular"}[it["verb_class"]]
                masu_kanji = _kanji_masu(jp, kana, it["masu"])
                masu_answers = [it["masu"]] + ([masu_kanji] if masu_kanji else [])
                self._add(Card(
                    id=f"{it['id']}:masu",
                    kind="verb_masu",
                    unit=it["unit"],
                    prompt=written,
                    instruction="Give the polite (ます) form",
                    answers=masu_answers,
                    context=f"{kana} — {'; '.join(en)}",
                    reveal=f"{written} → {masu_kanji or it['masu']}  ({it['masu']})",
                    teach=f"This is a {cls}.",
                    tags=["verb", cls],
                    order=it["seq"],
                ))

    def _build_kanji(self) -> None:
        for it in self.kanji["items"]:
            ch = it["char"]
            readings = " ・ ".join(it["on"] + it["kun"])
            self._add(Card(
                id=f"{it['id']}:m",
                kind="kanji_meaning",
                unit=it["unit"],
                prompt=ch,
                instruction="What does this kanji mean?",
                answers=it["meanings"],
                english=True,
                context="",
                reveal=f"{ch}  —  {'; '.join(it['meanings'])}",
                teach=f"Readings: {readings}",
                tags=["kanji"],
                order=it["seq"],
            ))
            # Reading a real word is the skill the exam actually tests.
            for n, ex in enumerate(it["examples"]):
                self._add(Card(
                    id=f"{it['id']}:w{n}",
                    kind="kanji_reading",
                    unit=it["unit"],
                    prompt=ex["jp"],
                    instruction="How is this read?",
                    answers=[ex["kana"]],
                    context=ex["en"],
                    reveal=f"{ex['jp']}  =  {ex['kana']}  —  {ex['en']}",
                    teach=f"{ch} — {'; '.join(it['meanings'])}. Readings: {readings}",
                    tags=["kanji", "reading"],
                    order=it["seq"] * 10 + n,
                ))

    def _build_grammar(self) -> None:
        for it in self.grammar["items"]:
            teach = it["note"]
            if it.get("contrast"):
                teach = (teach + "  " + it["contrast"]).strip()
            for n, d in enumerate(it["drills"]):
                self._add(Card(
                    id=f"{it['id']}:d{n}",
                    kind="grammar",
                    unit=it["unit"],
                    prompt=d["jp"],
                    instruction="Fill in the blank ＿",
                    answers=d["answers"],
                    context=d["en"],
                    reveal=d["jp"].replace("＿", f"【{d['answers'][0]}】"),
                    teach=f"{it['title']} — {it['form']}. {teach}".strip(),
                    tags=["grammar", it["title"]],
                    order=it["seq"] * 10 + n,
                ))

    # --- selection --------------------------------------------------------
    def by_kind(self, *kinds: str) -> list[Card]:
        return [c for c in self.cards.values() if c.kind in kinds]

    def by_unit(self, unit: int) -> list[Card]:
        return [c for c in self.cards.values() if c.unit == unit]

    def by_tag(self, tag: str) -> list[Card]:
        return [c for c in self.cards.values() if tag in c.tags]

    def ids(self) -> list[str]:
        return list(self.cards)

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for c in self.cards.values():
            out[c.kind] = out.get(c.kind, 0) + 1
        return out
