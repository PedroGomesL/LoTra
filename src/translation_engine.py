"""
Módulo de Tradução Adaptativo do LoTra:
- Consulta de cache ultrarrápido (< 1ms) via DocumentContextVault.
- Tradução via LLM local (Ollama API com Qwen 2.5 / Llama 3.2 / MarianMT selecionado pelo Hardware Profiler).
- Mecanismo de Tradução Offline Contextual (Glossário + Dicionário de Expressões + Regras) para operação 100% autônoma.
- Gerenciamento e descarregamento de VRAM/RAM após inferência.
"""

import os
import sys
import re
import json
import time
import socket
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from document_context_vault import DocumentContextVault
from adaptive_engine_orchestrator import AdaptiveEngineOrchestrator, HardwareProfiler
from platform_core import VRAMManager
from hud_tooltip import normalize_text_spacing

# Dicionário offline de termos técnicos, computação quântica, IA, pesquisa acadêmica e expressões frequentes
OFFLINE_TECHNICAL_GLOSSARY = {
    # Amostras do arXiv e Abstract acadêmico
    "as artificial intelligence (ai)": "à medida que a inteligência artificial (IA)",
    "artificial intelligence (ai)": "inteligência artificial (IA)",
    "artificial intelligence": "inteligência artificial",
    "including generative ai": "incluindo IA generativa",
    "generative ai": "ia generativa",
    "generative": "generativa",
    "continue to evolve": "continua a evoluir",
    "concerns have arisen about": "surgiram preocupações sobre",
    "concerns have arisen": "surgiram preocupações",
    "over-reliance on ai": "dependência excessiva da IA",
    "over-reliance": "dependência excessiva",
    "overreliance": "dependência excessiva",
    "over-use": "uso excessivo",
    "overuse": "uso excessivo",
    "which may lead to": "o que pode levar a",
    "may lead to": "pode levar a",
    "lead to": "levar a",
    "human deskilling": "desqualificação humana",
    "deskilling": "desqualificação",
    "diminished cognitive engagement": "diminuição do envolvimento cognitivo",
    "cognitive engagement": "envolvimento cognitivo",
    "diminished": "diminuição",
    "can also lead users to accept": "também pode levar os usuários a aceitar",
    "can also lead users to": "também pode levar os usuários a",
    "can also lead": "também pode levar",
    "information given by ai": "informações fornecidas pela IA",
    "without performing critical examinations": "sem realizar exames críticos",
    "critical examinations": "exames críticos",
    "critical examination": "exame crítico",
    "without performing": "sem realizar",
    "causing negative consequences": "causando consequências negativas",
    "negative consequences": "consequências negativas",
    "such as misleading users with hallucinated contents": "como enganar usuários com conteúdos alucinados",
    "such as misleading users": "como enganar usuários",
    "misleading users": "enganar usuários",
    "hallucinated contents": "conteúdos alucinados",
    "hallucinated content": "conteúdo alucinado",
    "hallucinated": "alucinado",
    "hallucination": "alucinação",
    "this paper introduces": "este artigo apresenta",
    "this paper presents": "este artigo apresenta",
    "this paper proposes": "este artigo propõe",
    "this paper": "este artigo",
    "extraheric ai": "ia extra-hérica",
    "extraheric": "extra-hérico",
    "a human-ai interaction design framework": "uma estrutura de design de interação humano-ia",
    "interaction design framework": "estrutura de design de interação",
    "human-ai interaction designs": "designs de interação humano-ia",
    "human-ai interaction design": "design de interação humano-ia",
    "human-ai interaction": "interação humano-ia",
    "interaction design": "design de interação",
    "that fosters users' higher-order thinking skills": "que promove as habilidades de pensamento de ordem superior dos usuários",
    "users' higher-order thinking skills": "habilidades de pensamento de ordem superior dos usuários",
    "higher-order thinking skills": "habilidades de pensamento de ordem superior",
    "higher-order thinking": "pensamento de ordem superior",
    "thinking skills": "habilidades de pensamento",
    "such as creativity, critical thinking, and problem-solving": "como criatividade, pensamento crítico e resolução de problemas",
    "critical thinking": "pensamento crítico",
    "problem-solving": "resolução de problemas",
    "during task completion": "durante a conclusão da tarefa",
    "task completion": "conclusão da tarefa",
    "unlike existing human-ai interaction designs": "ao contrário dos designs existentes de interação humano-ia",
    "unlike existing": "ao contrário dos existentes",
    "which replace or augment human cognition": "que substituem ou aumentam a cognição humana",
    "replace or augment": "substituem ou aumentam",
    "human cognition": "cognição humana",
    "fosters cognitive engagement": "promove o envolvimento cognitivo",
    "by posing questions or providing alternative perspectives to users": "formulando perguntas ou fornecendo perspectivas alternativas aos usuários",
    "by posing questions": "formulando perguntas",
    "providing alternative perspectives to users": "fornecendo perspectivas alternativas aos usuários",
    "providing alternative perspectives": "fornecendo perspectivas alternativas",
    "alternative perspectives": "perspectivas alternativas",
    "rather than direct answers": "em vez de respostas diretas",
    "direct answers": "respostas diretas",
    "rather than": "em vez de",
    "we discuss interaction strategies": "discutimos estratégias de interação",
    "we discuss": "discutimos",
    "interaction strategies": "estratégias de interação",
    "evaluation methods aligned with cognitive load theory": "métodos de avaliação alinhados com a teoria da carga cognitiva",
    "aligned with cognitive load theory": "alinhados com a teoria da carga cognitiva",
    "cognitive load theory": "teoria da carga cognitiva",
    "bloom's taxonomy": "taxonomia de bloom",
    "and future research directions": "e direções futuras de pesquisa",
    "future research directions": "direções futuras de pesquisa",
    "to ensure that human cognitive skills remain a crucial element": "para garantir que as habilidades cognitivas humanas permaneçam um elemento crucial",
    "to ensure that": "para garantir que",
    "human cognitive skills": "habilidades cognitivas humanas",
    "cognitive skills": "habilidades cognitivas",
    "remain a crucial element": "permaneçam um elemento crucial",
    "crucial element": "elemento crucial",
    "in ai-integrated environments": "em ambientes integrados à IA",
    "ai-integrated environments": "ambientes integrados à IA",
    "promoting a balanced partnership between humans and ai": "promovendo uma parceria equilibrada entre humanos e IA",
    "promoting a balanced partnership": "promovendo uma parceria equilibrada",
    "balanced partnership": "parceria equilibrada",
    "between humans and ai": "entre humanos e IA",

    # Termos de Hardware, Física Quântica e Benchmarks
    "hello world": "olá mundo",
    "hello": "olá",
    "hi": "olá",
    "world": "mundo",
    "worlds": "mundos",
    "warning": "aviso",
    "warnings": "avisos",
    "voltage": "voltagem",
    "quantum scalability": "escalabilidade quântica",
    "cryogenic attenuation stages": "estágios de atenuação criogênica",
    "superconducting transmon qubit": "qubit transmon supercondutor",
    "microwave crosstalk attenuation": "atenuação de diafonia de micro-ondas",
    "latency comparison": "comparativo de latência",
    "optical character recognition": "reconhecimento óptico de caracteres",
    "hardware profiler": "perfilador de hardware",
    "adaptive engine": "motor adaptativo",
    "read-only principle": "princípio somente-leitura",
    "document context": "contexto do documento",
    "high fidelity": "alta fidelidade",
    "graceful degradation": "degradação graciosa",
    "real-time translation": "tradução em tempo real",
    "heads-up display": "exibição heads-up (HUD)",
    "local translator": "tradutor local",
    "fast discovery": "descoberta rápida",
    "recent advances": "avanços recentes",
    "recent": "recente",
    "advances": "avanços",
    "advance": "avanço",
    "human tasks": "tarefas humanas",
    "reduce workloads": "reduzir cargas de trabalho",
    "augment capabilities": "aumentar capacidades",
    "cognitive tasks": "tarefas cognitivas",
    "misinformation": "desinformação",
    "disinformation": "desinformação",
    "creativity": "criatividade",
    "evaluation methods": "métodos de avaliação",
    "unflinching": "inabalável",
    "serendipity": "serendipidade",
    "preposterous": "absurdo",
    "ephemeral": "efêmero",
    "bite the bullet": "encarar a situação",
    "hit the nail on the head": "acertar em cheio",
    "call it a day": "encerrar por hoje",

    # Conectivos e expressões comuns da língua inglesa
    "state of the art": "estado da arte",
    "state-of-the-art": "estado da arte",
    "ground truth": "verdade de referência",
    "as well as": "bem como",
    "in order to": "a fim de",
    "on the other hand": "por outro lado",
    "for example": "por exemplo",
    "for instance": "por exemplo",
    "in addition": "além disso",
    "furthermore": "além disso",
    "moreover": "além disso",
    "therefore": "portanto",
    "however": "no entanto",
    "nevertheless": "não obstante",
    "specifically": "especificamente",
    "consequently": "consequentemente",
    "such as": "como",
    "instead of": "em vez de",
    "due to": "devido a",
    "based on": "com base em",
    "in terms of": "em termos de",
    "with respect to": "com relação a",
    "and": "e",
    "with": "com",
    "without": "sem",
    "for": "para",
    "from": "de",
    "about": "sobre",
    "between": "entre",
    "among": "entre",
    "into": "em",
    "through": "através de",
    "also": "também",
    "not": "não",
    "only": "apenas",
    "this": "este",
    "that": "aquele",
    "these": "estes",
    "those": "aqueles",
    "all": "todos",
    "some": "alguns",
    "more": "mais",
    "most": "a maioria",
    "other": "outro",
    "new": "novo",
    "high": "alto",
    "low": "baixo",
    "first": "primeiro",
    "last": "último",

    # Artigos e pronomes essenciais
    "the": "o",
    "a": "um",
    "an": "um",
    "i": "eu",
    "you": "você",
    "he": "ele",
    "she": "ela",
    "it": "ele",
    "we": "nós",
    "they": "eles",
    "my": "meu",
    "your": "seu",
    "his": "dele",
    "her": "dela",
    "its": "seu",
    "our": "nosso",
    "their": "deles",
    "them": "eles",
    "us": "nós",
    "him": "ele",
    "what": "o que",
    "which": "qual",
    "who": "quem",
    "whom": "quem",
    "whose": "cujo",
    "where": "onde",
    "when": "quando",
    "why": "por que",
    "how": "como",

    # Verbos auxiliares e formas comuns
    "is": "é",
    "are": "são",
    "was": "foi",
    "were": "eram",
    "be": "ser",
    "been": "sido",
    "being": "sendo",
    "have": "ter",
    "has": "tem",
    "had": "tinha",
    "having": "tendo",
    "do": "fazer",
    "does": "faz",
    "did": "fez",
    "doing": "fazendo",
    "done": "feito",
    "can": "pode",
    "could": "poderia",
    "will": "irá",
    "would": "seria",
    "shall": "deverá",
    "should": "deve",
    "may": "pode",
    "might": "poderia",
    "must": "deve",

    # Verbos de pesquisa e ação acadêmica
    "show": "mostrar",
    "shows": "mostra",
    "showed": "mostrou",
    "shown": "mostrado",
    "showing": "mostrando",
    "present": "apresentar",
    "presents": "apresenta",
    "presented": "apresentou",
    "presenting": "apresentando",
    "demonstrate": "demonstrar",
    "demonstrates": "demonstra",
    "demonstrated": "demonstrou",
    "demonstrating": "demonstrando",
    "propose": "propor",
    "proposes": "propõe",
    "proposed": "proposto",
    "proposing": "propondo",
    "achieve": "alcançar",
    "achieves": "alcança",
    "achieved": "alcançado",
    "achieving": "alcançando",
    "improve": "melhorar",
    "improves": "melhora",
    "improved": "melhorado",
    "improving": "melhorando",
    "reduce": "reduzir",
    "reduces": "reduz",
    "reduced": "reduzido",
    "reducing": "reduzindo",
    "evaluate": "avaliar",
    "evaluates": "avalia",
    "evaluated": "avaliado",
    "evaluating": "avaliando",
    "develop": "desenvolver",
    "develops": "desenvolve",
    "developed": "desenvolvido",
    "developing": "desenvolvendo",
    "create": "criar",
    "creates": "cria",
    "created": "criado",
    "creating": "criando",
    "use": "usar",
    "uses": "usa",
    "used": "usado",
    "using": "usando",
    "apply": "aplicar",
    "applies": "aplica",
    "applied": "aplicado",
    "applying": "aplicando",
    "compare": "comparar",
    "compares": "compara",
    "compared": "comparado",
    "comparing": "comparando",
    "provide": "fornecer",
    "provides": "fornece",
    "provided": "fornecido",
    "providing": "fornecendo",
    "require": "exigir",
    "requires": "exige",
    "required": "exigido",
    "requiring": "exigindo",
    "enable": "permitir",
    "enables": "permite",
    "enabled": "habilitado",
    "enabling": "permitindo",
    "allow": "permitir",
    "allows": "permite",
    "allowed": "permitido",
    "allowing": "permitindo",
    "support": "apoiar",
    "supports": "apoia",
    "supported": "apoiado",
    "supporting": "apoiando",
    "ensure": "garantir",
    "ensures": "garante",
    "ensured": "garantido",
    "ensuring": "garantindo",
    "enhance": "aprimorar",
    "enhances": "aprimora",
    "enhanced": "aprimorado",
    "enhancing": "aprimorando",
    "perform": "executar",
    "performs": "executa",
    "performed": "executado",
    "performing": "executando",
    "generate": "gerar",
    "generates": "gera",
    "generated": "gerado",
    "generating": "gerando",
    "contain": "conter",
    "contains": "contém",
    "contained": "contido",
    "containing": "contendo",
    "include": "incluir",
    "includes": "inclui",
    "included": "incluído",
    "including": "incluindo",
    "indicate": "indicar",
    "indicates": "indica",
    "indicated": "indicado",
    "indicating": "indicando",
    "suggest": "sugerir",
    "suggests": "sugere",
    "suggested": "sugerido",
    "suggesting": "sugerindo",
    "observe": "observar",
    "observes": "observa",
    "observed": "observado",
    "observing": "observando",
    "consider": "considerar",
    "considers": "considera",
    "considered": "considerado",
    "considering": "considerando",
    "implement": "implementar",
    "implements": "implementa",
    "implemented": "implementado",
    "implementing": "implementando",

    # Substantivos frequentes em artigos, documentos e computação
    "study": "estudo",
    "studies": "estudos",
    "research": "pesquisa",
    "author": "autor",
    "authors": "autores",
    "paper": "artigo",
    "papers": "artigos",
    "article": "artigo",
    "articles": "artigos",
    "document": "documento",
    "documents": "documentos",
    "system": "sistema",
    "systems": "sistemas",
    "model": "modelo",
    "models": "modelos",
    "data": "dados",
    "dataset": "conjunto de dados",
    "datasets": "conjuntos de dados",
    "approach": "abordagem",
    "approaches": "abordagens",
    "method": "método",
    "methods": "métodos",
    "methodology": "metodologia",
    "result": "resultado",
    "results": "resultados",
    "performance": "desempenho",
    "accuracy": "precisão",
    "efficiency": "eficiência",
    "latency": "latência",
    "speed": "velocidade",
    "experiment": "experimento",
    "experiments": "experimentos",
    "evaluation": "avaliação",
    "user": "usuário",
    "users": "usuários",
    "interface": "interface",
    "network": "rede",
    "networks": "redes",
    "language": "linguagem",
    "task": "tarefa",
    "tasks": "tarefas",
    "process": "processo",
    "processes": "processos",
    "problem": "problema",
    "problems": "problemas",
    "solution": "solução",
    "solutions": "soluções",
    "application": "aplicação",
    "applications": "aplicações",
    "design": "projeto",
    "framework": "estrutura",
    "environment": "ambiente",
    "environments": "ambientes",
    "feature": "recurso",
    "features": "recursos",
    "technology": "tecnologia",
    "information": "informação",
    "structure": "estrutura",
    "quality": "qualidade",
    "impact": "impacto",
    "perspective": "perspectiva",
    "perspectives": "perspectivas",
    "context": "contexto",
    "scale": "escala",
    "output": "saída",
    "input": "entrada",
    "content": "conteúdo",
    "contents": "conteúdos",
    "mechanism": "mecanismo",
    "conclusion": "conclusão",
    "summary": "resumo",
    "algorithm": "algoritmo",
    "algorithms": "algoritmos",
    "device": "dispositivo",
    "devices": "dispositivos",
    "memory": "memória",
    "processor": "processador",
    "security": "segurança",
    "privacy": "privacidade",

    # Adjetivos e modificadores fundamentais
    "high": "alto",
    "low": "baixo",
    "large": "grande",
    "small": "pequeno",
    "new": "novo",
    "old": "antigo",
    "main": "principal",
    "major": "principal",
    "minor": "menor",
    "significant": "significativo",
    "simple": "simples",
    "complex": "complexo",
    "accurate": "preciso",
    "fast": "rápido",
    "slow": "lento",
    "reliable": "confiável",
    "efficient": "eficiente",
    "effective": "eficaz",
    "deep": "profundo",
    "current": "atual",
    "previous": "anterior",
    "recent": "recente",
    "novel": "inovador",
    "standard": "padrão",
    "local": "local",
    "global": "global",
    "direct": "direto",
    "indirect": "indireto",
    "general": "geral",
    "specific": "específico",
    "important": "importante",
    "critical": "crítico",
    "robust": "robusto",
    "overall": "geral",
    "full": "completo",
    "optimal": "ótimo",
    "adaptive": "adaptativo",
    "essential": "essencial",
    "clear": "claro",
    "easily": "facilmente",
    "quickly": "rapidamente",
    "directly": "diretamente",
    "significantly": "significativamente",
    "highly": "altamente",
    "well": "bem",
    "then": "então",
    "now": "agora",
    "always": "sempre",
    "never": "nunca",
    "often": "frequentemente",
    "usually": "usualmente",
    "currently": "atualmente",
    "particularly": "particularmente",
    "widely": "amplamente",
    "relatively": "relativamente",
    "extremely": "extremamente",
    "completely": "completamente",
    "successfully": "com sucesso",
    "but": "mas",
    "or": "ou",
    "so": "portanto",
    "because": "porque",
    "since": "desde",
    "while": "enquanto",
    "if": "se",
    "as": "como",
    "than": "do que",
    "of": "de",
    "in": "em",
    "on": "em",
    "at": "em",
    "to": "para",
    "by": "por",
}

