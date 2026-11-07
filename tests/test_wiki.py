import re
import unittest
from pathlib import Path

from sparkjobs.matching import accept, same_person, score
from sparkjobs.wiki import clean_value, lead_paragraph, member_name, norm_name, parse_page, split_items, split_title

SAMPLE = Path(__file__).parent / "fixtures" / "wiki" / "sample.xml"
PAGES = {p["title"]: p for p in map(parse_page, re.findall(r"<page>.*?</page>", SAMPLE.read_text(), re.S)) if p}


class TestNormalization(unittest.TestCase):
    def test_norm_name(self):
        self.assertEqual(norm_name("Mötley Crüe"), "motleycrue")
        self.assertEqual(norm_name("The Black Dahlia Murder"), "blackdahliamurder")
        self.assertEqual(norm_name("Emerson, Lake & Palmer"), "emersonlakeandpalmer")
        self.assertEqual(norm_name("AC/DC"), norm_name("ACDC"))

    def test_split_title(self):
        self.assertEqual(split_title("Death (metal band)"), ("Death", "metal band"))
        self.assertEqual(split_title("Opeth"), ("Opeth", ""))


class TestWikitext(unittest.TestCase):
    def test_clean_value(self):
        self.assertEqual(clean_value("[[Stockholm]], Sweden<ref>{{cite web|x}}</ref>"), "Stockholm, Sweden")
        self.assertEqual(clean_value("<!-- x -->[[Bill Andrews (drummer)|Bill Andrews]]"), "Bill Andrews")

    def test_split_items(self):
        self.assertEqual(split_items("{{hlist|[[Roadrunner Records|Roadrunner]]|Relapse}}"), ["Roadrunner", "Relapse"])
        self.assertEqual(split_items("{{flatlist|\n* [[Death metal]]\n* {{nowrap|[[speed metal]]}}\n}}"),
                         ["Death metal", "speed metal"])
        self.assertEqual(split_items("Tony Iommi<br />Bill Ward"), ["Tony Iommi", "Bill Ward"])
        self.assertEqual(split_items("Columbia, Atlantic"), ["Columbia", "Atlantic"])
        self.assertEqual(split_items("* Varg\n* [[List of Opeth band members|See list]]"), ["Varg"])


class TestParsePage(unittest.TestCase):
    def test_skips_non_artist_pages(self):
        self.assertNotIn("Death (disambiguation)", PAGES)  # bez infoboxu
        self.assertNotIn("Metallica (album)", PAGES)       # Infobox album

    def test_metallica(self):
        p = PAGES["Metallica"]
        self.assertEqual(p["origin"], "Los Angeles, California, U.S.")
        self.assertEqual(p["start_year"], 1981)
        self.assertEqual(p["members"], ["James Hetfield", "Lars Ulrich", "Kirk Hammett", "Robert Trujillo"])
        self.assertIn("Cliff Burton", p["past_members"])
        self.assertIn("Elektra", p["labels"])
        self.assertIn("Megadeth", p["spinoffs"])
        self.assertEqual(p["short_description"], "American heavy metal band")

    def test_death_qualifier_and_categories(self):
        p = PAGES["Death (metal band)"]
        self.assertEqual((p["name"], p["qualifier"]), ("Death", "metal band"))
        self.assertIn("Chuck Schuldiner", p["past_members"])
        self.assertNotIn("Final lineup", p["past_members"])
        self.assertIn("Musical groups established in 1984", p["categories"])

    def test_members_section(self):
        p = PAGES["Control Denied"]  # infobox bez clenov, clenovia v sekcii "== Members =="
        self.assertTrue(p["infobox"])
        self.assertEqual(p["members"][:2], ["Chuck Schuldiner", "Steve Di Giorgio"])
        self.assertIn("Brian Benson", p["past_members"])

    def test_band_without_infobox(self):
        p = PAGES["Exitium"]
        self.assertFalse(p["infobox"])
        self.assertEqual(p["past_members"][:2], ["Brandon Carrigan", "Kirk Kirkwood"])
        self.assertIn("Ancient Dome", PAGES)
        self.assertEqual(PAGES["Mayhem (band)"]["start_year"], 1984)

    def test_lead_paragraph(self):
        self.assertTrue(PAGES["Metallica"]["lead"].startswith(
            "Metallica is an American heavy metal band. It was formed in Los Angeles in 1981"))
        self.assertNotIn("<ref", PAGES["Metallica"]["lead"])
        self.assertTrue(PAGES["Sepultura"]["lead"].startswith('Sepultura ("grave") is a Brazilian heavy metal band'))
        self.assertTrue(PAGES["Mikael Åkerfeldt"]["lead"].startswith("Lars Mikael Åkerfeldt (born 17 April 1974)"))
        self.assertTrue(PAGES["Exitium"]["lead"].startswith("Exitium was an American grind band"))  # bez infoboxu
        lead = lead_paragraph("'''Neuraxis''' released [[Imagery (album)|Imagery]] in 1997 and many other albums.\n\n== History ==")
        self.assertEqual(lead, "Neuraxis released Imagery in 1997 and many other albums.")

    def test_member_role_stripped(self):
        self.assertEqual(member_name("Andy Gatford – guitars (1987–1993)"), "Andy Gatford")
        self.assertEqual(member_name('"Big" Mike'), "Big Mike")
        self.assertEqual(member_name("Jean-Pierre Leduc"), "Jean-Pierre Leduc")

    def test_solo_artist(self):
        p = PAGES["Mikael Åkerfeldt"]
        self.assertEqual(p["background"], "solo_singer")
        self.assertEqual(p["instruments"], ["Vocals", "guitar"])


