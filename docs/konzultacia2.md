# Konzultácia 2: Crawler

## Zmena zdroja dát: last.fm → Metal Archives

Pôvodný plán bol crawlovať www.last.fm. Začiatkom októbra 2026 však last.fm nasadil anti-bot ochranu (Fastly „Client Challenge"). Každá stránka interpreta, albumu aj `+similar` teraz pre klienta bez JavaScriptu vráti stránku, ktorá obsahuje iba JavaScriptovú výzvu, nie dáta. Obchádzať túto ochranu (headless prehliadač, riešenie výzvy) nechceme, preto sme zdroj zmenili.

**Encyclopaedia Metallum (www.metal-archives.com)** vracia serverom renderované HTML, robots.txt povoľuje stránky kapiel aj albumov a obsahuje takmer všetky polia z pôvodného návrhu:

| Údaj | Stránka | Príklad (Down) |
|------|---------|----------------|
| Názov, krajina, mesto | `/bands/{meno}/{id}` | Down, United States, New Orleans, Louisiana |
| Rok vzniku, roky aktivity, stav | `/bands/{meno}/{id}` | 1991; 1991–1996, 1999–2002, 2006–present; Active |
| Žáner, textové témy, label | `/bands/{meno}/{id}` | Southern/Sludge Metal; Personal struggles, Misery; Nuclear Blast |
| Členovia (aktuálni aj bývalí, s nástrojmi) | `/bands/{meno}/{id}` | Phil Anselmo, Pepper Keenan, … |
| Plný popisný text (biografia) | `/band/read-more/id/{id}` | text pre full-textový index |
| Diskografia (názov, typ, rok, recenzie) | `/band/discography/id/{id}/tab/all` | NOLA, Full-length, 1995, 17 recenzií (87 %) |
| Album: presný dátum, label, zoznam skladieb | `/albums/{kapela}/{album}/{id}` | NOLA, 19. 9. 1995 |
| Podobní interpreti (s hodnotením používateľov) | `/band/ajax-recommendations/id/{id}?showMoreSimilar=1` | Crowbar, Corrosion of Conformity, Pantera |

Oproti last.fm prichádzame o počty poslucháčov. Získavame však presnejšie faktografické polia a hodnotenia albumov z recenzií. Obmedzenie: databáza obsahuje len metalové kapely čo je pre nás ale vlastne preferované. Druhá fáza (obohatenie z Wikipédie) zostáva rovnaká, párovanie prebieha cez meno kapely a krajinu.

## 1. Aké frameworky chceme používať?

| Časť | Nástroj | Prečo |
|------|---------|-------|
| Jazyk | Python 3.12 | |
| HTTP | `httpx` s HTTP/2 | jediná externá závislosť crawlera; Cloudflare pred Metal Archives vracia challenge každému HTTP/1.1 klientovi (aj `requests` a `curl --http1.1`), cez HTTP/2 stránky prechádzajú |
| robots.txt | `urllib.robotparser` (štandardná knižnica) | kontrola `Disallow` aj `Crawl-delay` |
| Extrakcia odkazov a dát | `re` (regulárne výrazy), `json` pre abecedný zoznam kapiel | bez BeautifulSoup/Scrapy, crawler aj parser sú vlastná implementácia |
| Ukladanie | súbory HTML/JSON + textový súbor so stiahnutými kapelami | jednoduché, dá sa kedykoľvek znova parsovať bez opätovného sťahovania |
| Index, 1. fáza | vlastný invertovaný index v Pythone (TF-IDF / BM25) | |
| Wikipédia, 2. fáza | dump `enwiki-pages-articles` + Apache Spark (PySpark) | spracovanie veľkého dumpu a join s kapelami |
| Index, 2. fáza | PyLucene | full-text vyhľadávanie nad spojenými dátami |
| Prostredie | Docker | Spark a PyLucene v kontajneri |

## 2. Architektúra crawl systému

Metal Archives nemá sitemap. Úplný zoznam kapiel však ponúka abecedný register (`/lists/A` … `/lists/Z`, `/lists/NBR` pre mená začínajúce číslom a `/lists/~` pre ostatné znaky). Tabuľku v ňom stránka dopĺňa z adresy `/browse/ajax-letter/l/{písmeno}/json/1`, ktorá vracia JSON s 500 kapelami na požiadavku (URL kapely, krajina, žáner, stav). robots.txt ju nezakazuje. Crawler preto začína týmito 28 zoznamami a nepotrebuje žiadne štartovacie kapely.

Pre každú kapelu sa zatiaľ sťahujú dve stránky: hlavná stránka kapely a jej diskografia. Podobné kapely, plná biografia a stránky albumov sa v tejto fáze nesťahujú.

Crawler beží v dvoch krokoch. Keďže poradie stránok je vopred dané (zoznam → kapela → jej diskografia), nepotrebuje všeobecný front URL adries.

**Návrh na vysokej úrovni:**

```mermaid
flowchart LR
    subgraph SYS["python -m crawler"]
        Q["Front URL<br/>kapely zo zoznamu, ktoré<br/>ešte nie sú vo visited.txt"]
        C["Crawler<br/>- stiahni stránku (HTTP/2, pauza 3 s)<br/>- ulož surové HTML / JSON<br/>- vytiahni URL (regex)"]
        D[("data/raw/<br/>HTML + JSON")]
        V[("visited.txt")]
        Q --> C
        C --> D
        C --> V
        C -. "vytiahnuté URL späť do frontu:<br/>kapely zo zoznamu,<br/>diskografia zo stránky kapely" .-> Q
    end
    C <--> DNS(["DNS"])
    C <--> WEB(["metal-archives.com"])
    style SYS stroke-dasharray: 6 6
```

**Presný priebeh oboch krokov:**

```mermaid
flowchart TD
    START(["python -m crawler --max-bands N"]) --> R["načítaj robots.txt<br/>(zakázané adresy, Crawl-delay: 3)"]
    R --> L0
    subgraph K1["Krok 1: abecedný zoznam kapiel"]
        L0["ďalšie písmeno A–Z, NBR, ~<br/>start = 0"] --> E1{"band_list/{písmeno}_{start}.json<br/>už existuje?"}
        E1 -->|nie| DL["stiahni a ulož JSON<br/>so 500 kapelami"]
        E1 -->|áno, prečítaj z disku| T
        DL --> T["start += 500"]
        T --> M1{"start < iTotalRecords?"}
        M1 -->|áno| E1
    end
    M1 -->|nie, ďalšie písmeno| L0
    DL -->|chyba, preskoč písmeno| L0
    M1 -->|nie, všetky písmená hotové| B1
    subgraph K2["Krok 2: kapely"]
        B1{"ďalšia kapela zo zoznamu,<br/>ktorá nie je vo visited.txt?"} -->|áno| BP["stiahni stránku kapely<br/>→ band/{id}.html"]
        BP -->|OK| DP["nájdi id diskografie (regex)<br/>stiahni diskografiu → band_disc/{id}.html"]
        DP --> AP["pripíš URL kapely do visited.txt"]
        AP --> MX{"už N kapiel<br/>v tomto behu?"}
        MX -->|nie| B1
        BP -->|chyba: preskoč, skúsi sa<br/>pri ďalšom behu| B1
    end
    MX -->|áno| END(["koniec"])
    B1 -->|nie, všetko stiahnuté| END
```

- **Krok 1, zoznam kapiel:** pre každé písmeno sa sťahujú strany zoznamu (`iDisplayStart` = 0, 500, 1000, …), kým nie je dosiahnutý počet kapiel `iTotalRecords` z prvej odpovede. Každá strana sa uloží ako JSON. Strany, ktoré už na disku sú, sa znova nesťahujú. Celý zoznam má 419 strán (~25 minút).
- **Krok 2, kapely:** URL kapiel sa čítajú priamo z uložených JSON súborov zoznamu. Pre každú kapelu, ktorá ešte nie je v `data/visited.txt`, sa stiahne hlavná stránka a hneď za ňou diskografia. Až potom sa URL kapely pripíše do `visited.txt`.
- **Čo už bolo stiahnuté:** jediným stavom crawlera je `data/visited.txt`, jedna URL kapely na riadok. Žiadna kapela sa tak nestiahne dvakrát a crawl sa dá kedykoľvek prerušiť (Ctrl+C). Pri ďalšom spustení pokračuje tam, kde skončil.
- **Id kapely** sa berie zo stránky (z odkazu na diskografiu), nie z URL. Stránka `/bands/Mastodon/9006` totiž zobrazí Mastodon aj s nesprávnym id (skutočné je 1361) a diskografia postavená z id v URL by vrátila 404.
- **Blokovanie:** ak server namiesto obsahu vráti anti-bot stránku („Client Challenge", „Just a moment…"), crawler ju neuloží ako dáta a skončí.

## 3. Hlavičky, timeout, pauza

| Nastavenie | Hodnota |
|------------|---------|
| `User-Agent` | `vinf-crawler/0.1 (+FIIT STU VINF school project)`, poctivo sa identifikujeme ako crawler |
| `Accept` | `text/html,application/xhtml+xml;q=0.9,*/*;q=0.8` |
| `Accept-Language` | `en-US,en;q=0.8` |
| `Accept-Encoding` | `gzip, deflate` |
| Protokol | HTTP/2, jedno spojenie pre celý crawl (`httpx.Client`) |
| Timeout | 10 s na pripojenie, 30 s na čítanie odpovede |
| Pauza medzi požiadavkami | 3 s (`Crawl-delay: 3` z robots.txt) + náhodne 0–1 s |
| Opakovanie | max. 3× pri chybe spojenia, timeoute, 429 a 5xx; čakanie 10 s → 20 s → 40 s, prípadne podľa hlavičky `Retry-After` |
| 404 a iné chyby | zalogujú sa a crawler pokračuje ďalšou kapelou; kapela sa nezapíše do `visited.txt`, takže sa pri ďalšom behu skúsi znova |
| robots.txt | pred každou URL `can_fetch()`; zakázané sú `/affiliate/`, `/history/`, `/report/`, `/forum/`, `/users/` |

**Stiahnutie jednej stránky:**

```mermaid
flowchart TD
    A(["stiahni URL"]) --> RB{"povolená<br/>v robots.txt?"}
    RB -->|nie| NONE(["preskoč, zapíš do výpisu"])
    RB -->|áno| W["počkaj, kým od začiatku poslednej požiadavky<br/>neuplynú 3 s + náhodne 0–1 s"]
    W --> G["HTTP/2 GET s hlavičkami<br/>timeout: 10 s spojenie, 30 s odpoveď"]
    G -->|chyba spojenia,<br/>timeout, 429, 5xx| RT{"zostáva opakovanie?<br/>(max. 3)"}
    RT -->|áno| BO["čakaj 10 → 20 → 40 s<br/>alebo podľa Retry-After"] --> W
    RT -->|nie| NONE
    G -->|odpoveď| BL{"nadpis Client Challenge /<br/>Just a moment / Attention Required?"}
    BL -->|áno| STOP(["BlockedError: celý crawl sa zastaví,<br/>stránka sa neuloží"])
    BL -->|nie| ST{"status 200?"}
    ST -->|áno| OK(["vráť HTML / JSON"])
    ST -->|nie, napr. 404| NONE
```

Pri pauze ~3,5 s to vychádza na približne 1 000 stránok za hodinu. Na jednu kapelu pripadajú 2 stránky, čiže ~500 kapiel za hodinu. Celý register (201 787 kapiel) je ~400 000 stránok, teda približne 16 dní nepretržitého sťahovania.

## 4. Implementácia a stiahnuté stránky

Kód je v priečinku [`crawler/`](../crawler):

| Súbor | Úloha |
|-------|-------|
| `config.py` | hlavičky, timeouty, pauzy, cesty |
| `fetcher.py` | HTTP klient, robots.txt, rate limiting, retry, detekcia blokovania |
| `crawler.py` | krok 1 (zoznam kapiel) a krok 2 (kapela + diskografia), extrakcia odkazov regulárnymi výrazmi |
| `__main__.py` | spustenie z príkazového riadku |

Spustenie:

```bash
pip install -r requirements.txt
python -m crawler --max-bands 1000   # kapely z data/visited.txt preskočí
```


Stiahnuté kapely sú v [`data/visited.txt`](../data/visited.txt).
