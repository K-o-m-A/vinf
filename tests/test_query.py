"""Unit testy rozboru otazok (filtre a typy otazok) a normalizacie slov v indexe.

Spustenie: python -m unittest discover -s tests -t . -v
"""
import unittest

from indexer.index import fold, profile_tokenize, tokenize
from indexer.query import Filters, country_lookup, detect_intent, member_group, parse_filters

COUNTRIES = country_lookup(["United States", "Brazil", "Sweden", "Slovakia", "Norway", "Korea, South",
                            "Türkiye", "Czechia", "United Kingdom", "Armenia", "Germany"])


def parse(line):
    return parse_filters(line, COUNTRIES)


class TestFilters(unittest.TestCase):
    def test_country_genre_decade(self):
        f, _ = parse("thrash metal bands from Brazil formed in the 1980s")
        self.assertEqual(f.countries, {"Brazil"})
        self.assertEqual(f.formed, (1980, 1989))
        self.assertEqual(f.genre_words, {"thrash"})

    def test_demonym(self):
        f, rest = parse("swedish melodic death metal gothenburg")
        self.assertEqual(f.countries, {"Sweden"})
        self.assertEqual(f.genre_words, {"melodic", "death"})
        self.assertEqual(rest, "gothenburg")

    def test_country_aliases(self):
        self.assertEqual(parse("doom bands from the USA")[0].countries, {"United States"})
        self.assertEqual(parse("korean bands")[0].countries, {"Korea, South"})
        self.assertEqual(parse("turkish thrash")[0].countries, {"Türkiye"})
        self.assertEqual(parse("czech grindcore")[0].countries, {"Czechia"})
        self.assertEqual(parse("english heavy metal")[0].countries, {"United Kingdom"})

    def test_years(self):
        self.assertEqual(parse("bands formed in 1991")[0].formed, (1991, 1991))
        self.assertEqual(parse("grindcore from the late 90s")[0].formed, (1996, 1999))
        self.assertEqual(parse("early 2000s metalcore")[0].formed, (2000, 2003))
        self.assertEqual(parse("black metal before 1995")[0].formed, (None, 1994))
        self.assertEqual(parse("death metal since 2010")[0].formed, (2010, None))
        self.assertEqual(parse("death metal after 2010")[0].formed, (2011, None))
        self.assertEqual(parse("bands formed between 1985 and 1990")[0].formed, (1985, 1990))

    def test_status(self):
        self.assertEqual(parse("active black metal bands from Slovakia")[0].status, "Active")
        self.assertEqual(parse("disbanded doom bands")[0].status, "Split-up")
        self.assertEqual(parse("split-up thrash bands")[0].status, "Split-up")
        self.assertEqual(parse("bands on hold")[0].status, "On hold")

    def test_theme_is_not_genre(self):
        # "death" za "about" je tema, nie zaner
        f, rest = parse("bands that sing about death")
        self.assertFalse(f)
        self.assertIn("death", rest)

    def test_band_name_is_not_filter(self):
        f, rest = parse("Black Sabbath")
        self.assertFalse(f)
        self.assertEqual(rest, "black sabbath")
        f, rest = parse("Kanonenfieber")
        self.assertFalse(f)
        self.assertEqual(rest, "kanonenfieber")

    def test_metal_alone_is_no_filter(self):
        f, _ = parse("metal band from Armenia")
        self.assertEqual(f.countries, {"Armenia"})
        self.assertEqual(f.genre_words, set())

    def test_slovakian_metal_bands(self):
        for line in ("slovakian metal bands", "slovak metal bands", "metal bands from Slovakia"):
            with self.subTest(line=line):
                f, _ = parse(line)
                self.assertEqual(f.countries, {"Slovakia"})
                self.assertEqual(f.genre_words, set())
        self.assertEqual(parse("slovakian black metal bands")[0].genre_words, {"black"})

    def test_match(self):
        f, _ = parse("norwegian black metal before 1995")
        doc = {"country": "Norway", "formed": 1991, "status": "Active", "genres": ["Black Metal", "Ambient"]}
        self.assertTrue(f.match(doc))
        self.assertFalse(f.match({**doc, "formed": 1999}))
        self.assertFalse(f.match({**doc, "formed": None}))
        self.assertFalse(f.match({**doc, "country": "Sweden"}))
        self.assertFalse(f.match({**doc, "genres": ["Death Metal"]}))
        self.assertIs(Filters().match(doc), True)


class TestIntents(unittest.TestCase):
    def test_intents(self):
        cases = {
            "Who are the members of Metallica?": ("members", "Metallica"),
            "who played in Phantom Lord": ("members", "Phantom Lord"),
            "Which bands did Dave Mustaine play in?": ("person", "Dave Mustaine"),
            "What is the best rated album of Opeth?": ("best", "Opeth"),
            "What is the best rated Opeth full-length album?": ("best", "Opeth"),
            "best rated black metal albums": (None, None),
            "albums by Opeth": ("discography", "Opeth"),
            "Where is Burzum from?": ("fact", "Burzum"),
            "When was Slayer formed?": ("fact", "Slayer"),
            "Who is Dave Mustaine?": ("who", "Dave Mustaine"),
            "Who are the members of Kanonenfieber?": ("members", "Kanonenfieber"),
            "Where is Kanonenfieber from?": ("fact", "Kanonenfieber"),
            "When was Kanonenfieber formed?": ("fact", "Kanonenfieber"),
            "swedish death metal": (None, None),
            "Which band has an album named Besnota": (None, None),
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(detect_intent(line), expected)


    def test_member_group(self):
        self.assertEqual(member_group("Who are the current members of Metallica?"), "current")
        self.assertEqual(member_group("former members of Metallica"), "past")
        self.assertEqual(member_group("live musicians of Opeth"), "live")
        self.assertIsNone(member_group("members of Metallica"))


class TestNormalization(unittest.TestCase):
    def test_fold_removes_diacritics(self):
        self.assertEqual(fold("Sarcófago"), "sarcofago")
        self.assertEqual(fold("Türkiye"), "turkiye")

    def test_tokenize_plural_and_accents(self):
        self.assertEqual(tokenize("Vikings Wars Sarcófago"), ["viking", "war", "sarcofago"])
        # "ss", "us", "is" sa nemenia
        self.assertEqual(tokenize("bass virus genesis"), ["bass", "virus", "genesis"])

    def test_profile_word_pairs(self):
        self.assertEqual(profile_tokenize("World War I"), ["world", "war", "world_war", "war_i"])
        self.assertNotIn("world_war", profile_tokenize("New World Order"))


if __name__ == "__main__":
    unittest.main()
