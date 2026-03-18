from tradingcat.repositories.state import RolloutPolicyRepository
from tradingcat.services.rollout import RolloutPolicyService


def test_rollout_policy_defaults_to_full_allocation(tmp_path):
    service = RolloutPolicyService(RolloutPolicyRepository(tmp_path))

    summary = service.summary()

    assert summary["stage"] == "100%"
    assert summary["allocation_ratio"] == 1.0
    assert summary["source"] == "default"


def test_rollout_policy_applies_recommendation(tmp_path):
    service = RolloutPolicyService(RolloutPolicyRepository(tmp_path))

    policy = service.apply_recommendation({"current_recommendation": "30%"})

    assert policy.stage == "30%"
    assert policy.allocation_ratio == 0.3
    assert policy.source == "recommendation"
