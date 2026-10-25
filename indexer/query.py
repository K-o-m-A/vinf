"""Rozbor otazky na filtre a typ otazky.

"thrash metal bands from Brazil formed in the 1980s" ->
    Filters(countries={"Brazil"}, formed=(1980, 1989), genre_words={"thrash"}), zvysny text ""
"""
import re
from dataclasses import dataclass, field

from .index import fold


# pridavne mena a skratky -> krajina, ako ju pise Metal Archives
COUNTRY_ALIASES = {
    "american": "United States", "usa": "United States", "u.s.a.": "United States", "america": "United States",
    "united states of america": "United States", "german": "Germany", "brazilian": "Brazil",
    "italian": "Italy", "british": "United Kingdom", "uk": "United Kingdom", "britain": "United Kingdom",
    "great britain": "United Kingdom", "english": "United Kingdom", "england": "United Kingdom",
    "scottish": "United Kingdom", "scotland": "United Kingdom", "welsh": "United Kingdom",
    "wales": "United Kingdom", "french": "France", "canadian": "Canada", "swedish": "Sweden",
    "finnish": "Finland", "spanish": "Spain", "russian": "Russia", "polish": "Poland",
    "mexican": "Mexico", "australian": "Australia", "argentinian": "Argentina", "argentine": "Argentina",
    "chilean": "Chile", "dutch": "Netherlands", "holland": "Netherlands", "japanese": "Japan",
    "indonesian": "Indonesia", "greek": "Greece", "colombian": "Colombia", "norwegian": "Norway",
    "czech": "Czechia", "czech republic": "Czechia", "portuguese": "Portugal", "belgian": "Belgium",
    "austrian": "Austria", "hungarian": "Hungary", "ukrainian": "Ukraine", "swiss": "Switzerland",
    "danish": "Denmark", "malaysian": "Malaysia", "ecuadorian": "Ecuador", "turkish": "Türkiye",
    "turkey": "Türkiye", "peruvian": "Peru", "slovak": "Slovakia", "slovakian": "Slovakia",
    "croatian": "Croatia", "romanian": "Romania", "irish": "Ireland", "serbian": "Serbia",
    "venezuelan": "Venezuela", "belarusian": "Belarus", "bulgarian": "Bulgaria", "filipino": "Philippines",
    "chinese": "China", "costa rican": "Costa Rica", "indian": "India", "bolivian": "Bolivia",
    "israeli": "Israel", "singaporean": "Singapore", "slovenian": "Slovenia",
    "south african": "South Africa", "korean": "Korea, South", "south korean": "Korea, South",
    "south korea": "Korea, South", "korea": "Korea, South", "estonian": "Estonia", "thai": "Thailand",
    "uruguayan": "Uruguay", "lithuanian": "Lithuania", "paraguayan": "Paraguay", "icelandic": "Iceland",
    "puerto rican": "Puerto Rico", "salvadoran": "El Salvador", "latvian": "Latvia",
    "bosnian": "Bosnia and Herzegovina", "bosnia": "Bosnia and Herzegovina", "guatemalan": "Guatemala",
    "iranian": "Iran", "cuban": "Cuba", "macedonian": "North Macedonia", "macedonia": "North Macedonia",
    "maltese": "Malta", "taiwanese": "Taiwan", "vietnamese": "Vietnam", "lebanese": "Lebanon",
    "egyptian": "Egypt", "moroccan": "Morocco", "pakistani": "Pakistan", "armenian": "Armenia",
    "nepalese": "Nepal", "tunisian": "Tunisia", "faroese": "Faroe Islands", "mongolian": "Mongolia",
    "new zealander": "New Zealand", "kazakh": "Kazakhstan", "luxembourgish": "Luxembourg",
    "cypriot": "Cyprus", "honduran": "Honduras", "nicaraguan": "Nicaragua", "panamanian": "Panama",
    "dominican": "Dominican Republic", "sri lankan": "Sri Lanka", "syrian": "Syria",
    "jordanian": "Jordan", "algerian": "Algeria", "saudi": "Saudi Arabia", "iraqi": "Iraq",
}


def country_lookup(countries):
    """{fraza bez diakritiky: krajina}, dlhsie frazy prve ("south korean" pred "korean")."""
    table = {fold(c): c for c in countries if c}
    table.update({fold(alias): c for alias, c in COUNTRY_ALIASES.items()})
    table["korea south"] = "Korea, South"
    return dict(sorted(table.items(), key=lambda kv: -len(kv[0])))


