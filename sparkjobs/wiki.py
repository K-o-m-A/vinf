import html
import re
import unicodedata

TITLE = re.compile(r"<title>(.*?)</title>", re.S)
NS = re.compile(r"<ns>(\d+)</ns>")
PAGE_ID = re.compile(r"<id>(\d+)</id>")  # prve <id> v <page> je id stranky, dalsie su revizie
REDIRECT = re.compile(r'<redirect title="([^"]*)"')
TEXT = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S)

INFOBOX_START = re.compile(r"\{\{\s*Infobox[ _]+(?:musical[ _]+artist|band|musician)\s*(?=[|\n}<])", re.I)
BRACES = re.compile(r"\{\{|\}\}")
# pole infoboxu: "| current_members = ..." na zaciatku riadku, hodnota po dalsie pole
FIELD = re.compile(r"^\s*\|\s*([A-Za-z_ ]+?)\s*=(.*?)(?=^\s*\|\s*[A-Za-z_ ]+?\s*=|\Z)", re.S | re.M)
CATEGORY = re.compile(r"\[\[\s*Category\s*:\s*([^|\]]+?)\s*(?:\|[^\]]*)?\]\]", re.I)
SHORT_DESC = re.compile(r"\{\{\s*Short description\s*\|([^}|]*)", re.I)
QUALIFIER = re.compile(r"\s*\(([^)]*)\)\s*$")  # "Death (metal band)" -> "metal band"

COMMENT = re.compile(r"<!--.*?-->", re.S)
REF = re.compile(r"<ref[^>/]*/>|<ref[^>]*>.*?</ref>", re.S | re.I)
BR = re.compile(r"<br\s*/?>", re.I)
HTML_TAG = re.compile(r"</?[a-z][^>]*>", re.I)
LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")  # [[ciel|text]] -> text, [[ciel]] -> ciel
LINK_TARGET = re.compile(r"\[\[([^|\]#]+)")
EXT_LINK = re.compile(r"\[(?:https?:)?//\S+\s+([^\]]*)\]")  # [http://x.com text] -> text
URL_TEMPLATE = re.compile(r"\{\{\s*(?:URL|official URL)\s*\|\s*([^}|]+)", re.I)
# sablony, ktorych argumenty su polozky zoznamu: {{hlist|a|b}}, {{flatlist|* a * b}}, {{ubl|a|b}}
LIST_TEMPLATE = re.compile(r"\{\{\s*(?:hlist|flatlist|flat list|plainlist|plain list|ubl|unbulleted list|"
                           r"bulleted list|blist|nowrap|nobr|small|lang\|[a-z-]+)\s*\|?", re.I)
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")  # ostatne (citacie, {{efn}}, ...) sa zahodia
LIST_SEP = re.compile(r"\n\s*\*+|\|\s*|<br>|•|·|;")
SPACE = re.compile(r"\s+")
YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)\b")
# polozky, ktore nie su mena: "List of Opeth band members", "See former members", "Final lineup"
JUNK_ITEM = re.compile(r"^\(?\s*(?:see\b|list of\b|full list\b|final line-?up|former members|previous members)",
                       re.I)
# sekcia "== Members ==" v tele clanku, ked infobox clenov nema
MEMBERS_SECTION = re.compile(r"^==\s*(?:band\s+)?(?:members|line-?ups?|personnel)\s*==\s*$(.*?)(?=^==[^=]|\Z)",
                             re.I | re.M | re.S)
BULLET = re.compile(r"^\*+\s*(.+)$")
FORMER = re.compile(r"former|past|previous", re.I)
SUBHEADING = re.compile(r"^(?:=+[^=]+=+|'''[^']+'''|[^*][^:]{0,30}:)\s*$")
# "Chuck Schuldiner – guitars (1995–1997)" -> "Chuck Schuldiner"; pomlcka len s medzerou, aby ostalo "Jean-Pierre"
MEMBER_ROLE = re.compile(r"\s+[–—-]\s*|\s*[–—]\s*|\s*[(,:;]")
# clanky bez hudobneho infoboxu, ktore su o skupine: kratky popis alebo kategorie
BAND_DESC = re.compile(r"\b(?:band|musical group|music group|musical project|musical duo|musical trio|supergroup)\b",
                       re.I)
NOT_BAND_DESC = re.compile(r"\b(?:album|song|single|EP|discography|tour|festival|record label|film|episode|list|"
                           r"members?|topics referred)\b", re.I)
