import re

from .wiki import norm_name, split_title

# MA krajina -> slova, ktorymi ju Wikipedia pise v origin / short description / kategoriach
COUNTRY_ALIASES = {
    "United States": ["United States", "U.S.", "US", "USA", "American"],
    "United Kingdom": ["United Kingdom", "UK", "U.K.", "England", "Scotland", "Wales", "Northern Ireland",
                       "British", "English", "Scottish", "Welsh"],
    "Germany": ["German"], "Brazil": ["Brazilian"], "Italy": ["Italian"], "France": ["French"],
    "Canada": ["Canadian"], "Sweden": ["Swedish"], "Finland": ["Finnish"], "Spain": ["Spanish"],
    "Russia": ["Russian"], "Poland": ["Polish"], "Mexico": ["Mexican"], "Australia": ["Australian"],
    "Argentina": ["Argentine", "Argentinian"], "Chile": ["Chilean"], "Netherlands": ["Dutch"],
    "Japan": ["Japanese"], "Indonesia": ["Indonesian"], "Greece": ["Greek"], "Colombia": ["Colombian"],
    "Norway": ["Norwegian"], "Czechia": ["Czech Republic", "Czech"], "Portugal": ["Portuguese"],
    "Belgium": ["Belgian"], "Austria": ["Austrian"], "Hungary": ["Hungarian"], "Ukraine": ["Ukrainian"],
    "Switzerland": ["Swiss"], "Denmark": ["Danish"], "Malaysia": ["Malaysian"], "Ecuador": ["Ecuadorian"],
    "Türkiye": ["Turkey", "Turkish"], "Peru": ["Peruvian"], "Slovakia": ["Slovak"], "Croatia": ["Croatian"],
    "New Zealand": ["New Zealand"], "Romania": ["Romanian"], "Ireland": ["Irish"], "Serbia": ["Serbian"],
    "Venezuela": ["Venezuelan"], "Belarus": ["Belarusian"], "Bulgaria": ["Bulgarian"],
    "Philippines": ["Filipino"], "China": ["Chinese"], "India": ["Indian"], "Israel": ["Israeli"],
    "Slovenia": ["Slovenian"], "South Africa": ["South African"], "Korea, South": ["South Korea", "Korean"],
    "Estonia": ["Estonian"], "Iceland": ["Icelandic"], "Lithuania": ["Lithuanian"], "Latvia": ["Latvian"],
    "Iran": ["Iranian"], "Faroe Islands": ["Faroese"],
}
WORD = re.compile(r"[^\W\d_]{3,}")
# slova z lokality, ktore nic nehovoria o meste
PLACE_STOP = frozenset("early later the and county city state province region area of unknown".split())


def country_words(country):
    if not country:
        return []
    return [country] + COUNTRY_ALIASES.get(country, [])


def contains_word(text, word):
    # Cele slovo/fraza, aby "US" nesedelo v "Russia"; zhoda velkych pismen pri skratkach.
    flags = 0 if len(word) <= 3 else re.I
    return re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, flags) is not None


def place_tokens(text):
    return {w.lower() for w in WORD.findall(text or "")} - PLACE_STOP


def name_tokens(name):
    # "Robert 'Bobby' Zembrzycki" -> {"robert", "bobby", "zembrzycki"}
    return frozenset(t for t in (norm_name(w) for w in re.split(r"[\s'\"]+", name or "")) if t)


def same_person(ma, wiki):
    # MA casto pise prezyvku alebo kratsie meno: "Bobby" ~ "Robert 'Bobby' Zembrzycki",
    # "Andrew Gatford" ~ "Andy Gatford" (rovnake priezvisko a zaciatocne pismeno).
    a, b = name_tokens(ma), name_tokens(wiki)
    if not a or not b:
        return False
    if norm_name(ma) == norm_name(wiki) or a <= b:
        return True
    last_a, last_b = norm_name(ma.split()[-1]), norm_name(wiki.split()[-1])
    return len(a) >= 2 and len(b) >= 2 and len(last_a) >= 3 and last_a == last_b and ma[0].lower() == wiki[0].lower()


