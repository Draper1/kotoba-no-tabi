"""Romaji <-> kana conversion and lenient answer matching.

This module exists to be *fair*. A learner who knows the answer should never be
told "not yet" because of a typo, a macron, or a defensible long-vowel spelling.
Everything is normalised to hiragana before comparison, so these are all equal:

    コーヒー   ko-hi-   koohii   kōhī   こーひー

You can answer in romaji (no IME needed) or in real kana (with the IME on).
Both are normalised the same way, so the game never cares which you used.
"""

from __future__ import annotations

# --- romaji -> kana -------------------------------------------------------
# Longest-first matching, so "kya" wins over "ki"+"ya" and "shi" over "si".

_R2K: dict[str, str] = {}


def _add(table: str) -> None:
    """Parse compact 'romaji=kana' pairs, whitespace separated."""
    for pair in table.split():
        r, k = pair.split("=")
        _R2K[r] = k


# Base gojuon
_add("""
a=あ i=い u=う e=え o=お
ka=か ki=き ku=く ke=け ko=こ
sa=さ shi=し su=す se=せ so=そ
ta=た chi=ち tsu=つ te=て to=と
na=な ni=に nu=ぬ ne=ね no=の
ha=は hi=ひ fu=ふ he=へ ho=ほ
ma=ま mi=み mu=む me=め mo=も
ya=や yu=ゆ yo=よ
ra=ら ri=り ru=る re=れ ro=ろ
wa=わ wi=ゐ we=ゑ wo=を n=ん
""")

# Dakuten / handakuten
_add("""
ga=が gi=ぎ gu=ぐ ge=げ go=ご
za=ざ ji=じ zu=ず ze=ぜ zo=ぞ
da=だ de=で do=ど
ba=ば bi=び bu=ぶ be=べ bo=ぼ
pa=ぱ pi=ぴ pu=ぷ pe=ぺ po=ぽ
""")

# Youon (small ya/yu/yo combos)
_add("""
kya=きゃ kyu=きゅ kyo=きょ  gya=ぎゃ gyu=ぎゅ gyo=ぎょ
sha=しゃ shu=しゅ sho=しょ  ja=じゃ  ju=じゅ  jo=じょ
cha=ちゃ chu=ちゅ cho=ちょ  nya=にゃ nyu=にゅ nyo=にょ
hya=ひゃ hyu=ひゅ hyo=ひょ  bya=びゃ byu=びゅ byo=びょ
pya=ぴゃ pyu=ぴゅ pyo=ぴょ  mya=みゃ myu=みゅ myo=みょ
rya=りゃ ryu=りゅ ryo=りょ
""")

# Alternate romanisations (kunrei-shiki, nihon-shiki, common typing habits).
# Accepting these is the whole point: the learner is being tested on Japanese,
# not on which romanisation system they happened to learn.
_add("""
si=し ti=ち tu=つ hu=ふ zi=じ  di=ぢ du=づ dzu=づ
sya=しゃ syu=しゅ syo=しょ  tya=ちゃ tyu=ちゅ tyo=ちょ
jya=じゃ jyu=じゅ jyo=じょ  zya=じゃ zyu=じゅ zyo=じょ
dya=ぢゃ dyu=ぢゅ dyo=ぢょ
cya=ちゃ cyu=ちゅ cyo=ちょ
fa=ふぁ fi=ふぃ fe=ふぇ fo=ふぉ
va=ゔぁ vi=ゔぃ vu=ゔ ve=ゔぇ vo=ゔぉ
she=しぇ che=ちぇ je=じぇ
ye=いぇ  wu=う
ti=ち  xtsu=っ ltsu=っ
xa=ぁ xi=ぃ xu=ぅ xe=ぇ xo=ぉ
la=ぁ li=ぃ lu=ぅ le=ぇ lo=ぉ
xya=ゃ xyu=ゅ xyo=ょ  xtu=っ ltu=っ
-=ー
""")

