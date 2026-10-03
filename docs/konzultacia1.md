# Zhrnutie projektu: Vyhľadávač metalových kapiel

Projekt je zameraný na vyhľadávač nad dátami o metalových kapelách. Dáta pochádzajú z Encyclopaedia Metallum (www.metal-archives.com) a v druhej časti sa budú dopĺňať faktami z Wikipédie.

## Zber dát

Projekt bude scrapovať stránky kapiel z Metal Archives, napríklad <https://www.metal-archives.com/bands/Kanonenfieber/3540483079>. Tieto stránky sa renderujú na serveri a majú jednotnú šablónu, takže sa z nich dá extrahovať bez potreby BeautifulSoup. Diskografiu kapely stránka načítava z vlastnej adresy `/band/discography/id/{id}/tab/all`, ktorá takisto vracia hotové serverové HTML, takže obsah nedogeneruje JavaScript a dá sa stiahnuť priamo.

Doména povoľuje scrapovanie. Podľa robots.txt sú prístupné stránky kapiel `/bands/{kapela}/{id}`, ich diskografie `/band/discography/id/{id}/tab/all` aj abecedný register kapiel, zatiaľ čo `/affiliate/`, `/history/`, `/report/`, `/forum/` a `/users/` sú zakázané. robots.txt predpisuje `Crawl-delay: 3`, takže medzi požiadavkami budeme čakať aspoň 3 sekundy. Doména neponúka sitemap, adresy kapiel preto budeme objavovať cez abecedný register (`/lists/A` … `/lists/Z`, `/lists/NBR`, `/lists/~`). Ten svoju tabuľku načítava z adresy `/browse/ajax-letter/l/{písmeno}/json/1`, ktorá vracia 500 kapiel na požiadavku, takže celý zoznam približne 200 000 kapiel získame zhruba 400 požiadavkami. Pre každú kapelu sa potom stiahne jej hlavná stránka a diskografia.

## Extrakcia informácií

Z hlavnej stránky kapely a jej diskografie sa vyberie niekoľko kľúčových údajov. Ďalšie kapely členov sú pre projekt zaujímavé, pretože prepájajú kapely cez ľudí a na nich stoja odpovede typu „v akých kapelách hrali členovia". Okrem týchto polí sa uloží aj úvodný popisný text z hlavnej stránky, aby bol k dispozícii pre full-textové indexovanie.