FORMED_VERB = r"(?:formed|founded|started|created|established|from|in)"
DECADE = re.compile(r"\b(?:in\s+the\s+)?(?:(?P<part>early|mid|late)[\s-]+)?(?:(?P<century>19|20)|')?"
                    r"(?P<decade>\d)0'?s\b")
BETWEEN = re.compile(r"\b(?:formed\s+)?between\s+(?P<a>\d{4})\s+and\s+(?P<b>\d{4})\b")
BEFORE = re.compile(r"\b(?:formed\s+)?(?:before|until|prior\s+to)\s+(?P<y>\d{4})\b")
AFTER = re.compile(r"\b(?:formed\s+)?(?P<op>after|since)\s+(?P<y>\d{4})\b")
EXACT_YEAR = re.compile(rf"\b{FORMED_VERB}\s+(?:the\s+year\s+)?(?P<y>(?:19|20)\d\d)\b")

STATUS_PATTERNS = [
    (re.compile(r"\b(?:still\s+|currently\s+)?active\b"), "Active"),
    (re.compile(r"\b(?:split[\s-]*up|disbanded|broke\s+up|broken\s+up|defunct|inactive|no\s+longer\s+active)\b"),
     "Split-up"),
    (re.compile(r"\bon\s+hold\b"), "On hold"),
    (re.compile(r"\bchanged\s+(?:their\s+)?name\b"), "Changed name"),
]

GENRE_WORDS = frozenset("""
death black thrash heavy melodic doom progressive rock power groove grindcore metalcore brutal sludge
stoner hard symphonic gothic atmospheric raw speed hardcore deathcore post crossover technical punk
ambient folk blackened depressive goregrind industrial experimental crust slam pagan funeral avant
garde epic noise psychedelic drone southern shred nwobhm dark alternative synth dungeon viking
neoclassical electronic nu shoegaze extreme grunge djent powerviolence jazz darkwave fusion
acoustic mathcore neofolk celtic glam noisecore medieval noisegrind classical cybergrind deathrock
operatic crustcore orchestral martial metal
""".split())
# zaner aj samostatne ("grindcore bands"), ostatne slova musia koncit na metal/rock/punk
GENRE_STANDALONE = frozenset("""
grindcore metalcore deathcore hardcore crust goregrind djent sludge stoner thrash doom nwobhm
crossover powerviolence mathcore slam noisecore cybergrind deathrock shoegaze grunge darkwave
neofolk crustcore noisegrind
""".split())
GENRE_END = frozenset({"metal", "rock", "punk"})
NOT_GENRE_BEFORE = frozenset({"about", "of", "on", "against"})  # "songs about death", "fear of death"
WORD = re.compile(r"[\w'!]+")


@dataclass
class Filters:
    countries: set = field(default_factory=set)
    formed: tuple = None  # (od, do), None = bez hranice
    status: str = None
    genre_words: set = field(default_factory=set)

    def __bool__(self):
        return bool(self.countries or self.formed or self.status or self.genre_words)

    def describe(self):
        parts = []
        if self.countries:
            parts.append("country = " + " or ".join(sorted(self.countries)))
        if self.formed:
            a, b = self.formed
            parts.append(f"formed {a}" if a == b else f"formed {a or '...'}-{b or '...'}")
        if self.status:
            parts.append(f"status = {self.status}")
        if self.genre_words:
            parts.append("genre has " + " + ".join(sorted(self.genre_words)))
        return ", ".join(parts)

    def match(self, doc):
        if self.countries and doc["country"] not in self.countries:
            return False
        if self.status and doc.get("status") != self.status:
            return False
        if self.formed:
            year = doc["formed"]
            a, b = self.formed
            if year is None or (a and year < a) or (b and year > b):
                return False
        if self.genre_words:
            words = set(re.findall(r"[a-z0-9]+", fold(" ".join(doc["genres"]))))
            if not self.genre_words <= words:
                return False
        return True


def _cut(text, m):
    return text[:m.start()] + " " + text[m.end():]


