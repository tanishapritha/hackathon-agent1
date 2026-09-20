import pytest
from hackathon_intelligence.schemas import HackathonRequest, FinalIdeaSet, HackathonProfile
from runner import extract_and_repair_json


def test_request_defaults_to_five():
    request = HackathonRequest(
        hackathon_text="A hackathon about useful AI systems."
    )
    assert request.num_ideas == 5


def test_request_rejects_invalid_count():
    try:
        HackathonRequest(
            hackathon_text="A hackathon about useful AI systems.",
            num_ideas=11,
        )
        assert False
    except ValueError:
        assert True


def test_extract_and_repair_truncated_loose_json():
    raw_truncated_output = """
    ```json
    {
      "hackathon_profile": {
        "explicit_facts": { "theme": "educational app" },
        "inferences": {
          "potential_target_audiences": [
            "K-12 students",
            "higher education students",
            "lifelong learners"
          ],
          "potential_areas": [
            "personalized learning",
            "gamification",
            "accessibility",
    """

    repaired = extract_and_repair_json(raw_truncated_output)
    assert isinstance(repaired, dict)
    assert "hackathon_profile" in repaired

    # Validate against Pydantic schema
    final_set = FinalIdeaSet.model_validate(repaired)
    assert isinstance(final_set.hackathon_profile, HackathonProfile)
    assert final_set.hackathon_profile.theme == "educational app"
    assert len(final_set.hackathon_profile.explicit_requirements) > 0
    assert len(final_set.hackathon_profile.inferred_strategic_implications) > 0