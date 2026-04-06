"""
Tests for hacker-laws knowledge base injection.
Validates that relevant laws are detected for architecture/scaling queries
and not injected for unrelated queries.
"""
import re
from pathlib import Path


KB_PATH = Path(__file__).parent.parent / "hacker_laws.md"


def load_laws() -> dict[str, str]:
    """Parse hacker_laws.md into {law_name: body} dict."""
    content = KB_PATH.read_text()
    sections = re.split(r'\n(?=## )', content)
    laws = {}
    for s in sections:
        m = re.match(r'^## (.+)', s)
        if m:
            laws[m.group(1)] = s
    return laws


def find_relevant_laws(query: str, laws: dict[str, str]) -> list[str]:
    """Return law names whose 'Relevant for' tags match the query topic."""
    q = query.lower()
    topic_map = {
        "team": ["scaling", "team"],
        "scal": ["scaling", "team"],
        "optim": ["optimization", "complexity"],
        "architect": ["architecture", "complexity"],
        "estimat": ["estimation"],
        "quality": ["quality"],
    }

    matched_topics = set()
    for kw, topics in topic_map.items():
        if kw in q:
            matched_topics.update(topics)

    if not matched_topics:
        return []

    hits = []
    for name, body in laws.items():
        relevant_match = re.search(r'\*\*Relevant for:\*\* (.+)', body)
        if not relevant_match:
            continue
        law_topics = {t.strip() for t in relevant_match.group(1).split(",")}
        if law_topics & matched_topics:
            hits.append(name)
    return hits


class TestHackerLawsKnowledgeBase:

    def setup_method(self):
        self.laws = load_laws()

    def test_knowledge_base_loads(self):
        assert len(self.laws) >= 50, f"Expected 50+ laws, got {len(self.laws)}"

    def test_brooks_law_present(self):
        assert any("Brook" in k for k in self.laws), "Brooks' Law not found"

    def test_pareto_principle_present(self):
        assert any("Pareto" in k for k in self.laws), "Pareto principle not found"

    def test_brooks_law_detected_on_team_scaling(self):
        """Brooks's Law must fire on team scaling queries."""
        hits = find_relevant_laws("how do we speed up by adding more engineers to the team", self.laws)
        assert any("Brook" in h for h in hits), (
            f"Brooks' Law not detected for team scaling query. Got: {hits}"
        )

    def test_pareto_detected_on_optimization(self):
        """Pareto principle must fire on optimization queries."""
        hits = find_relevant_laws("where should we focus our optimization effort", self.laws)
        assert any("Pareto" in h for h in hits), (
            f"Pareto not detected for optimization query. Got: {hits}"
        )

    def test_no_injection_on_unrelated_query(self):
        """No laws should be injected for unrelated queries."""
        hits = find_relevant_laws("what is the weather today", self.laws)
        assert hits == [], f"Expected no hits for unrelated query, got: {hits}"

    def test_conway_law_detected_on_architecture(self):
        hits = find_relevant_laws("how should we structure our microservices architecture", self.laws)
        assert any("Conway" in h for h in hits), (
            f"Conway's Law not detected for architecture query. Got: {hits}"
        )