def parse_filters(line, countries):
    """Vrati (Filters, zvysny text)."""
    text = " " + fold(line).replace("/", " ").replace("-", " ") + " "
    f = Filters()

    for phrase, country in countries.items():
        m = re.search(rf"(?<![\w']){re.escape(phrase)}(?![\w'])", text)
        if m:
            f.countries.add(country)
            text = _cut(text, m)

    if m := BETWEEN.search(text):
        f.formed, text = (int(m["a"]), int(m["b"])), _cut(text, m)
    elif m := BEFORE.search(text):
        f.formed, text = (None, int(m["y"]) - 1), _cut(text, m)
    elif m := AFTER.search(text):
        y = int(m["y"])
        f.formed, text = (y if m["op"] == "since" else y + 1, None), _cut(text, m)
    elif m := DECADE.search(text):
        decade = int(m["decade"])
        century = int(m["century"]) * 100 if m["century"] else (1900 if decade >= 3 else 2000)
        start = century + decade * 10
        lo, hi = {"early": (0, 3), "mid": (3, 6), "late": (6, 9)}.get(m["part"], (0, 9))
        f.formed, text = (start + lo, start + hi), _cut(text, m)
    elif m := EXACT_YEAR.search(text):
        f.formed, text = (int(m["y"]), int(m["y"])), _cut(text, m)

    for pattern, status in STATUS_PATTERNS:
        if m := pattern.search(text):
            f.status, text = status, _cut(text, m)
            break

    words = WORD.findall(text)
    keep, i = [], 0
    while i < len(words):
        j = i
        while j < len(words) and words[j] in GENRE_WORDS:
            j += 1
        run = words[i:j]
        before = words[i - 1] if i else ""
        is_genre = run and before not in NOT_GENRE_BEFORE and (
            run[-1] in GENRE_END or any(w in GENRE_STANDALONE for w in run))
        if is_genre:
            f.genre_words |= {w for w in run if w != "metal"}
            i = j
        else:
            keep.append(words[i])
            i += 1
    return f, " ".join(keep)


def _strip(name):
    return name.strip(" \"'“”?!.").strip()


INTENTS = [
    ("members", re.compile(r"\b(?:members?|line[\s-]?up|musicians)\s+(?:of|in|from)\s+(?:the\s+band\s+)?(?P<band>.+)", re.I)),
    ("members", re.compile(r"^who\s+(?:plays?|played|is|are|was|were|sings?|sang)\s+in\s+(?:the\s+band\s+)?(?P<band>.+)", re.I)),
    ("person", re.compile(r"^(?:in\s+)?(?:which|what)\s+bands?\s+(?:did|does|has|have|is|was)\s+(?P<person>.+?)\s+"
                          r"(?:play(?:ed)?|been|sing|sang|perform(?:ed)?|be|in)\b", re.I)),
    ("person", re.compile(r"^where\s+(?:did|does|has)\s+(?P<person>.+?)\s+play", re.I)),
    ("person", re.compile(r"^(?:bands\s+(?:of|with)|bands\s+featuring)\s+(?P<person>.+)", re.I)),
    ("best", re.compile(r"\b(?:best|top|highest)(?:[\s-]+rated)?\s+(?:albums?|releases?|records?)\s+(?:of|by|from)\s+"
                        r"(?P<band>.+)", re.I)),
    # "best rated Opeth full-length album": meno kapely pred slovom album
    ("best", re.compile(r"\b(?:best|top|highest)(?:[\s-]+rated)?\s+(?P<band>.+?)\s+(?:full[\s-]?length\s+)?"
                        r"(?:albums?|releases?|records?)\b", re.I)),
    ("discography", re.compile(r"\b(?:discography|albums|releases|records)\s+(?:of|by|from)\s+(?P<band>.+)", re.I)),
    ("fact", re.compile(r"^where\s+(?:is|are|was|were)\s+(?P<band>.+?)\s+from\b", re.I)),
    ("fact", re.compile(r"^when\s+(?:was|were|did)\s+(?P<band>.+?)\s+(?:formed|founded|start(?:ed)?|form)\b", re.I)),
    ("who", re.compile(r"^(?:who|what)\s+(?:is|are|was|were)\s+(?P<name>.+)", re.I)),
]


MEMBER_GROUP = re.compile(r"\b(?P<group>current|present|past|former|ex|live)[\s-]+(?:members?|line[\s-]?up|musicians)\b",
                          re.I)
GROUP_NAMES = {"current": "current", "present": "current", "past": "past", "former": "past", "ex": "past",
               "live": "live"}


def member_group(line):
    """"current members of Metallica" -> "current"; bez privlastku None (vsetky skupiny)."""
    m = MEMBER_GROUP.search(line)
    return GROUP_NAMES[m.group("group").lower()] if m else None


def detect_intent(line):
    """("members", "Metallica") pre otazky o kapele alebo osobe, inak (None, None)."""
    for kind, pattern in INTENTS:
        m = pattern.search(line.strip())
        if m:
            name = _strip(next(v for v in m.groupdict().values() if v))
            # "best rated black metal albums" je zaner, nie kapela
            if kind == "best" and set(WORD.findall(fold(name))) <= GENRE_WORDS:
                continue
            if name:
                return kind, name
    return None, None
