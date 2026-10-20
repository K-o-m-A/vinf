"""Extrakcia entit zo stiahnutych stranok Metal Archives pomocou regularnych vyrazov.

Stranka kapely (band/{id}.html):  meno, krajina, lokalita, stav, rok vzniku, zaner,
                                  temy, label, roky aktivity, popis, clenovia.
Diskografia (band_disc/{id}.html): nazov, typ, rok, pocet recenzii a priemerne hodnotenie.
"""
import html
import re

BAND_NAME = re.compile(r'<h1 class="band_name[^"]*">\s*<a href="([^"]+)">(.*?)</a>', re.S)
BAND_ID = re.compile(r"/band/discography/id/(\d+)/tab/all")
# <dt>Genre:</dt> <dd>...</dd>; obsah dd moze obsahovat odkazy, preto .*? s re.S
STAT = re.compile(r"<dt>([^<]+?):</dt>\s*<dd[^>]*>(.*?)</dd>", re.S)
COMMENT = re.compile(r'<div class="band_comment[^"]*">(.*?)(?:<div class="tool_strip|</div>)', re.S)
# sekcia jednej zostavy: od jej <div id=...> po koniec tabulky, dalsiu sekciu alebo "(None)"
LINEUP_SECTION = r'<div id="band_tab_members_{}">(.*?)(?:</table>|<div id="band_tab_members_|<em>\(None\)</em>)'
LINEUP_ROW = re.compile(
    r'<tr class="lineupRow">.*?<a href="(https://www\.metal-archives\.com/artists/[^"]+/(\d+))"[^>]*>(.*?)</a>'
    r".*?<td>\s*(.*?)\s*</td>", re.S)
RELEASE_ROW = re.compile(
    r'<tr>\s*<td><a href="(https://www\.metal-archives\.com/albums/[^"]+/(\d+))"[^>]*>(.*?)</a></td>'
    r'\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(\d{4})</td>(.*?)</tr>', re.S)
REVIEWS = re.compile(r">(\d+) \((\d+)%\)</a>")
YEAR_RANGE = re.compile(r"(\d{4}|\?)\s*-\s*(\d{4}|present|\?)")
# "Bass&nbsp;(1975-present), Keyboards&nbsp;(1997-present)": roky su za &nbsp; (\xa0),
# zatvorky v nastroji ("Vocals (lead)") maju obycajnu medzeru
ROLE_PART = re.compile(r"\s*(.+?)\xa0\(([^)]*)\)\s*,?")
PERIOD = re.compile(r"\s*\([^)]*\)")  # "(early)", "(later)" pri zanri
TAG = re.compile(r"<[^>]+>")
SPACE = re.compile(r"\s+")
COMMENTS_HTML = re.compile(r"<!--.*?-->", re.S)

FIELDS = {
    "Country of origin": "country",
    "Location": "location",
    "Status": "status",
    "Formed in": "formed",
    "Genre": "genre",
    "Themes": "themes",
    "Current label": "label",
    "Last label": "label",
    "Years active": "years_active",
}
EMPTY = {"N/A", "", "Unknown", "(None)"}
# pridavne mena zanru, ktore samostatne pred "/" znamenaju "<slovo> Metal" (resp. Rock, ...)
GENRE_MODIFIERS = frozenset("""
Atmospheric Avant-garde Black Blackened Brutal Dark Death Doom Epic Experimental Extreme
Folk Funeral Gothic Groove Heavy Industrial Melodic Neoclassical Pagan Post-Black Power
Progressive Raw Sludge Southern Speed Stoner Symphonic Technical Thrash Traditional Viking
""".split())


def clean(fragment):
    """HTML fragment -> obycajny text (bez tagov, entit a nadbytocnych medzier)."""
    text = TAG.sub(" ", COMMENTS_HTML.sub("", fragment))
    return SPACE.sub(" ", html.unescape(text)).strip()


def split_list(value, sep=","):
    return [part.strip() for part in re.split(sep, value) if part.strip()]


def split_genres(genre):
    """"Black/Death Metal (early); Doom Metal" -> ["Black Metal", "Death Metal", "Doom Metal"]."""
    genres = []
    for part in split_list(PERIOD.sub("", genre), r"[;,]"):
        pieces = split_list(part, "/")
        suffix = pieces[-1].split()[-1]  # spolocne posledne slovo, napr. "Metal"
        for piece in pieces:
            # "Black/Death Metal" -> "Black Metal", "Melodic Black/Death Metal" -> "Melodic Black Metal",
            # ale "Metalcore/Alternative Rock" ostava
            if piece.split()[-1] in GENRE_MODIFIERS and len(pieces[-1].split()) > 1 and piece != pieces[-1]:
                piece = f"{piece} {suffix}"
            if piece not in genres:
                genres.append(piece)
    return genres


def parse_members(page, section):
    m = re.search(LINEUP_SECTION.format(section), page, re.S)
    if not m:
        return []
    members = []
    for url, artist_id, name, role_html in LINEUP_ROW.findall(m.group(1)):
        raw = html.unescape(TAG.sub("", role_html)).strip()
        roles = [[clean(r), clean(y)] for r, y in ROLE_PART.findall(raw)]
        if not roles:  # bez rokov, napr. "Bass"
            roles = [[clean(raw), ""]]
        members.append({
            "id": int(artist_id), "name": clean(name), "url": url,
            "role": ", ".join(r for r, _ in roles),
            "roles": roles,  # [[nastroj, roky], ...]
        })
    return members


def extract_band(page):
    """Stranka kapely -> dict s entitami. Ak to nie je stranka kapely, vrati None."""
    m = BAND_NAME.search(page)
    if not m:
        return None
    band = {"url": m.group(1), "name": clean(m.group(2))}
    id_match = BAND_ID.search(page)
    band["id"] = int(id_match.group(1)) if id_match else int(band["url"].rsplit("/", 1)[1])

    for key, value in STAT.findall(page):
        field = FIELDS.get(key.strip())
        if field and field not in band:
            band[field] = clean(value)

    formed = band.get("formed", "")
    band["formed"] = int(formed) if formed.isdigit() else None
    band["genres"] = split_genres(band.get("genre", ""))
    band["themes"] = [] if band.get("themes", "N/A") in EMPTY else split_list(band["themes"], r"[,;]")
    band["years"] = [list(r) for r in YEAR_RANGE.findall(band.get("years_active", ""))]
    for field in ("location", "label", "country"):
        if band.get(field) in EMPTY:
            band[field] = None

    c = COMMENT.search(page)
    band["comment"] = clean(c.group(1)) if c else ""
    band["members"] = {s: parse_members(page, s) for s in ("current", "past", "live")}
    return band


def extract_discography(page):
    """Diskografia -> zoznam vydani (nazov, typ, rok, recenzie, hodnotenie v %)."""
    releases = []
    for url, album_id, name, rtype, year, rest in RELEASE_ROW.findall(page):
        r = REVIEWS.search(rest)
        releases.append({
            "id": int(album_id),
            "name": clean(name),
            "type": clean(rtype),
            "year": int(year),
            "reviews": int(r.group(1)) if r else 0,
            "rating": int(r.group(2)) if r else None,
            "url": url,
        })
    return releases
