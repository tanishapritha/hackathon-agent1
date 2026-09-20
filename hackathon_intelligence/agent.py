import json
from typing import Any, Dict, List
from google.adk.agents.llm_agent import Agent
from .config import GEMINI_MODEL
from .schemas import FinalIdeaSet, HackathonProfile, OpportunityMap, ResearchSource


PLANNER_INSTRUCTIONS = """
You are the Hackathon Research Planner.
Your job is to analyze the hackathon brief, user idea, and constraints, extract the Hackathon Profile, and create a targeted search research plan.

Output ONLY a valid JSON object matching this schema:
{
  "hackathon_profile": {
    "name": "Hackathon Name",
    "theme": "Theme",
    "problem_statements": ["..."],
    "required_technologies": ["..."],
    "allowed_technologies": ["..."],
    "restrictions": ["..."],
    "submission_requirements": ["..."],
    "judging_criteria": ["..."],
    "judging_weights": [{"criterion": "...", "weight": "..."}],
    "expected_novelty": "High",
    "expected_technical_depth": "High",
    "expected_impact": "High",
    "important_constraints": ["..."],
    "explicit_requirements": ["..."],
    "inferred_strategic_implications": ["..."],
    "opportunity_areas": ["..."]
  },
  "research_queries": [
    "search query 1 for target users and pain points",
    "search query 2 for existing competitors and solutions",
    "search query 3 for technical approaches and limitations",
    "search query 4 for market gaps"
  ],
  "research_focus": [
    "target users",
    "existing competitors",
    "technical gaps"
  ]
}

Provide max 5 targeted, highly relevant search queries. Avoid duplicate or vague queries.
Do not include text outside the JSON object.
"""

SYNTHESIS_INSTRUCTIONS = """
You are the Hackathon Opportunity Synthesizer.
Your job is to synthesize compact research evidence and the hackathon profile into a structured Opportunity Map.

Output ONLY a valid JSON object matching this schema:
{
  "target_users": ["..."],
  "workflows": ["..."],
  "pain_points": ["..."],
  "existing_solutions": ["..."],
  "technical_approaches": ["..."],
  "market_workflow_gaps": ["..."],
  "research_gaps": ["..."],
  "evidence_source_ids": ["S1", "S2"]
}

Be concise and evidence-backed. Do not generate final project ideas yet.
Do not include text outside the JSON object.
"""

CANDIDATE_INSTRUCTIONS = """
You are the Hackathon Candidate Idea Generator and Critic.
Given the Hackathon Profile and Opportunity Map, generate 8-10 candidate ideas internally, challenge them for feasibility, novelty, differentiation, and demo potential, and return the top requested N ideas.

Output ONLY a valid JSON object matching this schema:
{
  "hackathon_profile": { ... },
  "opportunity_map": { ... },
  "ideas": [
    {
      "title": "Project Title",
      "one_line_summary": "Summary (1-2 sentences)",
      "target_user": "Target user",
      "problem": "Problem statement",
      "current_workflow": "Current workflow",
      "proposed_solution": "Proposed solution",
      "market_gap": "Market gap",
      "research_gap": "Research gap",
      "technical_novelty": "Technical novelty",
      "hackathon_fit": "Hackathon fit",
      "impact": "Impact",
      "novelty": "Novelty",
      "feasibility": "Feasibility",
      "demoability": "Demoability",
      "research_potential": "Research potential",
      "risks": ["..."],
      "evidence_or_reasoning": "Reasoning and evidence",
      "source_ids": ["S1"],
      "hackathon_fit_score": 8.5,
      "impact_score": 9.0,
      "novelty_score": 8.0,
      "feasibility_score": 8.5,
      "demoability_score": 9.0,
      "research_potential_score": 8.0
    }
  ],
  "sources": [
    {
      "id": "S1",
      "title": "Source Title",
      "url": "https://example.com",
      "domain": "example.com",
      "evidence": "Evidence snippet"
    }
  ],
  "rejected_ideas_summary": "Summary of rejected generic/saturated candidates"
}

Do not include chain-of-thought or text outside the JSON object.
"""

root_agent = Agent(
    model=GEMINI_MODEL,
    name="hackathon_intelligence_agent",
    description="Researches hackathon opportunities and produces evidence-backed project ideas.",
    instruction=CANDIDATE_INSTRUCTIONS,
    output_schema=FinalIdeaSet,
)