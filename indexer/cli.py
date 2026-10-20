"""Interaktivne vyhladavanie: python -m indexer

Dopyt vypise zoradeny zoznam kapiel, cislo vysledku otvori detail kapely,
prikazy zacinaju dvojbodkou (:help). Vystup je v anglictine.
"""
import difflib
import json
import math
import pickle
import re
import sys
import time

from .index import IDF_METHODS, POPULARITY, Index, fold, profile_text, profile_tokenize, tokenize
from .query import country_lookup, detect_intent, parse_filters

try:
    import readline  # noqa: F401  historia a sipky v input()
except ImportError:
    pass

COLOR = sys.stdout.isatty()


def c(text, code):
    return f"\033[{code}m{text}\033[0m" if COLOR else str(text)


def bold(t): return c(t, "1")
def dim(t): return c(t, "2")
def green(t): return c(t, "32")
def yellow(t): return c(t, "33")
def cyan(t): return c(t, "36")


def prompt_safe(text):
    # readline inak zle pocita dlzku promptu s ANSI kodmi
    return re.sub(r"(\033\[[\d;]*m)", "\001\\1\002", text)


HELP = f"""
{bold('Search')}
  <query>              search bands, e.g.  black metal satanism norway
                       or ask a question:  Which thrash metal bands are from Brazil?
  <number>             full detail of a band from the last results, e.g.  3
  Enter  (or :more)    next page of results
  :why <number>        why the band is in the results: where the query words occur,
                       and their TF, DF, IDF and contribution to the score

{bold('Filters')}  (recognized in any query, applied to the band's extracted fields)
  country      from Brazil, swedish, norwegian, USA, ...
  formed       formed in 1991, in the 1980s, late 90s, before 1995, since 2010
  status       active, split-up / disbanded, on hold, changed name
  genre        thrash metal, melodic death metal, grindcore, ...
  e.g.  thrash metal bands from Brazil formed in the 1980s
  With no other words the bands are sorted by popularity (number of reviews).

{bold('Direct answers')}
  Who are the members of <band>?          lineup of the band
  Which bands did <person> play in?       bands of a musician, with roles and years
  What is the best rated album of <band>? albums sorted by rating
  discography of <band> / albums by <band>
  Where is <band> from? / When was <band> formed?

{bold('Band by release title')}
  which band has an album named <title>    e.g.  Which band has an album named Besnota
  who released <title>                     e.g.  Who released Master of Puppets?

{bold('Similar bands')}
  similar bands to <name>      e.g.  Similar bands to Kanonenfieber
  bands like <name>            e.g.  bands like 1914
  :similar <number>            bands similar to a result from the last list

{bold('Settings')}
  :idf classic|smooth|squared   IDF method (now: {{method}})
  :k <n>               results per page (now: {{k}})
  :compare [query]     top results of all IDF methods side by side

{bold('Other')}
  :help                this help
  :quit  (or Ctrl+D)

{bold('How results are found')}
  Every band is one document made of its name, country, location, genres, lyrical
  themes, label, status, member names, release titles and description. A band is a
  result if any query word occurs anywhere in that document. A band whose name equals
  the query is shown first; the rest is ranked by TF-IDF cosine similarity, so short
  documents where the query words make up a big part of the text rank high.
  Words are compared without diacritics and plural "s" (Sarcofago = Sarcófago,
  vikings = viking). If no band has the typed name, a band with a similar name is
  suggested ("did you mean").
  Similar bands are found differently: only by genre and lyrical themes of the band
  (its "profile"), so a band is similar if it plays the same style and sings about the
  same topics. Release titles, members and descriptions are not used there.
"""

SIMILAR = re.compile(r"(?:\bsimilar\b(?:\s+(?:bands?|artists?|groups?|music))?\s+(?:to|as)|\blike)\s+(?P<name>.+?)[\s?!.]*$",
                     re.I)

