from typing import Dict, List, Optional
from .schemas import CandidateIdea, HackathonProfile, JudgingWeight

DEFAULT_WEIGHTS = {
    "hackathon_fit": 0.25,
    "impact": 0.20,
    "novelty": 0.20,
    "feasibility": 0.15,
    "demoability": 0.10,
    "research_potential": 0.10,
}


def parse_weights(profile: Optional[HackathonProfile] = None) -> Dict[str, float]:
    """Extract normalized weights from profile or default."""
    if not profile or not profile.judging_weights:
        return DEFAULT_WEIGHTS

    weights = DEFAULT_WEIGHTS.copy()
    # Try parsing judging weights if any match standard keys
    try:
        total = 0.0
        parsed = {}
        for item in profile.judging_weights:
            crit = item.criterion.lower().strip()
            # extract numeric float from weight string e.g. "30%" or "0.3"
            import re
            m = re.search(r'(\d+(?:\.\d+)?)', item.weight)
            if m:
                val = float(m.group(1))
                if val > 1.0:
                    val = val / 100.0
                parsed[crit] = val
                total += val

        if total > 0 and len(parsed) >= 3:
            # map parsed to standard categories if possible
            for key in weights:
                for crit, val in parsed.items():
                    if key in crit:
                        weights[key] = val / total
    except Exception:
        pass

    return weights


def calculate_score(idea: CandidateIdea, weights: Optional[Dict[str, float]] = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    
    # Ensure scores are valid floats bounded 0-10
    fit = max(0.0, min(10.0, float(idea.hackathon_fit_score)))
    imp = max(0.0, min(10.0, float(idea.impact_score)))
    nov = max(0.0, min(10.0, float(idea.novelty_score)))
    fea = max(0.0, min(10.0, float(idea.feasibility_score)))
    dem = max(0.0, min(10.0, float(idea.demoability_score)))
    res = max(0.0, min(10.0, float(idea.research_potential_score)))

    score = (
        fit * w.get("hackathon_fit", 0.25)
        + imp * w.get("impact", 0.20)
        + nov * w.get("novelty", 0.20)
        + fea * w.get("feasibility", 0.15)
        + dem * w.get("demoability", 0.10)
        + res * w.get("research_potential", 0.10)
    )
    return round(score, 2)


def rank_ideas(
    ideas: List[CandidateIdea],
    profile: Optional[HackathonProfile] = None,
    requested_count: Optional[int] = None
) -> List[CandidateIdea]:
    weights = parse_weights(profile)
    
    # Deduplicate candidate ideas by title / summary similarity
    seen_titles = set()
    unique_ideas = []
    for idea in ideas:
        norm_title = idea.title.lower().strip()
        if norm_title in seen_titles:
            continue
        seen_titles.add(norm_title)
        idea.score = calculate_score(idea, weights)
        unique_ideas.append(idea)

    ranked = sorted(unique_ideas, key=lambda item: item.score or 0.0, reverse=True)
    
    if requested_count is not None and requested_count > 0:
        return ranked[:requested_count]
        
    return ranked