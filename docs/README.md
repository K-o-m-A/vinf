# Zhrnutie projektu: Vyhľadávač hudobných interpretov

Projekt je zameraný na vyhľadávač nad dátami o hudobných interpretoch. Dáta pochádzajú z www.last.fm a v druhej časti sa budú dopĺňať faktami z Wikipédie.

## Zber dát

Projekt bude scrapovať stránky interpretov z last.fm, napríklad <https://www.last.fm/music/System+of+a+Down>. Tieto stránky sa renderujú na serveri a majú jednotnú šablónu, takže sa z nich dá extrahovať bez potreby BeautifulSoup. Stránka interpreta, stránka albumu aj stránka podobných interpretov sa načítavajú ako serverové HTML, bez Cloudflare a bez toho, aby obsah dogeneroval JavaScript.

Doména povoľuje scrapovanie. Podľa robots.txt sú prístupné adresy `/music/{interpret}`, `/music/{interpret}/{album}` a prvá strana zoznamu podobných interpretov `/music/{interpret}/+similar`, zatiaľ čo `/search`, stránky žánrov `/tag/` a všetky adresy s parametrami v URL (`/music/…?…`) sú zakázané. Nie je predpísaný žiadny crawl delay, takže si medzi požiadavkami budeme udržiavať nejaké rozumné tempo. Jednotlivé adresy budeme objavovať cez oficiálnu sitemap (<https://www.last.fm/sitemap-index-secure.xml>) a zároveň postupným prechádzaním odkazov na podobných interpretov, kde sa od niekoľkých kapiel rozvetvím na ďalšie. Sitemap `top-artists` poskytuje čistý zoznam populárnych interpretov, kým „new spellings" sitemapy sú zašumené "scrobblami", preto sa budú filtrovať.

## Extrakcia informácií

Z každej stránky interpreta sa vyberie niekoľko kľúčových údajov. Podobní interpreti sú pre projekt zaujímaví, pretože na nich stoja odpovede typu „nájdi podobné skupiny". Okrem týchto polí sa uloží aj celý popisný text z biografie, aby bol k dispozícii pre full-textové indexovanie.

| Údaj | Príklad (System of a Down) |
|------|-----------------------------|
| Názov interpreta | System of a Down |
| Počet poslucháčov | 5 956 694 |
| Počet scrobbles | 531 165 345 |
| Roky aktivity | 1995 – súčasnosť |
| Miesto vzniku | Glendale, California |
| Žánrové tagy | alternative metal, nu metal, alternative |
| Top skladby | Chop Suey!, Toxicity, Aerials |
| Albumy (dátum + počet skladieb) | Toxicity (4. 9. 2001) |
| Podobní interpreti | Serj Tankian, Slipknot, Korn, Deftones |
| Popisný text (biografia) | plný text pre full-textový index |

## Implementácia vyhľadávania

V prvej fáze postavíme vlastný index ohodnotením. Používateľ zadá dopyt v anglickom jazyku, napríklad „armenian metal band", a dostane zoradený zoznam interpretov aj s ich údajmi. Vďaka zozbieraným podobným interpretom vie systém odpovedať aj na otázky, kde chce používateľ nájsť kapely podobné nejakej inej.

Druhá fáza pripája k dátam Wikipédiu. Spojenie funguje cez meno interpreta, záznam z last.fm sa napáruje na príslušný článok, napríklad <https://en.wikipedia.org/wiki/System_of_a_Down>. Fakty sa berú z infoboxu a z tela článku. Zmysel má brať najmä tie polia, ktoré na last.fm vôbec nie sú a reálne obohacujú výstup :

### Údaje z Wikipédie, ktoré na Last.fm nie sú

Last.fm sa sústredí na štatistiky počúvania a podobnosť, zatiaľ čo Wikipédia dodáva faktografiu o kapele, zloženie, vydavateľstvá, súvisiace projekty, diskografiu a ocenenia.

| Údaj z Wikipédie (infobox / článok) | Príklad (System of a Down) |
|-------------------------------------|-----------------------------|
| Členovia kapely (s nástrojmi) | Serj Tankian (spev, klávesy), Daron Malakian (gitara, spev), Shavo Odadjian (basgitara), John Dolmayan (bicie) |
| Bývalí členovia | Andy Khachaturian (bicie, 1994–1997) |
| Vydavateľstvá (labels) | American, Columbia |
| Súvisiace projekty (associated acts) | Daron Malakian and Scars on Broadway, Seven Hours After Violet |
| Presné roky aktivity vrátane prestávky | 1994–2006; 2010–súčasnosť | len približne (1995–súčasnosť) |
| Kompletná diskografia (chronologicky) | System of a Down (1998) → Toxicity (2001) → Steal This Album! (2002) → Mezmerize (2005) → Hypnotize (2005) |
| Ocenenia a certifikácie | Grammy za „B.Y.O.B." (2006); Toxicity 7× Platinum (USA) |
| Oficiálny web | systemofadown.com |

### Príklady párov stránok na napárovanie

Napárovanie prebieha cez meno interpreta. Väčšina prípadov je priamočiara (názov na Last.fm sa zhoduje s názvom článku).

| Interpret | Last.fm | Wikipedia |
|-----------|---------|-----------|
| System of a Down | <https://www.last.fm/music/System+of+a+Down> | <https://en.wikipedia.org/wiki/System_of_a_Down> |
| Serj Tankian | <https://www.last.fm/music/Serj+Tankian> | <https://en.wikipedia.org/wiki/Serj_Tankian> |
| Korn | <https://www.last.fm/music/Korn> | <https://en.wikipedia.org/wiki/Korn> |
| Deftones | <https://www.last.fm/music/Deftones> | <https://en.wikipedia.org/wiki/Deftones> |

## Ukážkové otázky

Stĺpec *What is tested at match* ukazuje, akú vyhľadávaciu schopnosť daný dopyt preveruje, od presnej zhody entity cez viacatribútové filtrovanie a full-textové vyhľadávanie až po prepojenie oboch zdrojov.

| # | Question | Expected answer | What is tested at match |
|---|----------|-----------------|--------------------------|
| 1 | Which artists are similar to System of a Down? | Serj Tankian, Slipknot, Korn, Deftones, Rage Against the Machine… | Similarity lookup je vzťah „podobní interpreti" pre danú entitu |
| 2 | How many listeners and scrobbles does System of a Down have? | ~6M listeners, ~531M scrobbles | Presná zhoda mena interpreta alebo číselné atribúty |
| 3 | Where is System of a Down from and when did they form? | Glendale, California; formed 1994 | Prepojenie Last.fm ↔ Wikipedia (obohatenie z infoboxu) |
| 4 | What genres does System of a Down play? | alternative metal, nu metal, hard rock | Viacatribútová zhoda, tagy z Last.fm + žánre z Wikipédie |
| 5 | When was the album Toxicity released? | 4 September 2001 | Presná zhoda entity albumu |
| 6 | Who are the members of System of a Down? | Serj Tankian, Daron Malakian, Shavo Odadjian, John Dolmayan | Pole z infoboxu Wikipédie ( fáza 2 - obohatenie) |
| 7 | Recommend metal bands similar to System of a Down. | Similar artists from Last.fm filtered by genre (e.g. Slipknot, Korn) | Viacatribútové filtrovanie — podobnosť + filter podľa žánru |
