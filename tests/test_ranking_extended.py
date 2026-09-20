from hackathon_intelligence.ranking import rank_ideas, calculate_score
from hackathon_intelligence.schemas import CandidateIdea, HackathonProfile, JudgingWeight


def make_idea(title="Test", score=8.0):
    return CandidateIdea(
        title=title,
        one_line_summary="Summary",
        target_user="Users",
        problem="Problem",
        current_workflow="Workflow",
        proposed_solution="Solution",
        market_gap="Gap",
        research_gap="Gap",
        technical_novelty="Novelty",
        hackathon_fit="Fit",
        impact="Impact",
        novelty="Novelty",
        feasibility="Feasibility",
        demoability="Demoability",
        research_potential="Potential",
        risks=[],
        evidence_or_reasoning="Reasoning",
        hackathon_fit_score=score,
        impact_score=score,
        novelty_score=score,
        feasibility_score=score,
        demoability_score=score,
        research_potential_score=score,
    )


def test_ranking_and_exact_count():
    ideas = [
        make_idea("Idea 1", score=5.0),
        make_idea("Idea 2", score=9.0),
        make_idea("Idea 3", score=7.0),
    ]

    ranked = rank_ideas(ideas, requested_count=2)
    assert len(ranked) == 2
    assert ranked[0].title == "Idea 2"
    assert ranked[1].title == "Idea 3"


def test_score_clamping():
    idea = make_idea("Out of bounds", score=15.0)
    # Score should clamp to 10.0
    assert calculate_score(idea) == 10.0