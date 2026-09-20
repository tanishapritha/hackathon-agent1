from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class JudgingWeight(BaseModel):
    criterion: str = Field(default="Criteria", description="Name of the evaluation criterion.")
    weight: str = Field(default="1.0", description="Weight assigned to the criterion.")

    @model_validator(mode="before")
    @classmethod
    def flex_weights(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"criterion": data, "weight": "1.0"}
        if isinstance(data, dict):
            crit = data.get("criterion") or data.get("name") or "Criteria"
            wt = str(data.get("weight") or data.get("value") or "1.0")
            return {"criterion": str(crit), "weight": wt}
        return {"criterion": "Criteria", "weight": "1.0"}


class HackathonProfile(BaseModel):
    name: str = Field(default="Hackathon")
    theme: str = Field(default="General")
    problem_statements: List[str] = Field(default_factory=list)
    required_technologies: List[str] = Field(default_factory=list)
    allowed_technologies: List[str] = Field(default_factory=list)
    restrictions: List[str] = Field(default_factory=list)
    submission_requirements: List[str] = Field(default_factory=list)
    judging_criteria: List[str] = Field(default_factory=list)
    judging_weights: List[JudgingWeight] = Field(default_factory=list)
    expected_novelty: str = Field(default="High")
    expected_technical_depth: str = Field(default="High")
    expected_impact: str = Field(default="High")
    important_constraints: List[str] = Field(default_factory=list)
    explicit_requirements: List[str] = Field(default_factory=list)
    inferred_strategic_implications: List[str] = Field(default_factory=list)
    opportunity_areas: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def flex_profile(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {"name": "Hackathon", "theme": str(data or "General")}
        
        # Handle nested explicit_facts / inferences from loose LLM outputs
        res = dict(data)
        if "explicit_facts" in res and isinstance(res["explicit_facts"], dict):
            ef = res.pop("explicit_facts")
            if "theme" in ef and not res.get("theme"):
                res["theme"] = str(ef["theme"])
            res.setdefault("explicit_requirements", []).extend([f"{k}: {v}" for k, v in ef.items()])

        if "inferences" in res and isinstance(res["inferences"], dict):
            inf = res.pop("inferences")
            res.setdefault("inferred_strategic_implications", []).extend([f"{k}: {v}" for k, v in inf.items()])

        # Normalize string items to list where needed
        for list_field in ["problem_statements", "required_technologies", "allowed_technologies", 
                          "restrictions", "submission_requirements", "judging_criteria", 
                          "important_constraints", "explicit_requirements", 
                          "inferred_strategic_implications", "opportunity_areas"]:
            val = res.get(list_field)
            if isinstance(val, str):
                res[list_field] = [val]
            elif val is None:
                res[list_field] = []

        return res


class ResearchSource(BaseModel):
    id: str = Field(default="S1")
    title: str = Field(default="Source")
    url: str = Field(default="https://example.com")
    domain: str = Field(default="example.com")
    published_date: Optional[str] = None
    evidence: str = Field(default="Evidence snippet")

    @model_validator(mode="before")
    @classmethod
    def flex_source(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {"id": "S1", "title": "Source", "url": "https://example.com", "domain": "example.com", "evidence": str(data)}
        d = dict(data)
        d["id"] = str(d.get("id") or "S1")
        d["title"] = str(d.get("title") or "Source")
        d["url"] = str(d.get("url") or "https://example.com")
        d["domain"] = str(d.get("domain") or "example.com")
        d["evidence"] = str(d.get("evidence") or d.get("snippet") or "Evidence")
        return d


class OpportunityMap(BaseModel):
    target_users: List[str] = Field(default_factory=list)
    workflows: List[str] = Field(default_factory=list)
    pain_points: List[str] = Field(default_factory=list)
    existing_solutions: List[str] = Field(default_factory=list)
    technical_approaches: List[str] = Field(default_factory=list)
    market_workflow_gaps: List[str] = Field(default_factory=list)
    research_gaps: List[str] = Field(default_factory=list)
    evidence_source_ids: List[str] = Field(default_factory=list)


class CandidateIdea(BaseModel):
    title: str = Field(default="Untitled Project Idea")
    one_line_summary: str = Field(default="Project summary")
    target_user: str = Field(default="Developers")
    problem: str = Field(default="Problem statement")
    current_workflow: str = Field(default="Current workflow")
    proposed_solution: str = Field(default="Proposed solution")
    market_gap: str = Field(default="Market gap")
    research_gap: str = Field(default="Research gap")
    technical_novelty: str = Field(default="Technical novelty")
    hackathon_fit: str = Field(default="Hackathon fit")
    impact: str = Field(default="High impact")
    novelty: str = Field(default="High novelty")
    feasibility: str = Field(default="High feasibility")
    demoability: str = Field(default="High demoability")
    research_potential: str = Field(default="High research potential")
    risks: List[str] = Field(default_factory=list)
    evidence_or_reasoning: str = Field(default="Evidence")
    source_ids: List[str] = Field(default_factory=list)

    hackathon_fit_score: float = Field(default=7.0, ge=0, le=10)
    impact_score: float = Field(default=7.0, ge=0, le=10)
    novelty_score: float = Field(default=7.0, ge=0, le=10)
    feasibility_score: float = Field(default=7.0, ge=0, le=10)
    demoability_score: float = Field(default=7.0, ge=0, le=10)
    research_potential_score: float = Field(default=7.0, ge=0, le=10)
    score: Optional[float] = None

    @model_validator(mode="before")
    @classmethod
    def flex_candidate(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {"title": "Project Idea", "one_line_summary": str(data)}
        d = dict(data)
        # Ensure string fields are strings
        str_fields = ["title", "one_line_summary", "target_user", "problem", "current_workflow",
                      "proposed_solution", "market_gap", "research_gap", "technical_novelty",
                      "hackathon_fit", "impact", "novelty", "feasibility", "demoability",
                      "research_potential", "evidence_or_reasoning"]
        for f in str_fields:
            val = d.get(f)
            if isinstance(val, list):
                d[f] = "; ".join(str(x) for x in val)
            elif val is None:
                d[f] = f"N/A {f.replace('_', ' ')}"
            else:
                d[f] = str(val)

        if isinstance(d.get("risks"), str):
            d["risks"] = [d["risks"]]
        elif not isinstance(d.get("risks"), list):
            d["risks"] = []

        if isinstance(d.get("source_ids"), str):
            d["source_ids"] = [d["source_ids"]]
        elif not isinstance(d.get("source_ids"), list):
            d["source_ids"] = []

        return d

    @field_validator(
        "hackathon_fit_score",
        "impact_score",
        "novelty_score",
        "feasibility_score",
        "demoability_score",
        "research_potential_score",
        mode="before"
    )
    @classmethod
    def clamp_scores(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(10.0, val))
        except (ValueError, TypeError):
            return 7.0


class FinalIdeaSet(BaseModel):
    hackathon_profile: HackathonProfile = Field(default_factory=HackathonProfile)
    opportunity_map: Optional[OpportunityMap] = None
    ideas: List[CandidateIdea] = Field(default_factory=list)
    sources: List[ResearchSource] = Field(default_factory=list)
    rejected_ideas_summary: str = ""

    @model_validator(mode="before")
    @classmethod
    def flex_final_set(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return {"ideas": []}
        d = dict(data)
        if "ideas" not in d or not isinstance(d["ideas"], list):
            d["ideas"] = []
        if "sources" not in d or not isinstance(d["sources"], list):
            d["sources"] = []
        if "hackathon_profile" not in d or not isinstance(d["hackathon_profile"], dict):
            d["hackathon_profile"] = {}
        return d


class HackathonRequest(BaseModel):
    hackathon_text: str = Field(min_length=10)
    user_idea: Optional[str] = None
    additional_context: Optional[str] = None
    num_ideas: int = Field(default=5, ge=1, le=10)