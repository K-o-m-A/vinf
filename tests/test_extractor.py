"""Unit testy REGEX extraktorov na 20 realnych stiahnutych strankach (tests/fixtures/).

Spustenie: python -m unittest discover -s tests -v
"""
import html
import unittest
from pathlib import Path

from crawler.crawler import BAND_ID_IN_PAGE, BAND_LINK
from extractor.extract import extract_band, extract_discography, split_genres

FIXTURES = Path(__file__).parent / "fixtures"

# file_id: (meno, krajina, stav, rok vzniku, zanre, label,
#           pocet clenov (aktualni, bivali, live), pocet vydani, prve vydanie (nazov, typ, rok, recenzie, %))
EXPECTED = {
    "125": ("Metallica", "United States", "Active", 1981, ["Thrash Metal", "Hard Rock", "Heavy Metal"],
            "Blackened Recordings", (4, 4, 4), 941, ("No Life 'til Leather", "Demo", 1982, 10, 87)),
    "71": ("Down", "United States", "Active", 1991, ["Southern Metal", "Sludge Metal"],
           "Nuclear Blast Records", (5, 3, 3), 17, ("1992 Demos", "Demo", 1992, 0, None)),
    "25": ("Iron Maiden", "United Kingdom", "Active", 1975, ["Heavy Metal", "NWOBHM"],
           "Parlophone", (6, 17, 4), 129, ("The Soundhouse Tapes", "EP", 1979, 3, 84)),
    "99": ("Black Sabbath", "United Kingdom", "Split-up", 1969, ["Heavy Metal", "Doom Metal"],
           "Vertigo Records", (4, 21, 8), 166, ("Evil Woman", "Single", 1970, 2, 88)),
    "72": ("Slayer", "United States", "Active", 1981, ["Thrash Metal"],
           "Nuclear Blast Records", (3, 3, 6), 58, ("Show No Mercy", "Full-length", 1983, 35, 90)),
    "146": ("Darkthrone", "Norway", "Active", 1987,
            ["Death Metal", "Black Metal", "Doom Metal", "Heavy Metal", "Speed Metal"],
            "Peaceville Records", (2, 3, 1), 55, ("Land of Frost", "Demo", 1988, 2, 94)),
    "38": ("Opeth", "Sweden", "Active", 1990, ["Progressive Death Metal", "Progressive Rock"],
           "Reigning Phoenix Music", (5, 16, 6), 47, ("Orchid", "Full-length", 1995, 28, 84)),
    "88": ("Burzum", "Norway", "Active", 1991, ["Black Metal", "Ambient"],
           "Byelobog Productions", (1, 0, 0), 35, ("Demo I", "Demo", 1991, 9, 75)),
    "78": ("Sepultura", "Brazil", "Active", 1984, ["Death Metal", "Thrash Metal", "Nu-Metal", "Groove Metal"],
           "Nuclear Blast Records", (4, 11, 7), 85, ("Bestial Devastation / Século XX", "Split", 1985, 1, 85)),
    "30": ("Emperor", "Norway", "Active", 1991, ["Symphonic Black Metal"],
           "Candlelight Records", (3, 6, 12), 26, ("Wrath of the Tyrant", "Demo", 1992, 6, 83)),
    "11": ("In Flames", "Sweden", "Active", 1990,
           ["Melodic Death Metal", "Melodic Groove Metal", "Metalcore", "Alternative Rock"],
           "Nuclear Blast Records", (5, 11, 16), 65, ("Demo '93", "Demo", 1993, 3, 92)),
    "3540261645": ("Carcharoth Λ.V.", "Germany", "Active", 2007, ["Atmospheric Metal", "Ambient Black Metal"],
                   "Unsigned/independent", (2, 0, 0), 8, ("Rehearsal '07", "Demo", 2007, 0, None)),
    "3540453125": ("Black Eucharist", "United States", "Active", 2021, ["Black Metal"],
                   "Stygian Black Hand", (3, 0, 0), 1, ("Inn of the Vaticide", "Full-length", 2023, 1, 75)),
    "100323": ("Armagbuwar", "Brazil", "Unknown", None, ["Black Metal", "Death Metal"],
               "Unsigned/independent", (0, 0, 0), 1, ("War in Fog", "Split", 1999, 0, None)),
    "66454": ("Zôikitá", "Brazil", "Unknown", 2001, ["Thrash Metal"],
              "Unsigned/independent", (5, 0, 0), 1, ("Only We Can", "Demo", 2003, 0, None)),
    "100100": ("Canobliss", "United States", "Changed name", 1996, ["Thrash Metal", "Groove Metal"],
               "Unsigned/independent", (5, 1, 0), 13, ("Wicked Necessary", "Full-length", 1998, 0, None)),
    "100176": ("Necro Cult", "United States", "On hold", 2007, ["Raw Black Metal"],
               "Nokturnal Transmissions Records", (1, 0, 2), 12, ("Kroatoan / Necro Cult", "Split", 2007, 0, None)),
    "10000": ("Treblinka", "Canada", "Split-up", 1985, ["Thrash Metal"],
              "Unsigned/independent", (5, 3, 0), 2, ("Trial of War", "Demo", 1987, 0, None)),
    "1000": ("Gothic Knights", "United States", "Active", 1990, ["Heavy Metal", "Power Metal"],
             "Unsigned/independent", (4, 9, 1), 10, ("To Hell and Back", "Demo", 1994, 0, None)),
    "10008": ("Mastaba", "Brazil", "Split-up", 1984, ["Thrash Metal"],
              "Unsigned/independent", (4, 0, 0), 0, None),
}


