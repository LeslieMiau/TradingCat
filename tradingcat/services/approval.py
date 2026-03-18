from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingcat.domain.models import ApprovalRequest, ApprovalStatus, OrderIntent
from tradingcat.repositories.state import ApprovalRepository


class ApprovalService:
    def __init__(self, repository: ApprovalRepository) -> None:
        self._repository = repository
        self._requests = repository.load()

    def create_request(self, intent: OrderIntent) -> ApprovalRequest:
        request = ApprovalRequest(order_intent=intent)
        self._requests[request.id] = request
        self._repository.save(self._requests)
        return request

    def approve(self, request_id: str, reason: str | None = None) -> ApprovalRequest:
        request = self._requests[request_id]
        request.status = ApprovalStatus.APPROVED
        request.decided_at = datetime.now(UTC)
        request.decision_reason = reason
        self._repository.save(self._requests)
        return request

    def reject(self, request_id: str, reason: str | None = None) -> ApprovalRequest:
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

    def expire_stale(self, max_age: timedelta, reason: str | None = None) -> list[ApprovalRequest]:
        now = datetime.now(UTC)
        expired: list[ApprovalRequest] = []
        for request in self._requests.values():
            if request.status != ApprovalStatus.PENDING:
                continue
            if now - request.created_at < max_age:
                continue
            request.status = ApprovalStatus.EXPIRED
            request.decided_at = now
            request.decision_reason = reason or f"Expired after {max_age}"
            expired.append(request)
        if expired:
            self._repository.save(self._requests)
        return expired

    def list_requests(self) -> list[ApprovalRequest]:
        return list(self._requests.values())

    def get(self, request_id: str) -> ApprovalRequest:
        return self._requests[request_id]

    def clear(self) -> None:
        self._requests = {}
        self._repository.save(self._requests)