RELEASE_KINDS = r"(?:albums?|records?|releases?|eps?|demos?|singles?|songs?|splits?|compilations?)"
RELEASE_QUESTIONS = [
    re.compile(rf"\b{RELEASE_KINDS}\s+(?:named|called|titled)\s+(?P<title>.+)", re.I),
    re.compile(rf"\b{RELEASE_KINDS}\s+[\"“'](?P<title>[^\"”']+)[\"”']", re.I),
    re.compile(r"^(?:who|which bands?|what bands?)\s+(?:released|recorded|made|wrote)\s+(?:the\s+)?"
               rf"(?:{RELEASE_KINDS}\s+)?(?P<title>.+)", re.I),
    re.compile(rf"\bthe\s+{RELEASE_KINDS}\s+(?P<title>.+)", re.I),
]
TITLE_TAIL = re.compile(r"(?:\s+(?:released|come out|out|by whom|from))?[\s\"”'?!.]*$", re.I)

# slova z otazok, ktore nic nehovoria o kapele; v indexe by vytiahli napr. album "Sing for You"
QUERY_FILLER = frozenset("""
which what who whom whose where when how many much find show list give me tell recommend
search looking look want would like some any all bands band artists artist groups group
sing sings singing play plays played playing member members about do does did are there formed
album albums record records release released named called titled
""".split())
GENERIC = frozenset({"metal", "music", "song", "lyric", "from", "formed", "year"})
# "bands that sing about death" nema hladat kapelu menom Death
THEME_QUESTION = re.compile(r"\b(?:about|sing|sings|lyrics?|themes?)\b", re.I)

MEMBER_GROUPS = {"current": "Current lineup", "past": "Past members", "live": "Live musicians"}
MEMBER_GROUP_LABEL = {"current": "current member", "past": "past member", "live": "live musician"}


def clean_query(line):
    return " ".join(t for t in tokenize(line) if t not in QUERY_FILLER)


def normalize_name(name):
    return " ".join(fold(name).strip(" ?!.").split())


def highlight(text, term):
    return re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", lambda m: bold(yellow(m.group())), text, flags=re.I)


def plural(n, word):
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def reviews(n):
    return plural(n, "review")


def release_line(r):
    rating = f", {r['rating']}% from {reviews(r['reviews'])}" if r["reviews"] else ""
    return f"{r['year']}  {r['name']}  ({r['type']}{rating})"


def same_title(a, b):
    return re.findall(r"\w+", a.lower()) == re.findall(r"\w+", b.lower())


def band_fields(band):
    members = [m["name"] for g in band["members"].values() for m in g]
    return [
        ("name", [band["name"]]),
        ("location", [x for x in (band.get("location"), band.get("country")) if x]),
        ("genre", band["genres"]),
        ("themes", band["themes"]),
        ("label", [band["label"]] if band.get("label") else []),
        ("status", [band["status"]] if band.get("status") else []),
        ("member", members),
        ("release title", [r["name"] for r in band["releases"]]),
        ("description", [band["comment"]] if band["comment"] else []),
    ]


def find_matches(band, terms):
    """Kde sa termy dopytu nachadzaju: [(pole, term, pocet vyskytov, texty s vyskytom)]."""
    matches = []
    for field, texts in band_fields(band):
        for term in terms:
            hits = [t for t in texts if term in tokenize(t)]
            count = sum(tokenize(t).count(term) for t in hits)
            if count:
                matches.append((field, term, count, hits))
    return matches


