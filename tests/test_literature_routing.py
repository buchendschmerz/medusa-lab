from __future__ import annotations

import json

from medusa.integrations.literature import (
    assign_keys,
    mine_gap_sentences,
    rank_and_dedupe,
    search_arxiv,
    search_openalex,
    to_bibtex,
)
from medusa.models import AnalysisReport, Hypothesis, LiteratureItem, Mode, TheoryModel, Track
from medusa.recipes import all_recipes, match_recipe
from medusa.routing import detect_human_requirements, route
from medusa.stats import sample_size

ARXIV_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2101.01234v2</id>
    <published>2021-01-05T00:00:00Z</published>
    <title>Naming games on
      social networks</title>
    <summary>We study naming games. However, it remains unclear how hubs affect consensus.</summary>
    <author><name>Ada Lovelace</name></author><author><name>Alan Turing</name></author>
    <arxiv:primary_category term="physics.soc-ph"/>
    <arxiv:doi>10.1000/xyz</arxiv:doi>
  </entry>
</feed>"""

OPENALEX = {"results": [{"id": "https://openalex.org/W1", "title": "Naming Games on Social Networks",
                         "publication_year": 2021, "doi": "https://doi.org/10.1000/xyz",
                         "authorships": [{"author": {"display_name": "Ada Lovelace"}}],
                         "primary_location": {"source": {"display_name": "Journal X"}},
                         "abstract_inverted_index": {"Hubs": [0], "matter": [1]}, "cited_by_count": 10},
                        {"id": "https://openalex.org/W2", "title": "Opinion dynamics", "publication_year": 2019,
                         "authorships": [], "abstract_inverted_index": None}]}


def test_arxiv_and_openalex_parsing() -> None:
    arxiv = search_arxiv("naming game network", fetch=lambda url, timeout: ARXIV_XML)
    assert arxiv[0].title == "Naming games on social networks" and arxiv[0].arxiv_id == "2101.01234"
    assert arxiv[0].authors == ["Ada Lovelace", "Alan Turing"] and arxiv[0].year == 2021
    oa = search_openalex("naming game", fetch=lambda url, timeout: json.dumps(OPENALEX).encode())
    assert oa[0].abstract == "Hubs matter" and oa[0].doi == "10.1000/xyz"
    ranked = rank_and_dedupe(arxiv + oa, ["naming game network"], limit=5)
    assert len(ranked) == 2  # duplicate title merged
    assign_keys(ranked)
    assert ranked[0].key.startswith("lovelace2021") and len({r.key for r in ranked}) == 2
    bib = to_bibtex(ranked)
    assert "@article{" in bib and "archivePrefix" in bib
    gaps = mine_gap_sentences(ranked)
    assert gaps and "remains unclear" in gaps[0][0]


def test_key_collisions_get_suffixes() -> None:
    items = [LiteratureItem(key="", title="Same Title Here", authors=["A B"], year=2020) for _ in range(3)]
    assign_keys(items)
    assert len({i.key for i in items}) == 3


def test_recipe_matching() -> None:
    assert match_recipe("SNSにおける新語の拡散と言語進化").recipe.id == "naming_game"
    assert match_recipe("Why do people cooperate?").recipe.id == "spatial_pd"
    assert match_recipe("拍手が揃う仕組み").recipe.id == "kuramoto"
    fallback = match_recipe("睡眠と創造性")
    assert fallback.is_default and fallback.recipe.id == "sir_network"
    for recipe in all_recipes():
        assert recipe.script_path.exists() and recipe.sweep_values() and recipe.sweep_values(quick=True)
        assert recipe.headline.get("ja") and recipe.headline.get("en")


def test_human_cue_detection_and_routing() -> None:
    assert "アンケート" in detect_human_requirements("アンケートで意識を調べる")
    assert "participants" in detect_human_requirements("Recruit 40 participants for a lab experiment")
    assert detect_human_requirements("simulate the Kuramoto model") == []
    analysis = AnalysisReport(model=TheoryModel(name="m", summary="s"), hypotheses=[
        Hypothesis(id="H1", statement="Order emerges above K_c", track=Track.IN_SILICO),
        Hypothesis(id="H2", statement="A survey of participants shows bias", track=Track.IN_SILICO),
        Hypothesis(id="H3", statement="People clap in sync", track=Track.HUMAN),
    ])
    hybrid = route(analysis, Mode.HYBRID)
    assert hybrid.in_silico == ["H1"] and hybrid.human == ["H2", "H3"] and hybrid.run_simulation
    assert "Re-routed" in analysis.hypotheses[1].routing_reason
    in_silico = route(analysis, Mode.IN_SILICO)
    assert in_silico.deferred == ["H2", "H3"] and not in_silico.write_proposals
    human = route(analysis, Mode.HUMAN)
    assert human.deferred == ["H1"] and not human.run_simulation and not human.write_paper


def test_power_analysis_matches_gpower() -> None:
    assert sample_size(0.5) == 64
    assert sample_size(0.5, design="within") == 34
    assert sample_size(0.8) == 26
    assert sample_size(1.0, design="within") == 10