class TestMatching(unittest.TestCase):
    MAYHEM_NO = {"id": 67, "name": "Mayhem", "country": "Norway", "location": "Langhus, Viken", "formed": 1984,
                 "members": {"current": [{"name": "Necrobutcher"}, {"name": "Hellhammer"}], "past": [], "live": []}}
    MAYHEM_DE = {"id": 19879, "name": "Mayhem", "country": "Germany", "location": "Kassel, Hesse", "formed": 1985,
                 "members": {"current": [{"name": "Stefan"}], "past": [], "live": []}}

    def test_right_band_wins(self):
        page = PAGES["Mayhem (band)"]
        no, feats = score(self.MAYHEM_NO, page)
        de, de_feats = score(self.MAYHEM_DE, page)
        self.assertTrue(feats["country"] and feats["year"] and feats["members"] == 2)
        self.assertTrue(feats["exact"])  # meno clanku, nie presmerovanie
        self.assertGreater(no, de)
        self.assertTrue(accept(no, feats))
        self.assertFalse(accept(de, de_feats))  # rovnake meno, ina krajina, bez clenov

    def test_accept_rules(self):
        def feats(**on):
            return {"country": False, "place": False, "year": False, "members": 0, "metal": False,
                    "solo": False, "self": False, **on}
        self.assertFalse(accept(5, feats(country=True, year=True, metal=True)))  # rapperi, hip hop cez presmerovania
        self.assertTrue(accept(6, feats(country=True, place=True, year=True, metal=True)))
        self.assertFalse(accept(3, feats(members=1)))
        self.assertTrue(accept(5, feats(country=True, members=1)))
        self.assertFalse(accept(5, feats(country=True, place=True, year=True)))  # "Fiend (rapper)"
        self.assertTrue(accept(3, feats(country=True, metal=True, self=True)))
        self.assertFalse(accept(2, feats(country=True, self=True)))  # "Ian" -> "Ian (rapper)"
        self.assertTrue(accept(15, feats(country=True, place=True, year=True, metal=True, members=5, solo=True)))

    def test_solo_project_of_member(self):
        band = {"name": "Necrobutcher", "country": "Norway", "formed": 2010,
                "members": {"current": [{"name": "Necrobutcher"}], "past": [], "live": []}}
        total, feats = score(band, PAGES["Mayhem (band)"])
        self.assertTrue(feats["solo"])
        self.assertFalse(accept(total, feats))

    def test_own_article_of_one_man_project(self):
        band = {"name": "Mikael Åkerfeldt", "country": "Sweden", "formed": None,
                "members": {"current": [{"name": "Mikael Åkerfeldt"}], "past": [], "live": []}}
        total, feats = score(band, PAGES["Mikael Åkerfeldt"])
        self.assertTrue(feats["self"] and not feats["solo"])
        self.assertTrue(accept(total, feats))

    def test_member_nicknames(self):
        self.assertTrue(same_person("Bobby", "Robert 'Bobby' Zembrzycki"))
        self.assertTrue(same_person("Andrew Gatford", "Andy Gatford"))
        self.assertTrue(same_person("Mikael Åkerfeldt", "Mikael Akerfeldt"))
        self.assertFalse(same_person("Dan", "Danila Lopuha"))
        self.assertFalse(same_person("John Smith", "Mark Smith"))

    def test_members_from_body(self):
        band = {"name": "Control Denied", "country": "United States", "location": "Tampa, Florida", "formed": 1995,
                "members": {"current": [{"name": "Chuck Schuldiner"}, {"name": "Tim Aymar"}], "past": [], "live": []}}
        total, feats = score(band, PAGES["Control Denied"])
        self.assertEqual(feats["members"], 2)
        self.assertTrue(accept(total, feats))

    def test_us_alias(self):
        band = {"name": "Death", "country": "United States", "location": "Altamonte Springs, Florida",
                "formed": 1984, "members": {}}
        _, feats = score(band, PAGES["Death (metal band)"])
        self.assertTrue(feats["country"] and feats["place"] and feats["metal"])


if __name__ == "__main__":
    unittest.main()