def shared_members(band, page):
    wiki = (page.get("members") or []) + (page.get("past_members") or [])
    names = {m["name"] for section in (band.get("members") or {}).values() for m in section or []}
    return sum(any(same_person(n, w) for w in wiki) for n in names if norm_name(n))


def page_places(page):
    # origin, a ked chyba, kategorie "Musical groups from Trondheim" / "Heavy metal musical groups from California"
    places = [page.get("origin") or ""]
    places += [c.split(" from ", 1)[1] for c in page.get("categories") or [] if " from " in c]
    return place_tokens(" ".join(places))


def ma_members(band):
    # Normalizovane mena vsetkych clenov kapely z MA (aktualni, byvali, live).
    names = set()
    for section in (band.get("members") or {}).values():
        for m in section or []:
            names.add(norm_name(m["name"]))
    names.discard("")
    return names


def score(band, page):
    """Vrati (skore, priznaky) pre par kapela z MA x clanok z Wikipedie.

    priznaky: country - krajina z MA je v origin/popise/kategoriach clanku
              place   - aspon jedno slovo z MA lokality je v origin clanku (mesto, stat)
              year    - rok vzniku z MA sa lisi od zaciatku years_active najviac o 1
              members - pocet spolocnych clenov
              metal   - clanok je o metalovej kapele (zaner, popis, kategorie, kvalifikator)
              solo    - kapela sa vola ako clen z clanku, ale clanok sa tak nevola: solo projekt
                        clena ("Mike Kerr") nasiel kapelu, v ktorej hra ("Royal Blood"), cez presmerovanie
              self    - clanok o cloveku, ktory je jedinym menom aj clenom projektu ("Bruce Dickinson")
              exact   - kapela sa vola ako clanok, nie len ako presmerovanie: pri vybere vyhra
                        "Lamb of God" pred starym menom "Burn the Priest", ktore ma v MA vlastny zaznam
    """
    where = " ".join([page.get("origin") or "", page.get("short_description") or "",
                      " ".join(page.get("categories") or [])])
    country = any(contains_word(where, w) for w in country_words(band.get("country")))
    place = bool(place_tokens(band.get("location")) & page_places(page))
    formed, start = band.get("formed"), page.get("start_year")
    year = formed is not None and start is not None and abs(formed - start) <= 1
    wiki_members = {norm_name(m) for m in (page.get("members") or []) + (page.get("past_members") or [])}
    members = shared_members(band, page)
    key = norm_name(band.get("name"))
    page_keys = {norm_name(split_title(page.get("title") or "")[0]), norm_name(page.get("name"))}
    solo = key in wiki_members and key not in page_keys
    own = key in page_keys and key in ma_members(band) and not wiki_members
    about = " ".join([page.get("qualifier") or "", page.get("short_description") or "",
                      " ".join(page.get("genres") or []), " ".join(page.get("categories") or [])]).lower()
    metal = "metal" in about or "grindcore" in about or "hardcore" in about
    total = 3 * min(members, 3) + 2 * country + place + 2 * year + metal
    return total, {"country": country, "place": place, "year": year, "members": members, "metal": metal,
                   "solo": solo, "self": own, "exact": key in page_keys}


MIN_SCORE = 7


def accept(total, feats):
    # Par prijmeme pri skore aspon 7, alebo pri spolocnom clenovi a zhodnej krajine. Pri skore 4-5 bez
    # clenov (krajina + rok + "metal") bola asi tretina parov zla: rapperi, hip hop skupiny cez presmerovania.
    # Bez clenov staci zhoda krajiny, mesta, roku aj metalu (skore 6), alebo clanok o cloveku, ktory projekt
    # tvori, ak je metalovy alebo sedi mesto (inak "Ian" -> "Ian (rapper)").
    # Solo projekt "Mike Kerr" sa nespoji s kapelou, v ktorej Mike Kerr hra, ak je to jediny spolocny clen.
    if feats["solo"] and feats["members"] <= 1:
        return False
    if feats["country"] and feats["self"] and (feats["metal"] or feats["place"]):
        return True
    if feats["country"] and feats["place"] and feats["year"] and feats["metal"]:
        return True
    return total >= MIN_SCORE or (feats["members"] > 0 and feats["country"])