BAND_CATEGORY = re.compile(r"\bmusical (?:groups|duos|trios|quartets|quintets|sextets)\b", re.I)
DISAMBIGUATION = re.compile(r"\{\{\s*(?:disambig|dab\b|hndis|set index)", re.I)
ESTABLISHED = re.compile(r"established in (1[89]\d\d|20\d\d)")
# uvodny odsek: text pred prvym nadpisom bez sablon, obrazkov a tabuliek
HEADING = re.compile(r"^==", re.M)
FILE_LINK = re.compile(r"\[\[\s*(?:File|Image)\s*:[^\[\]]*\]\]", re.I)  # bez vnorenych odkazov
FILE_PREFIX = re.compile(r"\[\[\s*(?:File|Image)\s*:", re.I)  # "[[Imagery (album)|...]]" nie je obrazok
TABLE = re.compile(r"\{\|.*?\|\}", re.S)
EMPTY_PARENS = re.compile(r"\(\s*[,;]?\s*\)")
PARENS_LEAD_PUNCT = re.compile(r"\(\s*[,;]\s*")  # "(; born 1974)" po odstraneni vyslovnosti
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:])")
PARAGRAPH = re.compile(r"\n\s*\n")

# polia infoboxu, ktore nas zaujimaju; zoznamove sa rozdelia na polozky
LIST_FIELDS = {
    "genre": "genres", "label": "labels", "current_members": "members", "members": "members",
    "past_members": "past_members", "associated_acts": "associated_acts", "spinoffs": "spinoffs",
    "spinoff_of": "spinoff_of", "alias": "aliases", "instrument": "instruments",
}
TEXT_FIELDS = {"name": "name", "origin": "origin", "years_active": "years_active",
               "website": "website", "background": "background", "birth_name": "birth_name"}


def norm_name(name):
    # Kluc pre join: bez diakritiky, malymi pismenami, bez interpunkcie, "&" = "and", bez uvodneho "the".
    # "Mötley Crüe" -> "motleycrue", "The Black Dahlia Murder" -> "blackdahliamurder"
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower().replace("&", " and ")
    text = re.sub(r"^\s*the\s+", "", text)
    return re.sub(r"[\W_]+", "", text)


def split_title(title):
    # "Death (metal band)" -> ("Death", "metal band"), "Opeth" -> ("Opeth", "")
    m = QUALIFIER.search(title)
    return (title[:m.start()], m.group(1)) if m else (title, "")


def template_end(text, start):
    # Koniec sablony od pozicie start ("{{..."): pocita vnorenie {{ a }}, vrati index za "}}".
    depth = 0
    for m in BRACES.finditer(text, start):
        depth += 1 if m.group() == "{{" else -1
        if depth == 0:
            return m.end()
    return len(text)


def clean_value(value):
    # Hodnota pola infoboxu -> obycajny text (bez odkazov, referencii, komentarov a HTML).
    value = REF.sub("", COMMENT.sub("", value))
    value = URL_TEMPLATE.sub(r"\1", value)
    value = LIST_TEMPLATE.sub("", value)
    value = BR.sub("<br>", value)
    for _ in range(3):  # vnorene sablony (citacie v citaciach)
        value = TEMPLATE.sub("", value)
    value = value.replace("}}", "").replace("{{", "")
    value = LINK.sub(r"\1", EXT_LINK.sub(r"\1", value))
    value = HTML_TAG.sub("", value.replace("<br>", "\n* ")).replace("'''", "").replace("''", "")
    return value


def split_items(value):
    # Zoznamove pole -> polozky: "* a\n* b", "a<br>b", "{{hlist|a|b}}" -> ["a", "b"].
    # Ciarky delime len ak v hodnote nie je iny oddelovac (",": "Stockholm, Sweden" nie je zoznam).
    cleaned = clean_value(value)
    parts = LIST_SEP.split("\n" + cleaned)
    if len([p for p in parts if p.strip()]) <= 1:
        parts = cleaned.split(",")
    items = []
    for part in parts:
        item = SPACE.sub(" ", part).strip(" ,.*:")
        if item and item not in items and len(item) < 120 and not JUNK_ITEM.match(item):
            items.append(item)
    return items


def member_name(item):
    # Polozka zoznamu clenov -> meno bez nastroja, rokov a uvodzoviek ('"Big" Mike' -> "Big Mike").
    name = MEMBER_ROLE.split(item, maxsplit=1)[0].replace('"', "").strip(" '*")
    return name if name and len(name.split()) <= 5 and not JUNK_ITEM.match(name) else None


def members_section(text):
    # Clenovia zo sekcie "== Members ==": odrazky pred podnadpisom s "former/past" su aktualni, za nim byvali.
    current, past = [], []
    m = MEMBERS_SECTION.search(text)
    if not m:
        return current, past
    target = current
    for line in m.group(1).split("\n"):
        line = line.strip()
        bullet = BULLET.match(line)
        if bullet:
            name = member_name(SPACE.sub(" ", clean_value(bullet.group(1))).strip())
            if name and name not in current + past:
                target.append(name)
        elif SUBHEADING.match(line) and FORMER.search(line):
            target = past
    return current, past


