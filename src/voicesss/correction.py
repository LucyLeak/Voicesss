from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping


DEFAULT_COMPLEMENTS: dict[str, str] = {
    "obrigado": "obrigada",
    "bem-vindo": "bem-vinda",
    "bem vindo": "bem vinda",
    "cansado": "cansada",
    "exausto": "exausta",
    "esgotado": "esgotada",
    "sozinho": "sozinha",
    "solitário": "solitária",
    "solitario": "solitária",
    "animado": "animada",
    "preocupado": "preocupada",
    "ocupado": "ocupada",
    "atrasado": "atrasada",
    "confuso": "confusa",
    "perdido": "perdida",
    "pronto": "pronta",
    "preparado": "preparada",
    "nervoso": "nervosa",
    "ansioso": "ansiosa",
    "tranquilo": "tranquila",
    "chateado": "chateada",
    "assustado": "assustada",
    "acostumado": "acostumada",
    "envolvido": "envolvida",
    "incluído": "incluída",
    "incluido": "incluída",
    "excluído": "excluída",
    "excluido": "excluída",
    "inscrito": "inscrita",
    "aprovado": "aprovada",
    "reprovado": "reprovada",
    "contratado": "contratada",
    "demitido": "demitida",
    "chamado": "chamada",
    "convidado": "convidada",
    "formado": "formada",
    "graduado": "graduada",
    "dedicado": "dedicada",
    "focado": "focada",
    "distraído": "distraída",
    "distraido": "distraída",
    "satisfeito": "satisfeita",
    "surpreso": "surpresa",
    "decepcionado": "decepcionada",
    "decepsionado": "decepcionada",
    "apto": "apta",
}

DEFAULT_SELF_PRONOUNS: dict[str, str] = {
    "mesmo": "mesma",
    "próprio": "própria",
    "proprio": "própria",
}

DEFAULT_NOUNS: dict[str, str] = {
    "aluno": "aluna",
    "professor": "professora",
    "médico": "médica",
    "medico": "médica",
    "engenheiro": "engenheira",
    "programador": "programadora",
    "desenvolvedor": "desenvolvedora",
    "advogado": "advogada",
    "psicólogo": "psicóloga",
    "psicologo": "psicóloga",
    "amigo": "amiga",
    "garoto": "garota",
    "menino": "menina",
    "filho": "filha",
    "irmão": "irmã",
    "irmao": "irmã",
    "namorado": "namorada",
    "candidato": "candidata",
    "autor": "autora",
    "ator": "atriz",
    "cantor": "cantora",
    "diretor": "diretora",
    "coordenador": "coordenadora",
    "gestor": "gestora",
    "cliente": "cliente",
    "usuário": "usuária",
    "usuario": "usuária",
}

SELF_COMPLEMENT_TRIGGERS = (
    r"(?:eu\s+)?(?:sou|estou|tô|to|fui|era|estava|tava|fiquei|fico|ando|continuo)",
    r"(?:eu\s+)?(?:me\s+sinto|me\s+senti|sinto-me|senti-me)",
    r"(?:isso\s+)?me\s+(?:deixou|deixaram|deixam|deixa|deixava|tornou|tornaram|tornam|torna|fez|fizeram|fazem|faz|manteve|mantiveram|mantêm|mantem)",
)

SELF_NOUN_TRIGGERS = (
    r"(?:eu\s+)?(?:sou|fui|era)",
    r"(?:eu\s+)?(?:me\s+considero|considero-me)",
)


def _preserve_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _word_or_phrase_pattern(words: Mapping[str, str]) -> str:
    escaped = sorted((re.escape(word) for word in words), key=len, reverse=True)
    return r"(?:" + "|".join(escaped) + r")"


@dataclass(slots=True)
class SelfReferenceFeminizer:
    """Normaliza termos masculinos que se referem a quem esta falando."""

    complements: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_COMPLEMENTS))
    self_pronouns: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_SELF_PRONOUNS))
    nouns: Mapping[str, str] = field(default_factory=lambda: dict(DEFAULT_NOUNS))
    max_words_after_trigger: int = 4

    @classmethod
    def from_json(cls, path: str | Path | None = None) -> "SelfReferenceFeminizer":
        if path is None:
            return cls()

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        complements = dict(DEFAULT_COMPLEMENTS)
        self_pronouns = dict(DEFAULT_SELF_PRONOUNS)
        nouns = dict(DEFAULT_NOUNS)
        complements.update({k.lower(): v for k, v in data.get("complements", {}).items()})
        self_pronouns.update({k.lower(): v for k, v in data.get("self_pronouns", {}).items()})
        nouns.update({k.lower(): v for k, v in data.get("nouns", {}).items()})
        return cls(complements=complements, self_pronouns=self_pronouns, nouns=nouns)

    def normalize(self, text: str) -> str:
        normalized = self._normalize_direct_self_pronouns(text)
        normalized = self._normalize_standalone_thanks(normalized)
        normalized = self._normalize_triggered_complements(normalized)
        normalized = self._normalize_triggered_nouns(normalized)
        return normalized

    def _replacement_for(self, original: str, mapping: Mapping[str, str]) -> str:
        return _preserve_case(original, mapping[original.lower()])

    def _normalize_direct_self_pronouns(self, text: str) -> str:
        pattern = re.compile(
            r"\b(?P<prefix>eu|mim|comigo|me)\s+(?P<word>mesmo|próprio|proprio)\b",
            flags=re.IGNORECASE,
        )

        def repl(match: re.Match[str]) -> str:
            word = match.group("word")
            return f"{match.group('prefix')} {self._replacement_for(word, self.self_pronouns)}"

        return pattern.sub(repl, text)

    def _normalize_standalone_thanks(self, text: str) -> str:
        pattern = re.compile(
            r"\b(?P<prefix>muito\s+)?(?P<word>obrigado)\b",
            flags=re.IGNORECASE,
        )

        def repl(match: re.Match[str]) -> str:
            prefix = match.group("prefix") or ""
            word = match.group("word")
            return f"{prefix}{self._replacement_for(word, self.complements)}"

        return pattern.sub(repl, text)

    def _normalize_triggered_complements(self, text: str) -> str:
        if not self.complements:
            return text

        terms = _word_or_phrase_pattern(self.complements)
        gap = rf"(?:\s+(?!{terms}\b)[^\s,.!?;:]+){{0,{self.max_words_after_trigger}}}\s+"
        trigger = r"(?:" + "|".join(SELF_COMPLEMENT_TRIGGERS) + r")"
        pattern = re.compile(
            rf"\b(?P<prefix>{trigger}{gap})(?P<word>{terms})\b",
            flags=re.IGNORECASE,
        )

        def repl(match: re.Match[str]) -> str:
            word = match.group("word")
            return f"{match.group('prefix')}{self._replacement_for(word, self.complements)}"

        return pattern.sub(repl, text)

    def _normalize_triggered_nouns(self, text: str) -> str:
        if not self.nouns:
            return text

        terms = _word_or_phrase_pattern(self.nouns)
        trigger = r"(?:" + "|".join(SELF_NOUN_TRIGGERS) + r")"
        pattern = re.compile(
            rf"\b(?P<prefix>{trigger})\s+(?P<article>um|o)\s+(?P<word>{terms})\b",
            flags=re.IGNORECASE,
        )

        def repl(match: re.Match[str]) -> str:
            article = "uma" if match.group("article").lower() == "um" else "a"
            word = match.group("word")
            return f"{match.group('prefix')} {article} {self._replacement_for(word, self.nouns)}"

        return pattern.sub(repl, text)
