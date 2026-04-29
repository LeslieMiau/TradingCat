"""ManualConfirmationService — lightweight order confirmation for solo traders.

Replaces ApprovalService with terminology that better fits a single-person
system. The core workflow is preserved: orders marked ``requires_approval``
are routed to the manual broker and wait for explicit confirmation before
submission.

Status model:
  - ``pending``: awaiting trader confirmation
  - ``confirmed``: trader approved → order submitted
  - ``cancelled``: trader rejected
  - ``expired``: TTL elapsed without action
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingcat.domain.models import ApprovalRequest, ApprovalStatus, OrderIntent
from tradingcat.repositories.state import ApprovalRepository


class ManualConfirmationService:
    """Manages order confirmations for semi-automated (A-share/manual) execution.

    Thin layer over the existing ApprovalRepository for backward compatibility
    with persisted data. Terminology is changed from "approval" to "confirmation"
    to better reflect the solo-trader use case.
    """

    def __init__(self, repository: ApprovalRepository, ttl_minutes: int = 120) -> None:
        self._repository = repository
        self._requests = repository.load()
        self._ttl_minutes = ttl_minutes

    @property
    def pending(self) -> list[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]

    def create_request(self, intent: OrderIntent) -> ApprovalRequest:
        now = datetime.now(UTC)
        request = ApprovalRequest(
            order_intent=intent,
            created_at=now,
            expires_at=now + timedelta(minutes=self._ttl_minutes),
        )
        self._requests[request.id] = request
        self._repository.save(self._requests)
        return request

    def confirm(self, request_id: str, reason: str | None = None) -> ApprovalRequest:
        request = self._requests[request_id]
        request.status = ApprovalStatus.APPROVED
        request.decided_at = datetime.now(UTC)
        request.decision_reason = reason
        self._repository.save(self._requests)
        return request

    def cancel(self, request_id: str, reason: str | None = None) -> ApprovalRequest:
        request = self._requests[request_id]
        request.status = ApprovalStatus.REJECTED
        request.decided_at = datetime.now(UTC)
        request.decision_reason = reason
        self._repository.save(self._requests)
        return request

    def expire(self, request_id: str, reason: str | None = None) -> ApprovalRequest:
        request = self._requests[request_id]
        request.status = ApprovalStatus.EXPIRED
        request.decided_at = datetime.now(UTC)
        request.decision_reason = reason
        self._repository.save(self._requests)
        return request

    def expire_stale(self, reason: str | None = None) -> list[ApprovalRequest]:
        now = datetime.now(UTC)
        expired: list[ApprovalRequest] = []
        for request in self._requests.values():
            if request.status != ApprovalStatus.PENDING:
                continue
            if request.expires_at is not None and now >= request.expires_at:
                request.status = ApprovalStatus.EXPIRED
                request.decided_at = now
                request.decision_reason = reason or f"Expired after {self._ttl_minutes} min TTL"
                expired.append(request)
        if expired:
            self._repository.save(self._requests)
        return expired

    def get(self, request_id: str) -> ApprovalRequest:
        return self._requests[request_id]

    def list_all(self) -> list[ApprovalRequest]:
        return list(self._requests.values())

    # ── Compat aliases for routes that still use "approval" terminology ──
    list_requests = list_all

    def approve(self, request_id: str, reason: str | None = None) -> ApprovalRequest:
        return self.confirm(request_id, reason)

    def reject(self, request_id: str, reason: str | None = None) -> ApprovalRequest:
        return self.cancel(request_id, reason)

    def clear(self) -> None:
        self._requests = {}
        self._repository.save(self._requests)
