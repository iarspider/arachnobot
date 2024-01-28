import unittest

from twitch_commands import translate_message


class TestRu(unittest.TestCase):
    def test_one_word(self):
        self.assertEqual(translate_message("ghbdtn"), "привет")
        self.assertEqual(translate_message("plhfdcndeqnt"), "здравствуйте")

    def test_sentence(self):
        self.assertEqual(
            translate_message("Ghbdtn! Rfr ndjb ltkbirb&"), "Привет! Как твои делишки?"
        )
        self.assertEqual(
            translate_message("Lfdyj yt ,sdfk yf cnhbvf[( Rfr gj;bdftim&"),
            "Давно не бывал на стримах( Как поживаешь?",
        )

    def test_mixed(self):
        self.assertEqual(
            translate_message(
                "Yfi`k ytlfdyj bynthtcye. buhe ghj athvthcnjd? yfpsdftncz ЭЫефквуц ЦфддунЭю Buhfk d yt` rjulf yb,elm&"
            ),
            'Нашёл недавно интересную игру про фермерстов, называется "Stardew Walley". Играл в неё когда нибудь?',
        )


class TestEng(unittest.TestCase):
    def test_one_word(self):
        self.assertEqual(translate_message("Руддщ"), "Hello")
        self.assertEqual(translate_message("Ыекфтпу"), "Strange")

    def test_sentence(self):
        self.assertEqual(
            translate_message("Руддщ! Рщц фку нщг,"), "Hello! How are you?"
        )
        self.assertEqual(
            translate_message("Црфе нщг фку вщштп кшпре тщц,"),
            "What you are doing right now?",
        )

    def test_mixed(self):
        self.assertEqual(
            translate_message(
                "Дфеудн Ш ыфц туц пфьу щт ьфклуездфсу тфьув @Hecs ghjnbd zothjd@/ Црфе нщг ерштл фищге ерфе щкерщвщч пфьу,"
            ),
            'Lately I saw new game on marketplace named "Русы против ящеров". What you think about that orthodox game?',
        )


if __name__ == "__main__":
    unittest.main()
