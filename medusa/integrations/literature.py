"""Literature retrieval from arXiv and OpenAlex (no API keys needed)."""

from __future__ import annotations

import json
import logging
import math
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable

from ..models import LiteratureItem

log = logging.getLogger("medusa.literature")

USER_AGENT = "MedusaLab/0.1 (autonomous research lab; https://github.com/buchendschmerz/medusa-lab)"
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
STOPWORDS = frozenset(
    ["a", "an", "the", "of", "and", "or", "in", "on", "for", "to", "with", "from", "by", "at", "as", "is", "are", "be", "was", "were", "this", "that", "these", "those", "via", "into", "over", "under", "about", "using", "based", "study", "model", "models", "towards", "toward", "new", "its", "their", "our", "we"])

Fetcher = Callable[[str, float], bytes]


def http_get(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https endpoints
        return resp.read()


def _terms(query: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'\-]+", query.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def search_arxiv(query: str, max_results: int = 8, timeout: float = 30, fetch: Fetcher = http_get) -> list[LiteratureItem]:
    terms = _terms(query)[:5]
    if not terms:
        return []
    search = " AND ".join(f"all:{t}" for t in terms)
    params = urllib.parse.urlencode({"search_query": search, "start": 0, "max_results": max_results,
                                     "sortBy": "relevance", "sortOrder": "descending"})
    root = ET.fromstring(fetch(f"https://export.arxiv.org/api/query?{params}", timeout))
    items = []
    for entry in root.findall("a:entry", ATOM):
        title = " ".join((entry.findtext("a:title", "", ATOM) or "").split())
        if not title:
            continue
        abs_url = entry.findtext("a:id", "", ATOM) or ""
        arxiv_id = abs_url.rsplit("/abs/", 1)[-1]
        base_id = re.sub(r"v\d+$", "", arxiv_id)
        cat = entry.find("arxiv:primary_category", ATOM)
        category = cat.get("term", "") if cat is not None else ""
        published = entry.findtext("a:published", "", ATOM) or ""
        items.append(LiteratureItem(
            key="", title=title,
            authors=[(a.findtext("a:name", "", ATOM) or "").strip() for a in entry.findall("a:author", ATOM)],
            year=int(published[:4]) if published[:4].isdigit() else None,
            venue=f"arXiv:{base_id}" + (f" [{category}]" if category else ""),
            url=f"https://arxiv.org/abs/{base_id}",
            abstract=" ".join((entry.findtext("a:summary", "", ATOM) or "").split()),
            source="arxiv", doi=entry.findtext("arxiv:doi", "", ATOM) or "", arxiv_id=base_id,
        ))
    return items


def _openalex_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions = [(pos, word) for word, poss in index.items() for pos in poss]
    return " ".join(word for _, word in sorted(positions))


def search_openalex(query: str, max_results: int = 8, timeout: float = 30, fetch: Fetcher = http_get,
                    mailto: str = "") -> list[LiteratureItem]:
    params = {"search": query, "per-page": max_results}
    if mailto:
        params["mailto"] = mailto
    data = json.loads(fetch("https://api.openalex.org/works?" + urllib.parse.urlencode(params), timeout))
    items = []
    for work in data.get("results", []):
        title = " ".join((work.get("title") or work.get("display_name") or "").split())
        if not title:
            continue
        doi = (work.get("doi") or "").replace("https://doi.org/", "")
        source = ((work.get("primary_location") or {}).get("source") or {})
        items.append(LiteratureItem(
            key="", title=title,
            authors=[(a.get("author") or {}).get("display_name", "") for a in work.get("authorships", [])][:12],
            year=work.get("publication_year"), venue=source.get("display_name") or "",
            url=f"https://doi.org/{doi}" if doi else (work.get("id") or ""),
            abstract=_openalex_abstract(work.get("abstract_inverted_index")), source="openalex", doi=doi,
            citations=work.get("cited_by_count"),
        ))
    return items


SEARCHERS: dict[str, Callable[..., list[LiteratureItem]]] = {"arxiv": search_arxiv, "openalex": search_openalex}


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()).strip()


def rank_and_dedupe(items: Iterable[LiteratureItem], queries: list[str], limit: int) -> list[LiteratureItem]:
    query_terms = {t for q in queries for t in _terms(q)}
    seen: dict[str, LiteratureItem] = {}
    for item in items:
        key = _norm_title(item.title)
        if not key:
            continue
        if key in seen:  # prefer the record with an abstract / DOI
            old = seen[key]
            if (not old.abstract and item.abstract) or (not old.doi and item.doi):
                seen[key] = item
            continue
        seen[key] = item
    ranked = []
    for item in seen.values():
        words = set(_terms(item.title + " " + item.abstract))
        overlap = len(words & query_terms) / (len(query_terms) or 1)
        recency = 0.1 if (item.year or 0) >= 2015 else 0.0
        cites = 0.05 * math.log10(1 + (item.citations or 0))
        abstract_bonus = 0.05 if item.abstract else -0.1
        item.relevance = round(overlap + recency + cites + abstract_bonus, 4)
        ranked.append(item)
    ranked.sort(key=lambda it: it.relevance, reverse=True)
    return ranked[:limit]


def _ascii_word(text: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower())


def assign_keys(items: list[LiteratureItem], taken: Iterable[str] = ()) -> None:
    """Deterministic citation keys like ``baronchelli2006sharp``."""
    used = set(taken)
    for item in items:
        if item.key and item.key not in used:
            used.add(item.key)
            continue
        last = _ascii_word(item.authors[0].split()[-1]) if item.authors and item.authors[0].split() else "anon"
        word = next((w for w in (_ascii_word(w) for w in item.title.split()) if len(w) > 3 and w not in STOPWORDS), "x")
        base = f"{last or 'anon'}{item.year or 'nd'}{word}"[:48]
        key, suffix = base, 1
        while key in used:
            suffix += 1
            key = f"{base}{chr(ord('a') + suffix - 2)}" if suffix <= 27 else f"{base}{suffix}"
        item.key = key
        used.add(key)


def _bib_escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "").replace("}", "").replace("%", r"\%").replace("&", r"\&")


