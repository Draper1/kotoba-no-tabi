"""Tests for the parts that would quietly corrupt learning if they broke.

Run: python3 tests.py
"""
import os, sys, tempfile, time, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kotoba.content import Course
from kotoba.kana import check, katakana_to_hiragana, kana_to_romaji, normalize, romaji_to_kana
from kotoba.srs import DAY, GOT_IT, NOT_YET, CardState, schedule
from kotoba.store import Store

COURSE = Course()


class TestConversion(unittest.TestCase):
    def test_romaji_to_kana(self):
        for r, k in [("kanji","かんじ"), ("kitte","きって"), ("gakkou","がっこう"),
                     ("shinbun","しんぶん"), ("jitensha","じてんしゃ"), ("kyou","きょう"),
                     ("nihon","にほん"), ("tabemasu","たべます")]:
            self.assertEqual(romaji_to_kana(r), k, r)

    def test_kana_to_romaji(self):
        for k, r in [("たべます","tabemasu"), ("がっこう","gakkou"), ("コーヒー","koohii"),
                     ("じてんしゃ","jitensha"), ("を","wo")]:
            self.assertEqual(kana_to_romaji(k), r, k)

    def test_katakana_folds_to_hiragana(self):
        self.assertEqual(katakana_to_hiragana("コーヒー"), "こーひー")


class TestFairness(unittest.TestCase):
    """A learner who knows the answer must never be told 'not yet'."""

    def test_equivalent_spellings_all_accepted(self):
        for group in [["コーヒー","koohii","kouhii","kōhī","こーひー","ko-hi-"],
                      ["がっこう","gakkou","gakkoo","がっこお"],
                      ["せんせい","sensei","sensee"],
                      ["きょう","kyou","kyoo"]]:
            target = [group[0]]
            for form in group:
                self.assertTrue(check(form, target, vocabulary=COURSE.vocabulary).ok,
                                f"{form} should be accepted for {group[0]}")

    def test_typos_are_forgiven(self):
        self.assertTrue(check("tabemsu", ["たべます"]).ok)
        self.assertTrue(check("sensee", ["せんせい"]).ok)

    def test_real_words_are_never_treated_as_typos(self):
        """来ます vs 行きます differ by one character but are different verbs."""
        v = COURSE.vocabulary
        self.assertFalse(check("kimasu", ["いきます"], vocabulary=v).ok)
        self.assertFalse(check("ikimasu", ["きます"], vocabulary=v).ok)

    def test_minimal_pairs_stay_distinct(self):
        for a, b in [("は","が"), ("お","を"), ("おばさん","おばあさん"), ("ここ","こうこう")]:
            self.assertNotEqual(normalize(a), normalize(b), f"{a} vs {b}")

    def test_empty_answer_is_not_correct(self):
        self.assertFalse(check("", ["は"]).ok)

    def test_ime_kanji_input_accepted_for_masu_forms(self):
        v = COURSE.vocabulary
        for typed, cid in [("食べます","v:たべる:食べる:masu"), ("飲みます","v:のむ:飲む:masu"),
                           ("来ます","v:くる:来る:masu"), ("行きます","v:いく:行く:masu")]:
            card = COURSE.cards[cid]
            self.assertTrue(check(typed, card.answers, vocabulary=v).ok, typed)


class TestScheduling(unittest.TestCase):
    def test_intervals_grow_when_correct(self):
        now, c = time.time(), CardState("t")
        last = 0
        for _ in range(6):
            c = schedule(c, GOT_IT, now)
            self.assertGreaterEqual(c.interval, last)
            last = c.interval
        self.assertGreater(c.interval, 5 * DAY)

    def test_missed_card_returns_within_the_session(self):
        now, c = time.time(), CardState("t")
        for _ in range(6):
            c = schedule(c, GOT_IT, now)
        c = schedule(c, NOT_YET, now)
        self.assertLessEqual(c.interval, 10 * 60)

    def test_one_slip_does_not_wipe_displayed_progress(self):
        now, c = time.time(), CardState("t")
        for _ in range(7):
            c = schedule(c, GOT_IT, now)
        before = c.strength
        after = schedule(c, NOT_YET, now).strength
        self.assertGreater(after, before - 0.15, "a single slip should not crater the bar")

    def test_repeated_lapses_do_erode_honestly(self):
        now, c = time.time(), CardState("t")
        for _ in range(7):
            c = schedule(c, GOT_IT, now)
        for _ in range(5):
            c = schedule(c, NOT_YET, now)
        self.assertLess(c.strength, 0.7, "a repeatedly-missed card should not read as strong")

    def test_ease_stays_in_bounds(self):
        now, c = time.time(), CardState("t")
        for _ in range(30):
            c = schedule(c, NOT_YET, now)
        self.assertGreaterEqual(c.ease, 1.3)


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def store(self, name):
        return Store(os.path.join(self.dir, name))

    def test_replay_is_deterministic(self):
        s = self.store("a.db")
        now = time.time()
        for i in range(6):
            s.record("c1", GOT_IT, now=now + i)
        before = s.state("c1")
        s.rebuild()
        self.assertEqual(s.state("c1").reps, before.reps)
        self.assertAlmostEqual(s.state("c1").interval, before.interval, places=3)

    def test_merge_is_a_union_and_idempotent(self):
        a, b = self.store("a.db"), self.store("b.db")
        now = time.time()
        for i in range(4):
            a.record("x", GOT_IT, now=now + i)
        for i in range(3):
            b.record("y", GOT_IT, now=now + i)
        self.assertEqual(a.import_(b.export())["added"], 3)
        self.assertEqual(a.import_(b.export())["added"], 0)
        self.assertEqual(a.total_reviews(), 7)
        self.assertEqual(a.state("y").reps, 3)

    def test_export_round_trips_through_a_fresh_device(self):
        a = self.store("a.db")
        now = time.time()
        for i in range(5):
            a.record("z", GOT_IT, now=now + i)
        c = self.store("c.db")
        c.import_(a.export())
        self.assertEqual(c.state("z").reps, a.state("z").reps)


class TestContent(unittest.TestCase):
    def test_card_ids_are_unique(self):
        self.assertEqual(len(COURSE.cards), len(set(COURSE.cards)))

    def test_every_card_has_an_answer_and_a_reveal(self):
        for c in COURSE.cards.values():
            self.assertTrue(c.answers and all(c.answers), c.id)
            self.assertTrue(c.reveal, c.id)
            self.assertTrue(c.prompt, c.id)

    def test_every_answer_normalises_to_something(self):
        for c in COURSE.cards.values():
            if not c.english:
                self.assertTrue(normalize(c.answers[0]), f"{c.id} -> {c.answers}")

    def test_grammar_drills_have_a_blank(self):
        for c in COURSE.by_kind("grammar"):
            self.assertIn("＿", c.prompt, c.id)

    def test_every_card_answers_itself(self):
        """The stored answer must actually pass the checker for its own card."""
        for c in COURSE.cards.values():
            m = check(c.answers[0], c.answers, english=c.english,
                      vocabulary=COURSE.vocabulary)
            self.assertTrue(m.ok, f"{c.id}: {c.answers[0]!r} rejected by its own card")


if __name__ == "__main__":
    unittest.main(verbosity=2)