_MACRONS = {
    "ā": "aa", "ī": "ii", "ū": "uu", "ē": "ee", "ō": "ou",
    "â": "aa", "î": "ii", "û": "uu", "ê": "ee", "ô": "ou",
    "ǎ": "aa", "ǐ": "ii", "ǔ": "uu", "ě": "ee", "ǒ": "oo",
}

_DOUBLE_CONSONANTS = set("kgsztdnhbpmyrwfjcv")


def romaji_to_kana(text: str) -> str:
    """Convert a romaji string to hiragana. Unknown characters pass through."""
    s = text.lower().strip()
    for macron, plain in _MACRONS.items():
        s = s.replace(macron, plain)
    s = s.replace("'", "").replace("’", "")

    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        for length in (3, 2, 1):
            chunk = s[i:i + length]
            if chunk in _R2K:
                out.append(_R2K[chunk])
                i += length
                break
        else:
            c = s[i]
            # Sokuon: a doubled consonant becomes っ ("kitte" -> きって)
            if c in _DOUBLE_CONSONANTS and s[i + 1:i + 2] == c:
                out.append("っ")
                i += 1
            else:
                out.append(c)
                i += 1
    return "".join(out)


# --- kana -> romaji -------------------------------------------------------
# Built by inverting the primary table (first spelling wins, so we get the
# Hepburn form learners actually see on JLPT material: shi, chi, tsu, fu).

_K2R: dict[str, str] = {}
for _r, _k in _R2K.items():
    if _k not in _K2R or len(_r) < len(_K2R[_k]):
        _K2R[_k] = _r
# Force Hepburn for the handful where a shorter kunrei spelling would win.
_K2R.update({
    "し": "shi", "ち": "chi", "つ": "tsu", "ふ": "fu", "じ": "ji",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "づ": "zu", "ぢ": "ji", "を": "wo",
})


def kana_to_romaji(text: str) -> str:
    """Convert kana to Hepburn romaji, for hints and 'the answer was...' lines."""
    s = katakana_to_hiragana(text)
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        # Long-vowel mark repeats the previous vowel
        if s[i] == "ー" and out:
            out.append(out[-1][-1])
            i += 1
            continue
        # Sokuon doubles the next consonant
        if s[i] == "っ" and i + 1 < n:
            nxt = _lookup_kana(s, i + 1)
            if nxt:
                out.append(nxt[1][0])
            i += 1
            continue
        hit = _lookup_kana(s, i)
        if hit:
            length, rom = hit
            out.append(rom)
            i += length
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _lookup_kana(s: str, i: int) -> tuple[int, str] | None:
    for length in (2, 1):
        chunk = s[i:i + length]
        if chunk in _K2R:
            return length, _K2R[chunk]
    return None


# --- normalisation --------------------------------------------------------

_KANA_VOWEL = {"a": "\u3042", "i": "\u3044", "u": "\u3046", "e": "\u3048", "o": "\u304a"}
# Which kana vowel does each kana end on?  Used to expand the long-vowel mark:
# \u30b3\u30fc\u30d2\u30fc -> \u3053\u304a\u3072\u3044.  Must yield KANA, not the romaji letter.
_VOWEL_OF: dict[str, str] = {}
for _k, _r in _K2R.items():
    if _r and _r[-1] in "aiueo":
        _VOWEL_OF[_k] = _KANA_VOWEL[_r[-1]]

_STRIP = str.maketrans("", "", " \t　.,!?'\"-–—·/()[]。、！？「」〜～")


def katakana_to_hiragana(text: str) -> str:
    """ア -> あ. Leaves ー, punctuation and non-kana alone."""
    return "".join(
        chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch
        for ch in text
    )