def load(kind, file_id):
    return (FIXTURES / kind / f"{file_id}.html").read_text(encoding="utf-8")


class TestFixturePages(unittest.TestCase):
    """Rovnaka sada kontrol pre vsetkych 20 stranok (kazda stranka je vlastny subTest)."""

    def test_band_pages(self):
        self.assertEqual(len(EXPECTED), 20)
        for file_id, exp in EXPECTED.items():
            name, country, status, formed, genres, label, members, _, _ = exp
            with self.subTest(band=name):
                band = extract_band(load("band", file_id))
                self.assertIsNotNone(band)
                self.assertEqual(band["name"], name)
                self.assertEqual(band["id"], int(file_id))
                self.assertEqual(band["country"], country)
                self.assertEqual(band["status"], status)
                self.assertEqual(band["formed"], formed)
                self.assertEqual(band["genres"], genres)
                self.assertEqual(band["label"], label)
                counts = tuple(len(band["members"][s]) for s in ("current", "past", "live"))
                self.assertEqual(counts, members)
                self.assertTrue(band["url"].endswith(f"/{file_id}"))

    def test_discographies(self):
        for file_id, exp in EXPECTED.items():
            count, first = exp[7], exp[8]
            with self.subTest(band=exp[0]):
                releases = extract_discography(load("band_disc", file_id))
                self.assertEqual(len(releases), count)
                if first:
                    r = releases[0]
                    self.assertEqual((r["name"], r["type"], r["year"], r["reviews"], r["rating"]), first)
                for r in releases:
                    self.assertRegex(r["url"], r"^https://www\.metal-archives\.com/albums/.+/\d+$")
                    self.assertNotIn("<", r["name"])

    def test_no_html_left_in_text_fields(self):
        for file_id in EXPECTED:
            band = extract_band(load("band", file_id))
            for field in ("name", "country", "location", "genre", "label", "years_active", "comment"):
                value = band.get(field) or ""
                with self.subTest(band=band["name"], field=field):
                    self.assertNotRegex(value, r"<[a-z/][^>]*>")
                    self.assertNotRegex(value, r"&(amp|nbsp|#\d+);")