def lead_paragraph(text):
    # Prvy odsek clanku ako obycajny text: "Metallica is an American heavy metal band. It was formed ..."
    m = HEADING.search(text)
    lead = REF.sub("", COMMENT.sub("", text[:m.start()] if m else text))
    for _ in range(10):  # vnorene sablony ({{Infobox ... {{hlist|...}} }}) a obrazky s odkazmi v popise
        stripped = TEMPLATE.sub("", lead)
        stripped = FILE_LINK.sub("", LINK.sub(lambda l: l.group(0) if FILE_PREFIX.match(l.group(0))
                                              else l.group(1), stripped))
        if stripped == lead:
            break
        lead = stripped
    lead = TABLE.sub("", lead)
    lead = HTML_TAG.sub("", EXT_LINK.sub(r"\1", lead)).replace("'''", "").replace("''", "")
    for para in PARAGRAPH.split(lead):
        para = SPACE.sub(" ", para).strip()
        if len(para) >= 40 and para[0] not in "|!*{}:[":
            para = PARENS_LEAD_PUNCT.sub("(", EMPTY_PARENS.sub("", para))
            return SPACE_BEFORE_PUNCT.sub(r"\1", para).replace("  ", " ")
    return None


def is_band_article(text, short, categories):
    # Clanok bez hudobneho infoboxu berieme, ak ho kratky popis (alebo bez popisu kategorie) oznacuju za skupinu.
    if DISAMBIGUATION.search(text):
        return False
    if short:
        return bool(BAND_DESC.search(short)) and not NOT_BAND_DESC.search(short)
    return any(BAND_CATEGORY.search(c) for c in categories)


def link_targets(value):
    # Ciele wiki odkazov v poli: "[[Bill Andrews (drummer)|Bill Andrews]]" -> "Bill Andrews (drummer)".
    return [t.strip() for t in LINK_TARGET.findall(COMMENT.sub("", value)) if ":" not in t]


def parse_infobox(text):
    # Najde {{Infobox musical artist ...}} a vrati slovnik vybranych poli, alebo None.
    m = INFOBOX_START.search(text)
    if not m:
        return None
    body = text[m.end():template_end(text, m.start()) - 2]
    info = {}
    for key, value in FIELD.findall(body):
        key = key.strip().lower().replace(" ", "_")
        if key in LIST_FIELDS:
            field = LIST_FIELDS[key]
            info.setdefault(field, [])
            items = split_items(value)
            if field in ("members", "past_members"):
                items = [n for n in map(member_name, items) if n]
            info[field] += [i for i in items if i not in info[field]]
            if field == "associated_acts":
                info["associated_links"] = link_targets(value)
        elif key in TEXT_FIELDS:
            info[TEXT_FIELDS[key]] = SPACE.sub(" ", clean_value(value).replace("\n* ", ", ").replace("|", ", ")).strip(" ,*")
    years = YEAR.findall(info.get("years_active", ""))
    info["start_year"] = int(years[0]) if years else None
    return info


def parse_page(page):
    # Jeden <page> element -> slovnik, alebo None ak stranka nie je clanok (ns != 0),
    # nie je presmerovanie, nema hudobny infobox a nie je ani o skupine. Presmerovania vraciame, lebo
    # dalsie mena kapely ("Amorphis (band)" -> "Amorphis") su pre join uzitocne.
    title = TITLE.search(page)
    ns = NS.search(page)
    if not title or not ns or ns.group(1) != "0":
        return None
    title = html.unescape(title.group(1))
    pid = int(PAGE_ID.search(page).group(1))
    redirect = REDIRECT.search(page)
    if redirect:
        return {"id": pid, "title": title, "redirect": html.unescape(redirect.group(1))}
    m = TEXT.search(page)
    if not m:
        return None
    text = html.unescape(m.group(1))
    short = SHORT_DESC.search(text)
    short = short.group(1).strip() if short else None
    categories = CATEGORY.findall(text)
    info = parse_infobox(text)
    has_infobox = info is not None
    if not has_infobox:
        if title.startswith("List of") or not is_band_article(text, short, categories):
            return None
        info = {"start_year": None}
    if not info.get("members") and not info.get("past_members"):
        info["members"], info["past_members"] = members_section(text)
    if info["start_year"] is None:
        years = [int(y) for c in categories for y in ESTABLISHED.findall(c)]
        info["start_year"] = min(years) if years else None
    return {
        "id": pid, "title": title, "redirect": None,
        "qualifier": split_title(title)[1],
        "short_description": short,
        "categories": categories,
        "length": len(text),
        "infobox": has_infobox,
        "lead": lead_paragraph(text),
        **info,
    }