def normalize(text: str) -> str:
    """Fold an answer to a canonical hiragana form for comparison.

    Handles the four things that otherwise cause unfair misses:
      * script            (katakana -> hiragana)
      * romaji vs kana    (romaji is converted)
      * long vowels       (ー expanded, おう/えい folded to おお/ええ)
      * punctuation/space (stripped)
    """
    s = text.strip().lower()
    if not s:
        return ""
    # If it contains no kana/kanji at all, treat it as romaji input.
    if not any(ch > "　" for ch in s):
        s = romaji_to_kana(s)
    s = katakana_to_hiragana(s)

    # Expand the long-vowel mark into the vowel it lengthens
    expanded: list[str] = []
    for ch in s:
        if ch == "ー" and expanded:
            expanded.append(_VOWEL_OF.get(expanded[-1], ""))
        else:
            expanded.append(ch)
    s = "".join(expanded)

    # Fold long-vowel spellings so every way of writing a long vowel agrees:
    #   がっこう == がっこお == ガッコー,  せんせい == せんせえ,  きょう == きょお
    # Rule: う after an o-vowel kana lengthens that o; い after an e-vowel
    # lengthens that e.  This is how they are actually pronounced, and it means
    # the learner is never penalised for choosing one transcription over another.
    folded: list[str] = []
    for ch in s:
        if folded:
            v = _VOWEL_OF.get(folded[-1])
            if ch == "う" and v == "お":
                folded.append("お")
                continue
            if ch == "い" and v == "え":
                folded.append("え")
                continue
        folded.append(ch)
    s = "".join(folded)
    s = s.replace("ゔ", "ぶ")
    return s.translate(_STRIP)


def normalize_en(text: str) -> str:
    """Canonical form for English meanings: lowercase, no articles, no fluff."""
    s = text.strip().lower()
    for junk in ("(", ")", "[", "]", ".", ",", "!", "?", ";", ":", '"', "'"):
        s = s.replace(junk, " ")
    words = [w for w in s.split() if w not in ("a", "an", "the", "to", "some")]
    return " ".join(words)


# --- fuzzy matching -------------------------------------------------------

def edit_distance(a: str, b: str, cap: int = 3) -> int:
    """Levenshtein distance, short-circuiting once it exceeds `cap`."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


# Result of checking an answer. `ok` means it counts; `typo` means it counted
# but we should say something kind about the spelling.
class Match:
    __slots__ = ("ok", "typo", "matched")

    def __init__(self, ok: bool, typo: bool = False, matched: str = ""):
        self.ok = ok
        self.typo = typo
        self.matched = matched

    def __bool__(self) -> bool:
        return self.ok


def check(
    given: str,
    accepted: list[str],
    english: bool = False,
    vocabulary: frozenset[str] | None = None,
) -> Match:
    """Is `given` an acceptable answer? Typos within tolerance still count.

    Tolerance scales with length so short answers (where one character carries
    the whole meaning, e.g. は vs が) stay strict, while long ones forgive a slip.

    `vocabulary` is every normalised answer the course knows.  If the learner's
    input is *itself* a real word, it is never treated as a typo of a different
    one -- "kimasu" is 来ます, not a slip for 行きます.  Without this guard the game
    would praise a genuine mix-up and quietly reinforce it.
    """
    if not given.strip():
        return Match(False)

    norm = normalize_en if english else normalize
    g = norm(given)
    if not g:
        return Match(False)

    cands = [(norm(a), a) for a in accepted]
    for c, original in cands:
        if c and g == c:
            return Match(True, matched=original)

    # The learner typed a different word that genuinely exists: that is a mix-up
    # worth teaching, not a keyboard slip. Skip straight to the gentle reveal.
    if vocabulary and g in vocabulary:
        return Match(False)

    # Typo tolerance, on the longer answers only.
    for c, original in cands:
        if not c:
            continue
        allowed = 0 if len(c) < 4 else (1 if len(c) < 9 else 2)
        if allowed and edit_distance(g, c, allowed) <= allowed:
            return Match(True, typo=True, matched=original)

    # An English answer that contains the expected phrase counts
    # ("to eat food" for "to eat").
    if english:
        for c, original in cands:
            if c and (c in g or g in c) and len(g) >= 3:
                return Match(True, matched=original)

    return Match(False)