class TestEdgeCases(unittest.TestCase):
    def test_metallica_details(self):
        band = extract_band(load("band", "125"))
        self.assertEqual(band["location"], "Los Angeles/San Francisco, California")
        self.assertEqual(band["years"], [["1981", "present"]])
        self.assertEqual(band["themes"][:3], ["Introspection", "Anger", "Corruption"])
        hetfield = band["members"]["current"][1]
        self.assertEqual(hetfield["name"], "James Hetfield")
        self.assertEqual(hetfield["id"], 170)
        # zatvorka "(lead)" je sucast nastroja, roky su az za &nbsp;
        self.assertEqual(hetfield["roles"], [["Vocals (lead), Guitars (rhythm)", "1981-present"]])
        self.assertEqual(band["members"]["past"][0]["name"], "Cliff Burton")
        self.assertIn("Metallica was formed by Lars Ulrich and James Hetfield", band["comment"])

    def test_multiple_roles_with_years(self):
        harris = extract_band(load("band", "25"))["members"]["current"][0]
        self.assertEqual(harris["name"], "Steve Harris")
        self.assertEqual(harris["roles"], [["Bass", "1975-present"], ["Keyboards", "1997-present"]])
        self.assertEqual(harris["role"], "Bass, Keyboards")

    def test_role_without_years(self):
        member = extract_band(load("band", "10000"))["members"]["current"][0]
        self.assertEqual(member["roles"], [["Bass", ""]])

    def test_years_active_with_former_name(self):
        band = extract_band(load("band", "3540453125"))
        self.assertIn("(as Black Ejaculate )", band["years_active"])
        self.assertEqual(band["years"], [["2018", "2021"], ["2021", "present"]])

    def test_multiple_activity_periods(self):
        band = extract_band(load("band", "30"))
        self.assertEqual(band["years"], [["1991", "2001"], ["2005", "2007"], ["2013", "2014"], ["2016", "present"]])

    def test_band_name_with_nocaps_class(self):
        # Greckou abecedou: <h1 class="band_name noCaps">
        self.assertEqual(extract_band(load("band", "3540261645"))["name"], "Carcharoth Λ.V.")

    def test_unicode_name(self):
        band = extract_band(load("band", "66454"))
        self.assertEqual(band["name"], "Zôikitá")
        self.assertEqual(band["themes"], [])  # Themes: N/A

    def test_missing_values_are_none(self):
        band = extract_band(load("band", "100323"))
        self.assertIsNone(band["location"])
        self.assertIsNone(band["formed"])
        self.assertEqual(band["years"], [])
        self.assertEqual(band["members"], {"current": [], "past": [], "live": []})

    def test_location_with_periods(self):
        band = extract_band(load("band", "88"))
        self.assertTrue(band["location"].startswith("Bergen, Vestland (early)"))

    def test_empty_discography(self):
        self.assertEqual(extract_discography(load("band_disc", "10008")), [])

    def test_release_without_reviews(self):
        r = extract_discography(load("band_disc", "71"))[0]
        self.assertEqual((r["reviews"], r["rating"]), (0, None))

    def test_not_a_band_page(self):
        self.assertIsNone(extract_band("<html><title>Client Challenge</title></html>"))


class TestGenres(unittest.TestCase):
    def test_split_genres(self):
        cases = {
            "Black/Death Metal": ["Black Metal", "Death Metal"],
            "Doom/Death/Black Metal": ["Doom Metal", "Death Metal", "Black Metal"],
            "Thrash Metal (early); Hard Rock (mid); Heavy/Thrash Metal (later)":
                ["Thrash Metal", "Hard Rock", "Heavy Metal"],
            "Death Metal/Grindcore": ["Death Metal", "Grindcore"],
            "Melodic Groove Metal/Metalcore/Alternative Rock":
                ["Melodic Groove Metal", "Metalcore", "Alternative Rock"],
            "Punk/Thrash Metal": ["Punk", "Thrash Metal"],
            "Melodic Black/Death Metal": ["Melodic Black Metal", "Death Metal"],
            "Blackened Death/Doom Metal": ["Blackened Death Metal", "Doom Metal"],
            "Progressive Metal/Rock": ["Progressive Metal", "Rock"],
        }
        for genre, expected in cases.items():
            with self.subTest(genre=genre):
                self.assertEqual(split_genres(genre), expected)


class TestCrawlerUrlRegex(unittest.TestCase):
    """REGEX na extrakciu URL, ktore pouziva crawler."""

    def test_band_link_from_list_json(self):
        row = "<a href='https://www.metal-archives.com/bands/A_--_Solution/3540442600'>A // Solution</a>"
        self.assertEqual(BAND_LINK.search(row).group(1),
                         "https://www.metal-archives.com/bands/A_--_Solution/3540442600")

    def test_band_link_with_entities(self):
        row = "<a href='https://www.metal-archives.com/bands/Guns_N&#039;_Roses/1234'>Guns N' Roses</a>"
        url = html.unescape(BAND_LINK.search(row).group(1))
        self.assertEqual(url, "https://www.metal-archives.com/bands/Guns_N'_Roses/1234")

    def test_band_link_ignores_other_links(self):
        self.assertIsNone(BAND_LINK.search("<a href='https://www.metal-archives.com/labels/Foo/1'>Foo</a>"))

    def test_discography_id_from_band_page(self):
        for file_id in EXPECTED:
            with self.subTest(file_id=file_id):
                self.assertEqual(BAND_ID_IN_PAGE.search(load("band", file_id)).group(1), file_id)


if __name__ == "__main__":
    unittest.main()
