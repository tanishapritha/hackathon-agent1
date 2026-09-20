from hackathon_intelligence.ranking import calculate_score
from hackathon_intelligence.schemas import CandidateIdea


def make_idea():
    return CandidateIdea(
        title="Test",
        one_line_summary="Test idea.",
        target_user="Developers",
        problem="Test problem.",
        current_workflow="Manual process.",
        proposed_solution="Automated process.",
        market_gap="Gap.",
        research_gap="Gap.",
        technical_novelty="Novel approach.",
        hackathon_fit="Strong.",
        impact="High.",
        novelty="High.",
        feasibility="High.",
        demoability="High.",
        research_potential="High.",
        risks=[],
        evidence_or_reasoning="Test.",
        hackathon_fit_score=10,
        impact_score=10,
        novelty_score=10,
        feasibility_score=10,
        demoability_score=10,
        research_potential_score=10,
    )


def test_score():
    assert calculate_score(make_idea()) == 10.0
