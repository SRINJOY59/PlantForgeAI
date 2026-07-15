"""Question -> seed nodes. Tags link exactly (the same normalization the
resolver used at write time, so query and corpus meet on identical ids);
title-case phrases and standard codes fall back to name search."""

import re

from plantmind_core import tags
from plantmind_core.telemetry import get_logger

from retrieval.models import Seed

log = get_logger("retrieval.linker")

TITLE_PHRASE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
STANDARD_RE = re.compile(r"\b(OISD[-\s]?STD[-\s]?\d+|IS\s?\d{3,5}|IBR)\b", re.I)


class QueryLinker:
    def __init__(self, reader):
        self._reader = reader

    def link(self, question: str) -> list:
        seeds, seen = [], set()

        for tag, _, _ in tags.find_tags(question):
            self._add(seeds, seen, self._reader.entity_by_surface(tag))

        for match in STANDARD_RE.findall(question):
            for hit in self._reader.entities_by_name(match.replace(" ", "-")):
                self._add(seeds, seen, hit)

        if not seeds:   # e.g. "the seal replacement procedure"
            for phrase in TITLE_PHRASE_RE.findall(question):
                for hit in self._reader.entities_by_name(phrase, limit=2):
                    self._add(seeds, seen, hit)

        log.info("linked", question=question[:60],
                 seeds=[s.node_id for s in seeds])
        return seeds

    @staticmethod
    def _add(seeds, seen, hit):
        if hit and hit["id"] not in seen:
            seen.add(hit["id"])
            seeds.append(Seed(node_id=hit["id"], surface=hit["surface"],
                              label=hit["label"]))
