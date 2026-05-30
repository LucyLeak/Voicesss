import unittest

from voicesss.correction import SelfReferenceFeminizer


class SelfReferenceFeminizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.feminizer = SelfReferenceFeminizer()

    def test_complement_after_first_person_trigger(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("eu estou muito cansado hoje"),
            "eu estou muito cansada hoje",
        )

    def test_standalone_thanks(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("muito obrigado pela ajuda"),
            "muito obrigada pela ajuda",
        )

    def test_direct_self_pronoun(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("eu mesmo resolvi isso"),
            "eu mesma resolvi isso",
        )

    def test_does_not_change_unrelated_masculine_word(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("o relatorio esta atrasado, eu estou tranquilo"),
            "o relatorio esta atrasado, eu estou tranquila",
        )

    def test_does_not_break_non_gendered_phrase(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("eu tenho feito isso todos os dias"),
            "eu tenho feito isso todos os dias",
        )

    def test_mesmo_as_adverb_is_not_treated_as_pronoun(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("eu estou mesmo cansado"),
            "eu estou mesmo cansada",
        )

    def test_noun_after_identity_trigger(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("sou um desenvolvedor python"),
            "sou uma desenvolvedora python",
        )

    def test_identity_phrase_with_noun_and_adjective(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("Eu sou um garoto muito cansado"),
            "Eu sou uma garota muito cansada",
        )

    def test_plural_causative_trigger_refers_to_speaker(self) -> None:
        self.assertEqual(
            self.feminizer.normalize("certos problemas me deixam decepsionado"),
            "certos problemas me deixam decepcionada",
        )


if __name__ == "__main__":
    unittest.main()