| Údaj | Príklad (Kanonenfieber) |
|------|-------------------------|
| Názov kapely | Kanonenfieber |
| Krajina pôvodu | Germany |
| Miesto | Bamberg, Bavaria |
| Rok vzniku | 2020 |
| Roky aktivity, stav | 2020 – súčasnosť, Active |
| Žáner | Melodic Black/Death Metal |
| Textové témy | World War I |
| Aktuálne vydavateľstvo | Century Media Records |
| Členovia (s nástrojmi a obdobím) | Noise (všetky nástroje, 2020–) |
| Koncertní členovia | Gunnar (basgitara, vokály, 2021–), Hans (bicie, 2021–), Sickfried (rytmická gitara, 2021–), Ernst (sólová gitara, 2025–) |
| Bývalí koncertní členovia | Kreuzer (sólová gitara, 2021–2025) |
| Diskografia (názov, typ, rok, hodnotenie recenzií) | Die Urkatastrophe, Full-length, 2024, 11 recenzií (82 %) |
| Ďalšie kapely členov | Noise: Leiþa, Non Est Deus; Gunnar, Hans, Sickfried, Kreuzer: Non Est Deus (live) |
| Úvod biografie | prvých ~400 znakov textu pre full-textový index („"Kanonenfieber" is German for "cannon fever" and is synonymous with … "shell shock"…") |

## Implementácia vyhľadávania

V prvej fáze postavíme vlastný index s ohodnotením. Používateľ zadá dopyt v anglickom jazyku, napríklad „black metal band about World War I", a dostane zoradený zoznam kapiel aj s ich údajmi. Vďaka zozbieraným členom a ich ďalším kapelám vie systém odpovedať aj na otázky, ako sú kapely prepojené cez ľudí.

Druhá fáza pripája k dátam Wikipédiu. Spojenie funguje cez meno kapely, záznam z Metal Archives sa napáruje na príslušný článok, napríklad <https://en.wikipedia.org/wiki/Kanonenfieber>. Pri rovnakom mene viacerých kapiel pomáha krajina pôvodu. Fakty sa berú z infoboxu a z tela článku. Zmysel má brať najmä tie polia, ktoré na Metal Archives vôbec nie sú a reálne obohacujú výstup:

### Údaje z Wikipédie, ktoré na Metal Archives nie sú

Metal Archives sa sústredí na zloženie kapiel, diskografiu a recenzie, zatiaľ čo Wikipédia dodáva históriu vydavateľstiev, porovnania s inými kapelami, opis vedľajších projektov, image kapely a širšie žánrové zaradenie.

| Údaj z Wikipédie (infobox / článok) | Príklad (Kanonenfieber) |
|-------------------------------------|-------------------------|
| Všetky vydavateľstvá (labels) | Noisebringer Records, Avantgarde Music, Century Media |
| Kapely, s ktorými sa porovnáva zvuk | 1914, Bolt Thrower, Minenwerfer |
| Vedľajšie projekty a ich témy | Non Est Deus (fanatické náboženstvo), Leiþa (zúfalstvo, nenávisť k sebe, depresia) |
| Image kapely | anonymní členovia v nemeckých uniformách z 1. svetovej vojny a v maskách, odkaz na Hrob neznámeho vojína |
| Žánre podľa Wikipédie | blackened death metal, melodic death metal, melodic black metal |
| Oficiálny web | kanonenfieber.noisebringer.de |

### Príklady párov stránok na napárovanie

Napárovanie prebieha cez meno kapely. Väčšina prípadov je priamočiara (názov na Metal Archives sa zhoduje s názvom článku). Pri menách, ktoré majú aj iný význam, pridáva Wikipédia k názvu prívlastok „(band)".

| Kapela | Metal Archives | Wikipedia |
|--------|----------------|-----------|
| Kanonenfieber | <https://www.metal-archives.com/bands/Kanonenfieber/3540483079> | <https://en.wikipedia.org/wiki/Kanonenfieber> |
| 1914 | <https://www.metal-archives.com/bands/1914/3540396156> | <https://en.wikipedia.org/wiki/1914_(band)> |
| Bolt Thrower | <https://www.metal-archives.com/bands/Bolt_Thrower/234> | <https://en.wikipedia.org/wiki/Bolt_Thrower> |
| Minenwerfer | <https://www.metal-archives.com/bands/Minenwerfer/3540309791> | <https://en.wikipedia.org/wiki/Minenwerfer_(band)> |

## Ukážkové otázky

Stĺpec *What is tested at match* ukazuje, akú vyhľadávaciu schopnosť daný dopyt preveruje, od presnej zhody entity cez viacatribútové filtrovanie a full-textové vyhľadávanie až po prepojenie oboch zdrojov.

| # | Question | Expected answer | What is tested at match |
|---|----------|-----------------|--------------------------|
| 1 | In which other bands do Kanonenfieber members play? | Leiþa, Non Est Deus (Noise); Non Est Deus (live members) | Vzťah kapela → člen → iná kapela pre danú entitu |
| 2 | Where is Kanonenfieber from and when were they formed? | Bamberg, Bavaria, Germany; 2020 | Presná zhoda mena kapely a jej atribúty |
| 3 | Which bands is Kanonenfieber's sound compared to? | 1914, Bolt Thrower, Minenwerfer | Prepojenie Metal Archives ↔ Wikipedia (obohatenie z článku) |
| 4 | What genres does Kanonenfieber play? | Melodic Black/Death Metal, blackened death metal, melodic death metal | Viacatribútová zhoda, žáner z Metal Archives + žánre z Wikipédie |
| 5 | In which year was the album Die Urkatastrophe released? | 2024 | Presná zhoda entity albumu v diskografii |
| 6 | On which record labels has Kanonenfieber released music? | Noisebringer Records, Avantgarde Music, Century Media | Pole z infoboxu a diskografie Wikipédie (fáza 2 - obohatenie) |
| 7 | Recommend black/death metal bands with lyrics about World War I. | Kanonenfieber (Germany), 1914 (Ukraine), Minenwerfer (United States)… | Viacatribútové filtrovanie — filter podľa žánru a textových tém |