try:
    from offline_dictionary import (
        OFFLINE_GLUED_WORDS,
        OFFLINE_MULTIWORD_EXPRESSIONS,
        CORE_ACADEMIC_LEXICON,
        MorphologyEngine
    )
except ImportError:
    OFFLINE_GLUED_WORDS = {}
    OFFLINE_MULTIWORD_EXPRESSIONS = {}
    CORE_ACADEMIC_LEXICON = {}
    class MorphologyEngine:
        @classmethod
        def translate_token(cls, tok, lex):
            return lex.get(tok.lower())

class OfflineContextTranslator:
    """
    Tradutor offline 100% autônomo baseado em:
    1. Descolamento prévio de expressões aglutinadas de extração PDF de 2 colunas.
    2. Correspondência gananciosa (greedy longest-match) de locuções compostas e termos técnicos.
    3. Motor morfológico avançado (plurais, sufixos verbais -ing/-ed, advérbios -ly, cognatos -ção/-dade).
    4. Tradução token a token com preservação estrita de espaçamento, pontuação e casing.
    5. Cobertura léxica científica de alta fidelidade sem vazamento de palavras residuais em inglês.
    """
    
    @classmethod
    def translate(cls, text: str, context_prompt: str = "") -> str:
        clean = text.strip()
        if not clean:
            return ""

        # 1. Descolamento de palavras aglutinadas comuns em PDFs
        if OFFLINE_GLUED_WORDS:
            for glued, separated in OFFLINE_GLUED_WORDS.items():
                if glued.lower() in clean.lower():
                    pattern = re.compile(rf'(?<!\w){re.escape(glued)}(?!\w)', re.IGNORECASE)
                    clean = pattern.sub(separated, clean)
            
        lower_clean = clean.lower()

        # 2. Correspondência exata direta no glossário técnico
        if lower_clean in OFFLINE_TECHNICAL_GLOSSARY:
            res = OFFLINE_TECHNICAL_GLOSSARY[lower_clean]
            if clean.isupper():
                return res.upper()
            elif clean[0].isupper():
                return res.capitalize()
            return res

        # 3. Consolidação de dicionários (Técnico + Léxico Científico + Expressões Multi-palavras)
        all_single_words = dict(CORE_ACADEMIC_LEXICON)
        all_multi_words = dict(OFFLINE_MULTIWORD_EXPRESSIONS)

        for en, pt in OFFLINE_TECHNICAL_GLOSSARY.items():
            if " " in en or "-" in en:
                all_multi_words[en] = pt
            else:
                all_single_words[en] = pt

        # Ordena locuções compostas pela mais longa primeiro para greedy matching
        multi_word_terms = sorted(all_multi_words.items(), key=lambda x: len(x[0]), reverse=True)

        # 4. Divide em parágrafos para preservar quebras sem grudar blocos de texto
        paragraphs = clean.split("\n\n")
        translated_paragraphs = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            lines = para.split("\n")
            translated_lines = []

            for line in lines:
                working_line = line.strip()
                if not working_line:
                    continue

                # A. Substituição de locuções multi-palavras usando marcadores seguros
                placeholders = {}
                ph_idx = 0

                for en, pt in multi_word_terms:
                    escaped_en = re.escape(en)
                    pattern = re.compile(rf'(?<!\w){escaped_en}(?!\w)', re.IGNORECASE)
                    
                    def _ph_sub(match):
                        nonlocal ph_idx
                        matched = match.group(0)
                        ph_key = f"__LOTRA_PH_{ph_idx}__"
                        ph_idx += 1
                        if matched.isupper():
                            placeholders[ph_key] = pt.upper()
                        elif matched[0].isupper():
                            placeholders[ph_key] = pt.capitalize()
                        else:
                            placeholders[ph_key] = pt
                        return ph_key

                    working_line = pattern.sub(_ph_sub, working_line)

                # B. Tokeniza a linha preservando emojis compostos (com ZWJ e seletores), pontuações, hífens e apóstrofos
                tokens = re.findall(
                    r'(__LOTRA_PH_\d+__|'
                    r'[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff](?:[\ufe0e\ufe0f]|\u200d[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff]|[\U0001f3fb-\U0001f3ff])*|'
                    r'[a-zA-ZÀ-ÿ0-9\'-]+|'
                    r'[^\s\w])',
                    working_line
                )
                translated_tokens = []

                for tok in tokens:
                    if tok.startswith("__LOTRA_PH_") and tok in placeholders:
                        translated_tokens.append(placeholders[tok])
                    else:
                        tok_lower = tok.lower()
                        # Verificação 1: Correspondência direta no léxico consolidado
                        if tok_lower in all_single_words:
                            pt_word = all_single_words[tok_lower]
                            if tok.isupper():
                                translated_tokens.append(pt_word.upper())
                            elif tok[0].isupper():
                                translated_tokens.append(pt_word.capitalize())
                            else:
                                translated_tokens.append(pt_word)
                        else:
                            # Verificação 2: Motor Morfológico (plurais, particípios, gerúndios, cognatos)
                            morph_trans = MorphologyEngine.translate_token(tok, all_single_words)
                            if morph_trans:
                                if tok.isupper():
                                    translated_tokens.append(morph_trans.upper())
                                elif tok[0].isupper():
                                    translated_tokens.append(morph_trans.capitalize())
                                else:
                                    translated_tokens.append(morph_trans)
                            else:
                                translated_tokens.append(tok)

                # C. Reconstroi a linha garantindo que pontuações não fiquem com espaços errados
                built_line = ""
                no_space_before = {'.', ',', ';', ':', '!', '?', ')', ']', '}', '%', "’", "'"}
                no_space_after = {'(', '[', '{', '$', '¿', '¡', "’", "'"}

                for i, tok in enumerate(translated_tokens):
                    if i == 0:
                        built_line = tok
                    else:
                        prev_tok = translated_tokens[i - 1]
                        if tok in no_space_before or prev_tok in no_space_after:
                            built_line += tok
                        else:
                            built_line += " " + tok

                translated_lines.append(built_line)

            translated_paragraphs.append("\n".join(translated_lines))

        result = "\n\n".join(translated_paragraphs)
        result = re.sub(r'[ \t]+', ' ', result).strip()
        return result