def to_bibtex(items: Iterable[LiteratureItem]) -> str:
    entries = []
    for it in items:
        kind = "book" if it.foundational and not it.doi and "Press" in it.venue else "article"
        fields = [("title", it.title), ("author", " and ".join(it.authors) or "Anonymous"),
                  ("year", str(it.year or "")), ("journal" if kind == "article" else "publisher", it.venue)]
        if it.doi:
            fields.append(("doi", it.doi))
        if it.url:
            fields.append(("url", it.url))
        if it.arxiv_id:
            fields += [("eprint", it.arxiv_id), ("archivePrefix", "arXiv")]
        body = ",\n".join(f"  {k} = {{{_bib_escape(v)}}}" for k, v in fields if v)
        entries.append(f"@{kind}{{{it.key},\n{body}\n}}")
    return "\n\n".join(entries) + "\n"


CUES = ("remains unclear", "remain unclear", "open question", "little is known", "not well understood",
        "poorly understood", "future work", "future research", "we leave", "limitation", "has not been",
        "have not been", "unexplored", "lack of", "it is unknown", "remains to be", "challenge", "however")


def mine_gap_sentences(items: Iterable[LiteratureItem], limit: int = 3) -> list[tuple[str, str]]:
    """Heuristic (offline) extraction of sentences that state gaps: [(sentence, key)]."""
    scored = []
    for item in items:
        for sentence in re.split(r"(?<=[.!?])\s+", item.abstract or ""):
            low = sentence.lower()
            score = sum(2 if cue in ("open question", "remains unclear", "little is known") else 1
                        for cue in CUES if cue in low)
            if score and 40 <= len(sentence) <= 400:
                scored.append((score + item.relevance, sentence.strip(), item.key))
    scored.sort(key=lambda t: t[0], reverse=True)
    out, seen = [], set()
    for _, sentence, key in scored:
        if key in seen:
            continue
        seen.add(key)
        out.append((sentence, key))
        if len(out) >= limit:
            break
    return out