class Shell:
    def __init__(self, index, bands_file, profile_file, members_file):
        self.index = index
        self.bands_file = bands_file
        self.profile_file = profile_file
        self.members_file = members_file
        self.profile = None  # nacitaju sa az pri prvom pouziti
        self.members = None
        self.countries = country_lookup({d["country"] for d in index.docs})
        self.method = "classic"
        self.k = 10
        self.last_line = None
        self.ranked = []
        self.reset()
        self.release_hits = {}    # doc_id -> vydania s hladanym nazvom
        self.exact_release = set()
        self.term_share = {}      # term profilu -> podiel na vahe (podobne kapely)
        self.coverage = {}        # doc_id -> pokrytie profilu
        self.names = {}           # normalizovane meno -> [doc_id]
        for doc_id, doc in enumerate(index.docs):
            self.names.setdefault(normalize_name(doc["name"]), []).append(doc_id)
        self.name_groups = {}     # prve pismeno -> mena, pre "did you mean"
        for name in self.names:
            self.name_groups.setdefault(name[:1], []).append(name)

    def reset(self, query=None):
        """Novy zoznam vysledkov. Typ zoznamu urcuje similar_to / release_title / by_popularity."""
        self.query, self.page, self.terms = query, 0, []
        self.similar_to = None     # doc_id kapely, ak su to podobne kapely
        self.release_title = None  # nazov, ak su to kapely s vydanim tohto nazvu
        self.by_popularity = False  # iba filtre, zoradene podla poctu recenzii
        self.pin_label = {}        # doc_id -> "exact name match" / "did you mean?"

    # --- vyhladavanie ---------------------------------------------------------

    def search(self, line):
        start = time.time()
        filters, rest = parse_filters(line, self.countries)
        query = clean_query(rest)
        if filters:
            query = " ".join(t for t in query.split() if t not in GENERIC)
        if not query and not filters:
            print(yellow("No search words left in the query.") + dim(" Try e.g.: swedish melodic death metal"))
            return
        self.last_line = line
        self.reset(query)
        self.terms = list(dict.fromkeys(query.split()))

        if filters:
            print(dim(f"filters: {filters.describe()}" + (f"   words: {query}" if query else "")))
            allowed = {d for d, doc in enumerate(self.index.docs) if filters.match(doc)}
            ranked = [(s, d) for s, d in self.index.rank(query, self.method) if d in allowed] if query else []
            if query and not ranked and allowed:
                print(yellow(f"No band matching the filters mentions {query!r}.") + " Showing all that match the filters.")
            if not ranked:
                self.by_popularity = True
                ranked = sorted(((self.index.docs[d]["reviews"], d) for d in allowed), reverse=True)
                self.terms = []
            self.ranked = ranked
        else:
            if query != " ".join(tokenize(line)):
                print(dim(f"searching for: {query}"))
            # kapela s presne tymto menom ide na zaciatok, zvysok podla TF-IDF
            pinned = self.names.get(normalize_name(line)) or []
            if not pinned and not THEME_QUESTION.search(line):
                pinned = self.names.get(normalize_name(query)) or []
            self.pin_label = {d: "exact name match" for d in pinned}
            if not pinned and len(query.split()) <= 3 and len(tokenize(line)) == len(query.split()):
                pinned = self.did_you_mean(normalize_name(line))
            ranked = self.index.rank(query, self.method)
            self.ranked = [(None, d) for d in pinned] + [(s, d) for s, d in ranked if d not in pinned]
        took = (time.time() - start) * 1000
        if not self.ranked:
            print(yellow("Nothing found.") + dim(" Try other English words, e.g. a country, genre or member name."))
            return
        order = "sorted by popularity (number of reviews)" if self.by_popularity else f"idf={self.method}"
        print(dim(f"{len(self.ranked):,} results in {took:.0f} ms, {order}"))
        self.show_page()

    def did_you_mean(self, name):
        """Preklep v mene: rovnake prve pismeno, dlzka +-2, difflib >= 0.8."""
        if len(name) < 4:
            return []
        candidates = [n for n in self.name_groups.get(name[:1], []) if abs(len(n) - len(name)) <= 2]
        close = difflib.get_close_matches(name, candidates, n=3, cutoff=0.8)
        if not close:
            return []
        docs = [max(self.names[n], key=lambda d: self.index.docs[d]["reviews"]) for n in close]
        docs.sort(key=lambda d: -self.index.docs[d]["reviews"])
        names = ", ".join(self.index.docs[d]["name"] for d in docs)
        print(yellow(f"No band called {name!r}.") + f" Did you mean: {cyan(names)}?")
        self.pin_label = {d: "did you mean? (similar name)" for d in docs}
        return docs

    def show_page(self):
        if not self.ranked:
            print(dim("Type a query first."))
            return
        start = self.page * self.k
        page = self.ranked[start:start + self.k]
        if not page:
            print(dim("No more results."))
            return
        for i, (score, doc_id) in enumerate(page, start + 1):
            d = self.index.docs[doc_id]
            where = f"({d['country'] or '?'}, formed {d['formed'] or '?'})"
            if self.release_title is not None:
                mark = (green(f"has a release titled {self.release_title!r}") if doc_id in self.exact_release
                        else dim(f"a release title contains {self.release_title!r}"))
            elif score is None:
                mark = green(self.pin_label.get(doc_id, "exact name match"))
            elif self.by_popularity:
                mark = dim(reviews(d["reviews"]))
            elif self.similar_to is not None:
                mark = dim(f"score {score:.2f} = covers {self.coverage[doc_id]:.0%} of the profile, "
                           f"{reviews(d['reviews'])}")
            else:
                mark = dim(f"score {score:.3f}")
            print(f"{bold(f'{i:3}.')} {cyan(d['name'])} {dim(where)}  {d['genre']}  {mark}")

            if self.similar_to is not None:
                self.show_shared(self.load_band(doc_id))
            elif self.release_title is not None:
                for r in self.release_hits[doc_id]:
                    print(f"       {release_line(r)}")
            else:
                matched = {}
                for field, term, count, _ in find_matches(self.load_band(doc_id), self.terms):
                    matched.setdefault(field, []).append(term + (f" {count}x" if count > 1 else ""))
                if matched:
                    print(dim("       matched in: " + "; ".join(f"{f} ({', '.join(t)})" for f, t in matched.items())))
        rest = len(self.ranked) - start - len(page)
        if rest > 0:
            print(dim(f"   {rest:,} more results. Enter = next page, <number> = detail, :why <number> = explanation, :similar <number> = similar bands"))
        self.page += 1

    # --- podobne kapely -------------------------------------------------------

    def show_shared(self, band):
        """Zanre a temy kandidata spolocne s profilom; termy ako "metal" (pod 1 % vahy) sa neratau."""
        important = {t for t, share in self.term_share.items() if share >= 0.01}
        shared = {}
        for field, phrases in (("genre", band["genres"]), ("themes", band["themes"])):
            for phrase in phrases:
                if important & set(profile_tokenize(phrase)):
                    shared.setdefault(field, []).append(phrase)
        if shared:
            print(dim("       shares: " + "; ".join(f"{f}: {', '.join(v)}" for f, v in shared.items())))

    def find_band(self, name):
        """Pri viacerych kapelach s rovnakym menom vrati tu s najviac recenziami."""
        ids = self.names.get(normalize_name(name), [])
        if not ids:
            return None, 0
        return max(ids, key=lambda d: self.index.docs[d]["reviews"]), len(ids)

    def similar(self, doc_id, same_name=1):
        if self.profile is None:
            if not self.profile_file.exists():
                print(yellow("Profile index is missing.") + " Run: python -m indexer build")
                return
            self.profile = Index.load(self.profile_file)
        band = self.load_band(doc_id)
        text = profile_text(band)
        if not text.strip():
            print(yellow(f"{band['name']} has no genre or lyrical themes, cannot find similar bands."))
            return
        start = time.time()
        self.reset(text)
        self.similar_to = doc_id
        self.terms = list(dict.fromkeys(profile_tokenize(text)))
        self.term_share = {t: share for t, share, _ in self.profile.explain_similar(text, doc_id, self.method)}
        # pod 5 % pokrytia maju spolocne uz len "metal" a pod.
        results = [r for r in self.profile.similar(text, self.method) if r[2] != doc_id and r[1] >= 0.05]
        self.ranked = [(score, d) for score, _, d in results]
        self.coverage = {d: c for _, c, d in results}
        took = (time.time() - start) * 1000
        print(f"Bands similar to {cyan(band['name'])} {dim('(' + (band.get('country') or '?') + ')')}"
              f", compared by genre and lyrical themes:")
        print(f"  {dim('genre ')} {', '.join(band['genres']) or '-'}")
        print(f"  {dim('themes')} {', '.join(band['themes']) or '-'}")
        if same_name > 1:
            print(dim(f"  ({same_name} bands are called {band['name']!r}; using the one with the most reviews. "
                      f"Search the name and use :similar <number> to pick another.)"))
        print(dim(f"{len(self.ranked):,} results in {took:.0f} ms, idf={self.method}"))
        self.show_page()

    def similar_query(self, line):
        m = SIMILAR.search(line)
        if not m:
            return False
        doc_id, count = self.find_band(m.group("name"))
        if doc_id is None:
            print(dim(f"No band called {m.group('name')!r}, searching the text instead."))
            return False
        self.similar(doc_id, count)
        return True

    # --- priame odpovede z extrahovanych poli -------------------------------

    def answer(self, line):
        kind, name = detect_intent(line)
        if kind is None:
            return False
        if kind == "person":
            return self.person(name)
        doc_id, count = self.find_band(name)
        if doc_id is None:
            if kind == "who":
                return self.person(name)
            print(dim(f"No band called {name!r}, searching the text instead."))
            return False
        self.reset()
        self.ranked, self.page = [(None, doc_id)], 1
        b = self.load_band(doc_id)
        place = ", ".join(x for x in (b.get("location"), b.get("country")) if x) or "an unknown place"
        print(f"{bold(cyan(b['name']))} {dim('(' + (b.get('country') or '?') + ', ' + ', '.join(b['genres']) + ')')}")
        if count > 1:
            print(dim(f"  {count} bands are called {b['name']!r}; showing the one with the most reviews."))
        if kind in ("fact", "who"):
            formed = f"formed in {b['formed']}" if b.get("formed") else "year of formation unknown"
            print(f"  is from {place}, {formed}, status: {b.get('status')}"
                  + (f", active {b['years_active']}" if b.get("years_active") not in (None, "", "N/A") else ""))
        elif kind == "members":
            self.print_members(b)
        elif kind == "discography":
            self.print_discography(b)
        elif kind == "best":
            self.print_best(b)
        print(dim("\n  Type 1 for the full detail of the band."))
        return True

    def print_best(self, b):
        rated = [r for r in b["releases"] if r["reviews"]]
        if not rated:
            print(dim("  None of its releases has a review on the site."))
            return

        def by_rating(releases):
            return sorted(releases, key=lambda r: (-r["rating"], -r["reviews"]))

        # hodnotenie z 1-2 recenzii je nespolahlive, preto zvlast
        albums = [r for r in rated if r["type"] == "Full-length"]
        solid = by_rating(r for r in albums if r["reviews"] >= 3)
        best = (solid or by_rating(albums) or by_rating(rated))[0]
        print(f"  Best rated {'album' if best['type'] == 'Full-length' else 'release'}: {green(best['name'])} "
              f"({best['type']}, {best['year']}, {best['rating']}% from {reviews(best['reviews'])})")
        sections = [
            ("Full-length albums with at least 3 reviews", solid),
            ("Full-length albums with 1-2 reviews (rating less reliable)", by_rating(r for r in albums if r["reviews"] < 3)),
            ("Other releases (EPs, live albums, videos, ...)", by_rating(r for r in rated if r["type"] != "Full-length")),
        ]
        for title, releases in sections:
            if releases:
                print(f"\n  {bold(title)}")
                for r in releases:
                    print(f"    {release_line(r)}")

    def person(self, name):
        if self.members is None:
            if not self.members_file.exists():
                print(yellow("Member index is missing.") + " Run: python -m indexer build")
                return False
            with open(self.members_file, "rb") as f:
                self.members = pickle.load(f)
        key = " ".join(fold(name).split())
        entries = list(self.members.get(key, []))
        if len(key.split()) == 1:  # iba priezvisko alebo prezyvka
            keys = [k for k in self.members if k != key and key in k.split()]
            if len(keys) <= 30:
                entries += [e for k in keys for e in self.members[k]]
        if not entries:
            print(dim(f"No musician called {name!r}, searching the text instead."))
            return False

        # rovnake meno moze mat viac ludi, rozlisi ich id umelca
        people = {}
        for artist_id, display, doc_id, group, roles in entries:
            people.setdefault(artist_id, (display, []))[1].append((doc_id, group, roles))
        order = sorted(people.items(), key=lambda kv: -sum(self.index.docs[d]["reviews"] for d, _, _ in kv[1][1]))
        if len(order) > 1:
            print(dim(f"{len(order)} different musicians match {name!r} (told apart by their artist id)."))
        self.reset()
        self.ranked, self.page = [], 1
        for artist_id, (display, bands) in order:
            print(f"\n{bold(cyan(display))} {dim(f'(artist id {artist_id}, {plural(len(bands), "band")})')}")
            bands.sort(key=lambda b: (list(MEMBER_GROUPS).index(b[1]), -self.index.docs[b[0]]["reviews"]))
            for doc_id, group, roles in bands:
                self.ranked.append((None, doc_id))
                d = self.index.docs[doc_id]
                print(f"  {bold(f'{len(self.ranked):3}.')} {cyan(d['name'])} {dim('(' + (d['country'] or '?') + ')')}  "
                      f"{d['genre']}\n       {MEMBER_GROUP_LABEL[group]}: {roles or '?'}")
        print(dim("\n  Type a number for the full detail of the band."))
        return True

    # --- kapela podla nazvu vydania ------------------------------------------

    def release_query(self, line):
        for pattern in RELEASE_QUESTIONS:
            m = pattern.search(line)
            if m:
                title = TITLE_TAIL.sub("", m.group("title")).strip(" \"'“”")
                if title and self.find_releases(title):
                    return True
                if title:
                    print(dim(f"No release titled {title!r}, searching the text instead."))
                return False
        return False

    def find_releases(self, title):
        """Kandidati su kapely so vsetkymi slovami nazvu (prienik postingov), potom sa
        overia nazvy ich vydani. Bez toho by na "Which band has an album named Besnota"
        vyhrala kapela, ktorej popis obsahuje slova "album" a "named"."""
        start = time.time()
        words = tokenize(title)
        if not words:
            return False
        n = len(words)
        hits = {}
        for doc_id in self.index.docs_with_all(words):
            releases = []
            for r in self.load_band(doc_id)["releases"]:
                name = tokenize(r["name"])
                if any(name[i:i + n] == words for i in range(len(name) - n + 1)):
                    releases.append(r)
            if releases:
                hits[doc_id] = releases
        if not hits:
            return False

        self.reset(title)
        self.release_title, self.release_hits, self.terms = title, hits, words
        self.exact_release = {d for d, rs in hits.items() if any(same_title(r["name"], title) for r in rs)}
        self.ranked = [(None, d) for d in sorted(hits, key=lambda d: (
            d not in self.exact_release, -sum(r["reviews"] for r in hits[d]), -self.index.docs[d]["reviews"]))]
        took = (time.time() - start) * 1000
        count = sum(len(v) for v in hits.values())
        stats = f"({plural(count, 'release')} by {plural(len(hits), 'band')}, {took:.0f} ms)"
        print(f"Bands with a release titled {cyan(repr(title))} {dim(stats)}:")
        self.show_page()
        return True

    # --- detail kapely --------------------------------------------------------

    def pick(self, number):
        if not 1 <= number <= len(self.ranked):
            print(yellow(f"Result {number} does not exist."))
            return None
        return self.ranked[number - 1][1]

    def load_band(self, doc_id):
        with open(self.bands_file, "rb") as f:
            f.seek(self.index.docs[doc_id]["offset"])
            return json.loads(f.readline())

    def show_band(self, doc_id):
        b = self.load_band(doc_id)
        print()
        print(bold(cyan(b["name"])) + "  " + dim(b["url"]))
        rows = [
            ("Country", b.get("country")),
            ("Location", b.get("location")),
            ("Status", b.get("status")),
            ("Formed", b.get("formed")),
            ("Active", b.get("years_active")),
            ("Genre", ", ".join(b["genres"])),
            ("Themes", ", ".join(b["themes"])),
            ("Label", b.get("label")),
        ]
        for label, value in rows:
            if value:
                print(f"  {dim(f'{label:9}')} {value}")

        self.print_members(b)
        self.print_discography(b)

        if b["comment"]:
            print(f"\n  {bold('Description')} {dim('(as shown on the band page; the site cuts it at ~400 characters)')}")
            print(f"  {b['comment']}")
        print()

    def print_members(self, b):
        if not any(b["members"].values()):
            print(dim("\n  No lineup is listed for this band."))
        for group, title in MEMBER_GROUPS.items():
            members = b["members"][group]
            if not members:
                continue
            print(f"\n  {bold(title)} ({len(members)})")
            for m in members:
                roles = ", ".join(f"{r} ({y})" if y else r for r, y in m["roles"])
                print(f"    {m['name']:28} {dim(roles)}")

    def print_discography(self, b):
        releases = b["releases"]
        if not releases:
            print(dim("\n  No releases are listed for this band."))
            return
        print(f"\n  {bold('Discography')} ({len(releases)} releases)")
        name_width = max(len(r["name"]) for r in releases)
        type_width = max(len(r["type"]) for r in releases)
        for r in releases:
            rating = green(f"{r['rating']}% from {reviews(r['reviews'])}") if r["reviews"] else ""
            rtype = f"{r['type']:{type_width}}"
            print(f"    {r['year']}  {r['name']:{name_width}}  {dim(rtype)}  {rating}")
        rated = [r for r in releases if r["type"] == "Full-length" and r["reviews"] >= 3]
        if rated:
            best = max(rated, key=lambda r: (r["rating"], r["reviews"]))
            print(f"  {dim('Best rated full-length:')} {best['name']} "
                  f"({best['year']}, {best['rating']}% from {reviews(best['reviews'])})")

    # --- :why ------------------------------------------------------------------

    def why(self, number):
        doc_id = self.pick(number)
        if doc_id is None:
            return
        band = self.load_band(doc_id)
        if self.similar_to is not None:
            self.why_similar(band, doc_id)
            return
        if self.release_title is not None:
            print(f"\n{cyan(band['name'])} has these releases whose title contains "
                  f"{bold(yellow(self.release_title))}:")
            for r in self.release_hits[doc_id]:
                print(f"  {release_line(r)}")
            print(dim("  Found by intersecting the index postings of all words of the title, then checking\n"
                      "  the release titles of those bands. Exact title matches are listed first.\n"))
            return
        if self.query is None:
            print(dim("This is a direct answer from the extracted fields, not a ranked search."))
            return
        rows, d_norm = self.index.explain(self.query, doc_id, self.method)
        print(f"\n{cyan(band['name'])}  query: {self.query!r}")

        matches = find_matches(band, [r[0] for r in rows])
        print(f"\n  {bold('Where the query words occur')}")
        if not matches:
            print(dim("    nowhere in this band's document"))
        for field, term, count, hits in matches:
            times = f"{count}x" if count > 1 else "once"
            print(f"    {bold(term)} in {field} ({times}):")
            for text in hits:
                print(f"      {highlight(text, term)}")

        print(f"\n  {bold('Score')}  (idf={self.method}, document length |d| = {d_norm:.2f})")
        print(f"    {'term':16} {'tf':>4} {'df':>8} {'idf':>7} {'contribution':>13}")
        for term, tf, df, idf, contrib in rows:
            line = f"    {term:16} {tf:>4} {df:>8,} {idf:>7.3f} {contrib:>13.4f}"
            print(line if tf else dim(line))
        print(f"    {'score (cosine)':39} {bold(f'{sum(r[4] for r in rows):>13.4f}')}")
        print(dim("    tf = occurrences in this band's document, df = number of bands containing the word,\n"
                  "    rare words (low df) get a high idf. The score is divided by the document length,\n"
                  "    so a short document that mentions the word ranks above a long one."))
        print()

    def why_similar(self, band, doc_id):
        origin = self.load_band(self.similar_to)
        print(f"\n{cyan(band['name'])}  compared with {cyan(origin['name'])}")
        for b in (origin, band):
            print(f"  {bold(b['name'])}")
            print(f"    {dim('genre ')} {', '.join(b['genres']) or '-'}")
            print(f"    {dim('themes')} {', '.join(b['themes']) or '-'}")

        rows = self.profile.explain_similar(self.query, doc_id, self.method)
        print(f"\n  {bold('Profile of ' + origin['name'])}  (idf={self.method}; pairs of words are joined by _)")
        print(f"    {'term':22} {'df':>8} {'weight share':>13}  {band['name']} has it?")
        for term, share, has in rows:
            line = f"    {term:22} {self.profile.df(term):>8,} {share:>12.1%}  {'yes' if has else 'no'}"
            print(line if has else dim(line))
        cover = sum(share for _, share, has in rows if has)
        n_reviews = self.index.docs[doc_id]["reviews"]
        score = next(s for s, d in self.ranked if d == doc_id)
        print(f"    {'coverage (sum of shares it has)':45} {bold(f'{cover:.1%}')}")
        print(f"    {f'popularity boost 1 + {POPULARITY}*log10(1 + {n_reviews} reviews)':45} "
              f"{1 + POPULARITY * math.log10(1 + n_reviews):.3f}")
        print(f"    {'score = coverage * boost':45} {bold(f'{score:.3f}')}")
        print(dim("    Each term of the profile gets the weight (1 + log10 tf) * idf; rare terms like\n"
                  "    'war_i' weigh much more than common ones like 'metal'. Coverage is the share of the\n"
                  "    profile's squared weight that the band also has. Extra themes of the band do not lower\n"
                  "    it. Popular bands (more reviews on the site) get a small boost."))
        print()

    def compare(self, query):
        query = clean_query(query)
        cols = {m: self.index.search(query, m, self.k) for m in IDF_METHODS}
        cells = {m: [f"{d['name']} {s:.2f}" for s, d in r] for m, r in cols.items()}
        width = max(len(x) for col in cells.values() for x in col + [""]) + 3
        print(dim(f"query: {query}"))
        print("    " + "".join(bold(f"{m:{width}}") for m in cols))
        for i in range(self.k):
            row = "".join(f"{(cells[m][i] if i < len(cells[m]) else ''):{width}}" for m in cols)
            print(f"{i + 1:3} {row}")

    # --- slucka ---------------------------------------------------------------

    def command(self, line):
        cmd, _, arg = line[1:].partition(" ")
        arg = arg.strip()
        if cmd in ("q", "quit", "exit"):
            return False
        if cmd in ("h", "help", "?"):
            print(HELP.format(method=self.method, k=self.k))
        elif cmd == "idf":
            if arg in IDF_METHODS:
                self.method = arg
                print(f"idf = {arg}")
                if self.similar_to is not None:
                    self.similar(self.similar_to)
                elif self.last_line and self.release_title is None:
                    self.search(self.last_line)
            else:
                print(f"idf is {self.method}; options: {', '.join(IDF_METHODS)}")
        elif cmd == "k" and arg.isdigit() and int(arg) > 0:
            self.k = int(arg)
            print(f"k = {self.k}")
        elif cmd == "more":
            self.show_page()
        elif cmd == "similar" and arg.isdigit():
            doc_id = self.pick(int(arg))
            if doc_id is not None:
                self.similar(doc_id)
        elif cmd == "why" and arg.isdigit():
            self.why(int(arg))
        elif cmd == "compare" and (arg or self.query):
            self.compare(arg or self.query)
        else:
            print(yellow(f"Unknown command {line!r}.") + " Type :help for the list of commands.")
        return True

    def handle(self, line):
        line = line.strip()
        if not line:
            if self.query:
                self.show_page()
            return True
        if line.startswith(":"):
            return self.command(line)
        if line.isdigit() and self.ranked:
            doc_id = self.pick(int(line))
            if doc_id is not None:
                self.show_band(doc_id)
            return True
        if line.rstrip("?").lower() in ("quit", "exit"):
            return False
        if not (self.answer(line) or self.release_query(line) or self.similar_query(line)):
            self.search(line)
        return True

    def run(self):
        print(bold("Metal Archives search") +
              dim(f"  {self.index.n:,} bands, {len(self.index.postings):,} terms"))
        print(dim("Type a query or question in English, a result number for details, "
                  ":help for commands, :quit to exit."))
        while True:
            try:
                line = input("\n" + prompt_safe(green(f"[{self.method}]")) + " > ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                if not self.handle(line):
                    break
            except KeyboardInterrupt:
                print(dim("interrupted"))