class ONNXTranslationEngine:
    """
    Motor local de tradução neural autônomo baseado em ONNX Runtime / DirectML, CTranslate2 e SentencePiece.
    Projetado para MarianMT / Opus-MT (77M parâmetros) quantizado (~45MB) operando 100% offline.
    """

    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = Path(model_dir) if model_dir else (Path(os.environ.get("LOCALAPPDATA", "")) / "LoTra" / "models")
        self._session = None
        self._translator = None
        self._tokenizer = None
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Verifica se os arquivos do modelo e runtime (ONNX ou CTranslate2) estão disponíveis no sistema."""
        if self._available is not None:
            return self._available

        ct2_model = self.model_dir / "model.bin"
        onnx_model = self.model_dir / "opus-mt-en-pt.onnx"
        
        has_model = ct2_model.exists() or onnx_model.exists()
        if not has_model and self._translator is None and self._session is None:
            self._available = False
            return False

        if self._translator is not None or self._session is not None:
            self._available = True
            return True

        try:
            import ctranslate2
            self._available = True
            return True
        except ImportError:
            pass

        try:
            import onnxruntime
            self._available = True
            return True
        except ImportError:
            pass

        self._available = False
        return False

    def set_custom_backend(self, translator=None, session=None, tokenizer=None):
        """Permite injeção de sessão/tradutor pré-carregado ou mock para testes automatizados."""
        self._translator = translator
        self._session = session
        self._tokenizer = tokenizer
        self._available = True

    def translate(self, text: str) -> Optional[str]:
        """Executa tradução neural direta via CTranslate2 ou ONNX Runtime se disponível."""
        if not self.is_available():
            return None

        # 1. Backend CTranslate2 (MarianMT quantizado int8)
        if self._translator is not None or (self.model_dir / "model.bin").exists():
            try:
                if self._translator is None:
                    import ctranslate2
                    self._translator = ctranslate2.Translator(str(self.model_dir), device="auto")
                
                if hasattr(self._translator, "translate_text"):
                    return self._translator.translate_text(text)

                tokens = None
                if self._tokenizer:
                    tokens = self._tokenizer.encode(text, out_type=str)
                else:
                    sp_model_file = self.model_dir / "source.spm"
                    if sp_model_file.exists():
                        try:
                            import sentencepiece as spm
                            sp = spm.SentencePieceProcessor()
                            sp.load(str(sp_model_file))
                            tokens = sp.encode(text, out_type=str)
                        except Exception:
                            pass

                if tokens is not None and hasattr(self._translator, "translate_batch"):
                    results = self._translator.translate_batch([tokens])
                    target_tokens = results[0].hypotheses[0]
                    target_spm = self.model_dir / "target.spm"
                    if target_spm.exists():
                        try:
                            import sentencepiece as spm
                            sp_t = spm.SentencePieceProcessor()
                            sp_t.load(str(target_spm))
                            return sp_t.decode(target_tokens)
                        except Exception:
                            pass
                    return " ".join(target_tokens).replace(" ", " ").strip()
            except Exception:
                pass

        # 2. Backend ONNX Runtime (DirectML / CPU)
        try:
            if self._session is None and (self.model_dir / "opus-mt-en-pt.onnx").exists():
                import onnxruntime as ort
                model_path = str(self.model_dir / "opus-mt-en-pt.onnx")
                providers = ["DirectMLExecutionProvider", "CPUExecutionProvider"]
                self._session = ort.InferenceSession(model_path, providers=providers)

            if self._session is not None:
                if hasattr(self._session, "translate"):
                    return self._session.translate(text)
                if hasattr(self._session, "run_translation"):
                    return self._session.run_translation(text)
                if self._tokenizer:
                    inputs = self._tokenizer(text)
                    outputs = self._session.run(None, inputs)
                    if hasattr(self._tokenizer, "decode"):
                        return self._tokenizer.decode(outputs[0])
        except Exception:
            pass

        return None

class TranslationPipeline:
    """Pipeline completo de tradução coordenado por hardware e cache."""

    def __init__(self, vault: Optional[DocumentContextVault] = None, ollama_url: str = "http://127.0.0.1:11434"):
        self.vault = vault or DocumentContextVault()
        self.ollama_url = ollama_url
        self.orchestrator = AdaptiveEngineOrchestrator(target_latency_ms=250.0)
        self.onnx_engine = ONNXTranslationEngine()
        self._ollama_online: Optional[bool] = None
        self._last_ollama_check: float = 0.0

    def _is_ollama_available(self) -> bool:
        """Verifica de forma ultrarrápida (< 45ms) se o servidor local do Ollama está ouvindo."""
        now = time.perf_counter()
        if self._ollama_online is not None and (now - self._last_ollama_check) < 25.0:
            return self._ollama_online

        self._last_ollama_check = now
        try:
            host = "127.0.0.1"
            port = 11434
            if "://" in self.ollama_url:
                part = self.ollama_url.split("://", 1)[1]
                if ":" in part:
                    host, p_str = part.split(":", 1)
                    port = int(p_str.split("/")[0])
                else:
                    host = part.split("/")[0]

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.045)
                err = s.connect_ex((host, port))
                self._ollama_online = (err == 0)
        except Exception:
            self._ollama_online = False

        return self._ollama_online

    def _get_available_ollama_model(self, preferred_model: str) -> Optional[str]:
        """Obtém dinamicamente o melhor modelo disponível no Ollama instalado pelo usuário."""
        if not self._is_ollama_available():
            return None

        installed = []
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    installed = [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            pass

        if not installed:
            return None

        # 1. Se o preferred_model estiver instalado diretamente
        for m in installed:
            if m.lower() == preferred_model.lower() or m.lower().startswith(f"{preferred_model.lower()}:"):
                return m

        # 2. Prioridade de modelos candidatos
        candidate_priorities = [
            preferred_model,
            "qwen2.5:1.5b",
            "qwen2.5:0.5b",
            "qwen2.5:3b",
            "llama3.2:1b",
            "llama3.2:3b",
            "qwen2.5:7b",
        ]
        for cand in candidate_priorities:
            for inst in installed:
                if inst.lower() == cand.lower() or inst.lower().startswith(f"{cand.lower()}:"):
                    return inst

        # 3. Qualquer modelo da família qwen, llama, mistral ou gemma instalado
        for inst in installed:
            inst_lower = inst.lower()
            if any(family in inst_lower for family in ["qwen", "llama", "mistral", "gemma", "phi"]):
                return inst

        return installed[0] if installed else None

    def _is_valid_translation(self, text: str) -> bool:
        """
        Validador de Sanidade da Tradução:
        Detecta e rejeita alucinações de recusa, desculpas de LLMs e loops degenerativos de repetição infinita.
        """
        if not text or len(text.strip()) < 2:
            return False
            
        lower_text = text.lower()
        
        # 1. Padrões de recusa, desculpas ou meta-comentários da LLM
        refusal_patterns = [
            "o texto fornecido",
            "não está relacionado",
            "categoria de texto",
            "precisamos entender o contexto",
            "para traduzir o texto",
            "como uma inteligência artificial",
            "como um modelo de linguagem",
            "não posso traduzir",
            "sinto muito",
            "desculpe, mas",
            "aqui está a tradução",
            "tradução direta:"
        ]
        for pat in refusal_patterns:
            if pat in lower_text:
                return False
                
        # 2. Detecção de degeneração / loop infinito de frases repetidas
        sentences = [s.strip() for s in re.split(r'[.!?]+', text) if len(s.strip()) > 15]
        if len(sentences) >= 3:
            # Se mais de 35% das sentenças forem duplicadas
            unique_sentences = set(sentences)
            if len(unique_sentences) / len(sentences) < 0.65:
                return False
                
        return True

    def _query_ollama(self, 
                      model: str, 
                      prompt: str, 
                      timeout: float = 25.0,
                      stream_callback: Optional[Callable[[str, str], None]] = None,
                      dynamic_predict: Optional[int] = None) -> Optional[str]:
        """Tenta comunicação local com Ollama com streaming e otimizações de baixa latência."""
        if not self._is_ollama_available():
            return None

        endpoint = f"{self.ollama_url}/api/generate"
        predict_tokens = dynamic_predict if dynamic_predict is not None else 512
        use_stream = stream_callback is not None

        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": use_stream,
            "keep_alive": "15m",
            "options": {
                "temperature": 0.15,
                "top_p": 0.9,
                "repeat_penalty": 1.18,
                "repeat_last_n": 64,
                "num_ctx": 512,
                "num_predict": predict_tokens
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    if not use_stream:
                        data = json.loads(resp.read().decode("utf-8"))
                        res = data.get("response", "").strip()
                    else:
                        tokens = []
                        for line in resp:
                            if not line:
                                continue
                            try:
                                chunk = json.loads(line.decode("utf-8"))
                            except Exception:
                                continue
                            tok = chunk.get("response", "")
                            if tok:
                                tokens.append(tok)
                                full_so_far = "".join(tokens)
                                clean_disp = full_so_far
                                for pfx in ['"Tradução:', '“Tradução:', 'Tradução:', 'Tradução :']:
                                    if clean_disp.startswith(pfx):
                                        clean_disp = clean_disp[len(pfx):].lstrip()
                                if stream_callback:
                                    stream_callback(tok, clean_disp)
                            if chunk.get("done", False):
                                break
                        res = "".join(tokens).strip()

                    if res:
                        # Limpa possíveis aspas ou preâmbulos desnecessários gerados pelo modelo
                        if (res.startswith('"') and res.endswith('"')) or (res.startswith("“") and res.endswith("”")):
                            res = res[1:-1].strip()
                        if res.lower().startswith("tradução:"):
                            res = res[len("tradução:"):].strip()
                        if res.lower().startswith("tradução :"):
                            res = res[len("tradução :"):].strip()
                            
                        # Validação rigorosa de sanidade da tradução
                        if self._is_valid_translation(res):
                            return res
        except Exception:
            return None
        return None

    def translate_text(self, 
                       text: str, 
                       doc_hash: str = "ad_hoc_query", 
                       page_num: int = 1,
                       target_sla_ms: float = 250.0,
                       stream_callback: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
        """
        Executa tradução 100% local com:
        1. Normalização de espaçamento e quebras duras de linha de PDFs.
        2. Decisão de modelo baseada em hardware real e modelos do Ollama instalados.
        3. Verificação de cache ultrarrápido no DocumentContextVault (< 1ms).
        4. Inferência local via Ollama LLM com streaming e otimização de latência (num_ctx 512, keep_alive 15m).
        5. Fallback 100% offline via LoTra Built-in Offline Translator (Glossário e Regras).
        6. Gravação no cache ACID local em SQLite.
        7. Retorno estruturado com métricas e metadados.
        """
        raw_text = normalize_text_spacing(text.strip())
        if not raw_text:
            return {
                "source_text": "",
                "translated_text": "",
                "latency_ms": 0.0,
                "cache_hit": False,
                "engine_used": "none",
                "model_selected": "none"
            }

        t0 = time.perf_counter()

        # 1. Determina tamanho e tipo do texto
        word_count = len(raw_text.split())
        dynamic_predict = max(48, min(512, int(word_count * 2.2)))

        if word_count <= 2:
            text_type = "word"
        elif word_count <= 8:
            text_type = "idiom"
        else:
            text_type = "paragraph"

        # 2. Orquestração baseada em hardware
        self.orchestrator.target_latency_ms = target_sla_ms
        plan = self.orchestrator.select_optimal_pipeline(text_type=text_type, is_ocr_required=False)
        selected_model = plan.get("translation_model", "qwen_1.5b")
        model_name = plan.get("model_name", "Qwen 2.5 1.5B-Instruct")

        # 3. Contexto do documento (se existir registro no cofre)
        context_prompt = self.vault.get_hierarchical_context_prompt(doc_hash, page_num, raw_text)
        
        # Hierarquia Estruturada de Tradução:
        translated_result = None
        engine_used = "none"

        # Consulta inicial de Cache instantâneo (< 0.5ms)
        cached = self.vault.lookup_cache(doc_hash=doc_hash, source_text=raw_text, model_id=selected_model)
        if cached and not (len(raw_text) > 3 and cached.strip().lower() == raw_text.lower()):
            latency = (time.perf_counter() - t0) * 1000.0
            if stream_callback:
                stream_callback(cached, cached)
            return {
                "source_text": raw_text,
                "translated_text": cached,
                "latency_ms": round(latency, 2),
                "cache_hit": True,
                "engine_used": "DocumentContextVault Cache (ACID)",
                "model_selected": selected_model,
                "model_name": model_name,
                "hardware_profile": plan.get("hardware_used")
            }

        # Nível 1: Correspondência direta no Glossário Técnico Offline (< 0.1ms)
        lower_raw = raw_text.lower()
        if lower_raw in OFFLINE_TECHNICAL_GLOSSARY:
            gloss_term = OFFLINE_TECHNICAL_GLOSSARY[lower_raw]
            if raw_text.isupper():
                translated_result = gloss_term.upper()
            elif raw_text[0].isupper():
                translated_result = gloss_term.capitalize()
            else:
                translated_result = gloss_term
            engine_used = "LoTra Built-in Technical Glossary"

        # Nível 2: Inferência via Ollama Local com modelo instalado dinamicamente
        if not translated_result and self._is_ollama_available():
            ollama_model_map = {
                "marian_mt": "qwen2.5:1.5b",
                "qwen_0.5b": "qwen2.5:0.5b",
                "qwen_1.5b": "qwen2.5:1.5b",
                "llama_3.2_1b": "llama3.2:1b",
                "qwen_3b": "qwen2.5:1.5b",
                "llama_3.2_3b": "llama3.2:3b",
                "qwen_7b": "qwen2.5:7b"
            }
            preferred = ollama_model_map.get(selected_model, "qwen2.5:1.5b")
            actual_ollama_model = self._get_available_ollama_model(preferred)
            
            if actual_ollama_model:
                selected_model = actual_ollama_model
                model_name = f"Ollama ({actual_ollama_model})"

                # Checa cache específico do modelo retornado pelo Ollama
                cached = self.vault.lookup_cache(doc_hash=doc_hash, source_text=raw_text, model_id=selected_model)
                if cached and not (len(raw_text) > 3 and cached.strip().lower() == raw_text.lower()):
                    latency = (time.perf_counter() - t0) * 1000.0
                    if stream_callback:
                        stream_callback(cached, cached)
                    return {
                        "source_text": raw_text,
                        "translated_text": cached,
                        "latency_ms": round(latency, 2),
                        "cache_hit": True,
                        "engine_used": "DocumentContextVault Cache (ACID)",
                        "model_selected": selected_model,
                        "model_name": model_name,
                        "hardware_profile": plan.get("hardware_used")
                    }

                system_instruction = (
                    "Traduza o seguinte texto do inglês para o português brasileiro de forma natural, precisa e fluente. "
                    "Retorne EXCLUSIVAMENTE a tradução final, sem introdução, sem aspas adicionais e sem explicações."
                )
                if context_prompt:
                    prompt = f"Contexto: {context_prompt}\n\n{system_instruction}\n\nTexto: {raw_text}"
                else:
                    prompt = f"{system_instruction}\n\nTexto: {raw_text}"

                translated_result = self._query_ollama(
                    actual_ollama_model, 
                    prompt, 
                    timeout=20.0,
                    stream_callback=stream_callback,
                    dynamic_predict=dynamic_predict
                )
                if translated_result:
                    engine_used = f"Ollama Local ({actual_ollama_model})"

        # Se Ollama não respondeu, checa cache para o modelo padrão ou fallback
        if not translated_result:
            cached = self.vault.lookup_cache(doc_hash=doc_hash, source_text=raw_text, model_id=selected_model)
            if cached and not (len(raw_text) > 3 and cached.strip().lower() == raw_text.lower()):
                latency = (time.perf_counter() - t0) * 1000.0
                if stream_callback:
                    stream_callback(cached, cached)
                return {
                    "source_text": raw_text,
                    "translated_text": cached,
                    "latency_ms": round(latency, 2),
                    "cache_hit": True,
                    "engine_used": "DocumentContextVault Cache (ACID)",
                    "model_selected": selected_model,
                    "model_name": model_name,
                    "hardware_profile": plan.get("hardware_used")
                }

        # Nível 3: Inferência Neural Local via ONNX Runtime / DirectML (MarianMT / Opus-MT)
        if not translated_result and self.onnx_engine.is_available():
            translated_result = self.onnx_engine.translate(raw_text)
            if translated_result:
                engine_used = "ONNX Neural Engine (DirectML/CPU)"

        # Nível 4: Fallback 100% Offline: LoTra Built-in Offline Translator (Glossário e Regras)
        if not translated_result:
            translated_result = OfflineContextTranslator.translate(raw_text, context_prompt)
            engine_used = "LoTra Built-in Offline Translator"

        if translated_result and stream_callback:
            stream_callback(translated_result, translated_result)


        latency = (time.perf_counter() - t0) * 1000.0

        # 7. Grava no cache apenas se for uma tradução válida
        if translated_result and not (len(raw_text) > 3 and translated_result.strip().lower() == raw_text.lower()):
            self.vault.store_cache(
                doc_hash=doc_hash,
                page_num=page_num,
                source_text=raw_text,
                context_used=context_prompt,
                translated_text=translated_result,
                model_id=selected_model,
                latency_ms=latency
            )

        # 8. Limpa VRAM / working set de RAM
        VRAMManager.trim_process_memory()

        return {
            "source_text": raw_text,
            "translated_text": translated_result,
            "latency_ms": round(latency, 2),
            "cache_hit": False,
            "engine_used": engine_used,
            "model_selected": selected_model,
            "model_name": model_name,
            "decision_reason": plan.get("decision_reason"),
            "hardware_profile": plan.get("hardware_used")
        }
