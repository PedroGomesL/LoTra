"""
Testes unitários e de regressão para a acurácia de tradução offline do LoTra.
Valida a cobertura léxica, descolamento de palavras em PDFs de 2 colunas,
motor morfológico e porcentagem de acerto no artigo científico 'AI as Extraherics' (arXiv:2409.09218v2).
"""

import unittest
import sys
import os
import re

sys.path.insert(0, os.path.abspath("src"))

from translation_engine import OfflineContextTranslator
from offline_dictionary import OFFLINE_GLUED_WORDS, OFFLINE_MULTIWORD_EXPRESSIONS, CORE_ACADEMIC_LEXICON, MorphologyEngine
from hud_tooltip import normalize_text_spacing

SAMPLE_ACADEMIC_PARAGRAPH = """
As artificial intelligence (AI) technologies, including generative AI, continue to evolve, concerns have arisen about over-reliance on AI, which may lead to human deskilling and diminished cognitive engagement. Over-reliance on AI can also lead users to accept information given by AI without performing critical examinations, causing negative consequences, such as misleading users with hallucinated contents. This paper introduces extraheric AI, a human-AI interaction conceptual framework that fosters users’ higher-order thinking skills, such as creativity, critical thinking, and problem-solving, during task completion. Unlike existing human-AI interaction designs, which replace or augment human cognition, extraheric AI fosters cognitive engagement by posing questions or providing alternative perspectives to users, rather than direct answers. We discuss interaction strategies, evaluation methods aligned with cognitive load theory and Bloom’s taxonomy, and future research directions to ensure that human cognitive skills remain a crucial element in AI-integrated environments, promotingabalancedpartnership between humans and AI.
"""

class TestTranslationAccuracy(unittest.TestCase):

    def test_morphology_engine_inflections(self):
        """Valida plurais, gerúndios, particípios e advérbios no MorphologyEngine."""
        lexicon = {
            "technology": "tecnologia",
            "examination": "exame",
            "opportunity": "oportunidade",
            "framework": "estrutura",
            "foster": "promover",
            "replace": "substituir",
            "align": "alinhar",
            "develop": "desenvolver",
            "increasing": "crescente",
            "rapid": "rápido",
        }
        # Plurais (-ies, -s)
        self.assertEqual(MorphologyEngine.translate_token("technologies", lexicon), "tecnologias")
        self.assertEqual(MorphologyEngine.translate_token("examinations", lexicon), "exames")
        self.assertEqual(MorphologyEngine.translate_token("opportunities", lexicon), "oportunidades")
        self.assertEqual(MorphologyEngine.translate_token("frameworks", lexicon), "estruturas")

        # Formas verbais em -ing e -ed
        self.assertEqual(MorphologyEngine.translate_token("fostering", lexicon), "promovendo")
        self.assertEqual(MorphologyEngine.translate_token("replacing", lexicon), "substituindo")
        self.assertEqual(MorphologyEngine.translate_token("aligned", lexicon), "alinhado")
        self.assertEqual(MorphologyEngine.translate_token("developed", lexicon), "desenvolvido")

        # Advérbios em -ly
        self.assertEqual(MorphologyEngine.translate_token("rapidly", lexicon), "rapidamente")

        # Possessivos
        self.assertEqual(MorphologyEngine.translate_token("users'", lexicon), "dos usuários")
        self.assertEqual(MorphologyEngine.translate_token("bloom's", lexicon), "de Bloom")

    def test_pdf_glued_words_ungluing(self):
        """Valida descolamento de expressões acopladas de extração PDF."""
        text_with_glued = "environments, promotingabalancedpartnership between humans and AI. In the posthumanfuture humansarenot compromised."
        translated = OfflineContextTranslator.translate(text_with_glued)
        # Não deve conter termos colados
        self.assertNotIn("promotingabalancedpartnership", translated.lower())
        self.assertNotIn("posthumanfuture", translated.lower())
        self.assertNotIn("humansarenot", translated.lower())
        # Deve conter traduções adequadas
        self.assertTrue("parceria equilibrada" in translated.lower() or "parceria" in translated.lower())

    def test_academic_paper_abstract_translation_accuracy(self):
        """Valida que a taxa de tradução no resumo do artigo científico atinge mais de 85%."""
        normalized = normalize_text_spacing(SAMPLE_ACADEMIC_PARAGRAPH)
        translated = OfflineContextTranslator.translate(normalized)

        # Extrai palavras de conteúdo do original
        words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{2,}\b', normalized)]
        # Palavras em português que são idênticas ao inglês ou nomes técnicos
        pt_common = {"a", "e", "o", "os", "as", "um", "uma", "de", "em", "no", "na", "nos", "nas", "por", "para", "com", "se", "ou", "ai", "ia"}
        content_words = [w for w in words if w not in pt_common]

        trans_lower = translated.lower()
        untranslated = []
        for w in content_words:
            # Verifica se w continua no texto traduzido como palavra em inglês não traduzida
            if re.search(rf'\b{re.escape(w)}\b', trans_lower):
                untranslated.append(w)

        translated_count = len(content_words) - len(untranslated)
        accuracy = (translated_count / len(content_words)) * 100.0

        print(f"\n[Acurácia no Abstract]: {accuracy:.2f}% ({translated_count}/{len(content_words)} palavras)")
        print(f"[Amostra Traduzida]:\n{translated[:280]}...")

        # Exigência: mais de 85% de acerto (anteriormente estava em apenas ~50%)
        self.assertGreaterEqual(accuracy, 85.0, f"Acurácia de {accuracy:.2f}% abaixo da meta de 85%")

    def test_no_residual_common_english_words(self):
        """Garante que verbos e conectivos comuns não fiquem em inglês."""
        sample = "We discuss interaction strategies and future research directions to ensure that human cognitive skills remain a crucial element."
        translated = OfflineContextTranslator.translate(sample)
        # Nenhuma palavra básica em inglês deve sobrar
        self.assertNotIn("we", translated.lower().split())
        self.assertNotIn("discuss", translated.lower().split())
        self.assertNotIn("and", translated.lower().split())
        self.assertNotIn("to", translated.lower().split())
        self.assertNotIn("ensure", translated.lower().split())
        self.assertNotIn("that", translated.lower().split())

if __name__ == "__main__":
    unittest.main()
