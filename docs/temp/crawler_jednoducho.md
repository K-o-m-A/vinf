# Crawler jednoducho

## Čo crawler robí

Sťahuje stránky metalových kapiel z webu Metal Archives (www.metal-archives.com) a ukladá ich na disk. Pre každú kapelu stiahne dve stránky: hlavnú stránku kapely a jej diskografiu. Stránky ukladá surové, bez úprav. Údaje z nich (krajina, žáner, členovia, albumy…) sa vyberajú až neskôr, v samostatnom kroku.

## Ako zistí, ktoré kapely existujú

Web nemá sitemap, teda zoznam všetkých svojich stránok. Má však abecedný register kapiel (A, B, C, …, mená začínajúce číslom a ostatné znaky). Tento register sa dá stiahnuť ako JSON, vždy 500 kapiel naraz. Crawler preto najprv stiahne celý register: 419 súborov so všetkými 201 787 kapelami. Tak má úplný zoznam a žiadnu kapelu nevynechá.

## Dva kroky

**Krok 1: zoznam kapiel.** Pre každé písmeno stiahne všetky strany registra a uloží ich ako JSON súbory. Trvá to asi 25 minút a robí sa to iba raz. Pri ďalšom spustení sa už stiahnuté súbory preskočia.

**Krok 2: kapely.** Prechádza kapely zo zoznamu jednu po druhej. Pre každú:

1. pozrie sa, či ju už stiahol, a ak áno, preskočí ju,
2. stiahne hlavnú stránku kapely,
3. nájde na nej odkaz na diskografiu a stiahne ju,
4. zapíše kapelu do súboru `visited.txt`.

## Ako si pamätá, čo už stiahol

V súbore `visited.txt` je zoznam kapiel, ktoré sú už stiahnuté, jedna na riadok. Kapela sa doň zapíše hneď, ako je hotová. Crawler sa preto dá kedykoľvek zastaviť a pri ďalšom spustení pokračuje presne tam, kde skončil. Žiadna kapela sa nestiahne dvakrát.

## Ako sa správa k serveru

- **Pauza:** medzi dvoma požiadavkami čaká aspoň 3 sekundy, ako to vyžaduje súbor robots.txt (Crawl-delay: 3). K tomu pridá náhodne 0 až 1 sekundu, aby požiadavky nechodili v presne pravidelnom rytme.
- **robots.txt:** pred každou adresou skontroluje, či ju web dovoľuje sťahovať.
- **Predstaví sa:** v hlavičke User-Agent posiela „vinf-crawler/0.1 (+FIIT STU VINF school project)", nepredstiera, že je prehliadač.
- **HTTP/2:** web je chránený službou Cloudflare, ktorá starší protokol HTTP/1.1 blokuje. Cez HTTP/2 stránky prechádzajú normálne.

## Čo keď niečo zlyhá

- **Server neodpovedá:** na pripojenie čaká najviac 10 sekúnd, na dáta najviac 30 sekúnd.
- **Chyba spojenia alebo preťažený server:** skúsi to znova po 10, potom 20, potom 40 sekundách. Ak to nevyjde ani na štvrtý raz, stránku preskočí a skúsi ju pri ďalšom spustení.
- **Stránka neexistuje (404):** zapíše to do výpisu a pokračuje ďalšou kapelou.
- **Web ho zablokuje:** ak namiesto stránky príde kontrola proti robotom, crawler sa sám zastaví a takú stránku neuloží.

## Kde sú dáta

- `data/raw/band_list/` – abecedný zoznam kapiel (JSON)
- `data/raw/band/` – hlavné stránky kapiel (HTML)
- `data/raw/band_disc/` – diskografie (HTML)
- `data/visited.txt` – zoznam už stiahnutých kapiel

## Ako dlho to trvá

Jedna kapela trvá asi 7 sekúnd (dve stránky, každá s pauzou). To je približne 500 kapiel za hodinu. Celý web, teda 201 787 kapiel, trvá asi 16 dní nepretržitého sťahovania. Rýchlejšie to bez porušenia pravidiel webu nejde.

## Spustenie

```bash
.venv/bin/python -m crawler --max-bands 1000
```

Číslo za `--max-bands` určuje, koľko kapiel sa má v tomto behu stiahnuť.
