from tradingcat.repositories.state import RolloutPromotionRepository
from tradingcat.services.rollout import RolloutPromotionService


def test_rollout_promotion_service_records_and_summarizes_attempts(tmp_path):
    service = RolloutPromotionService(RolloutPromotionRepository(tmp_path))

    blocked = service.record(
        requested_stage="30%",
        recommended_stage="10%",
        current_stage="10%",
        allowed=False,
        reason="too early",
        blocker="Need more clean readiness weeks.",
    )
    allowed = service.record(
        requested_stage="10%",
        recommended_stage="10%",
        current_stage="hold",
        allowed=True,
        reason="base gate passed",
        blocker=None,
    )

    attempts = service.list_attempts()
    assert len(attempts) == 2
    assert attempts[0].id == allowed.id
    assert attempts[1].id == blocked.id

    summary = service.summary()
    assert summary["count"] == 2
    assert summary["allowed_count"] == 1
    assert summary["blocked_count"] == 1
    assert summary["latest"].id == allowed.id


def test_rollout_promotion_service_clear_resets_history(tmp_path):
    service = RolloutPromotionService(RolloutPromotionRepository(tmp_path))
    service.record(
        requested_stage="10%",
        recommended_stage="10%",
        current_stage="hold",
        allowed=True,
    )

    service.clear()

    assert service.list_attempts() == []
    assert service.summary()["count"] == 0
