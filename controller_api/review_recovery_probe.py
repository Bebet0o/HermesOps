from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from .service_support import (
    ServiceSupportError,
    _request,
    _validated_base_url,
    read_session,
)


@dataclass(frozen=True)
class ReviewRecoveryProbeResult:
    review_list_status: int
    review_status: int | None
    evidence_status: int | None
    recovery_list_status: int
    recovery_status: int | None
    review_count: int
    recovery_count: int


def _items(payload: dict[str, object], label: str) -> list[object]:
    items = payload.get("data")
    if not isinstance(items, list):
        raise ServiceSupportError(f"{label} did not return a list.")
    return items


def _identifier(item: object, label: str) -> str:
    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
        raise ServiceSupportError(f"{label} returned an invalid item.")
    return str(item["id"])


def probe_review_recovery_reads(
    base_url: str,
    session_file: Path,
    *,
    wait_seconds: float = 10,
) -> ReviewRecoveryProbeResult:
    host, port = _validated_base_url(base_url)
    token = read_session(session_file)

    review_list_status, review_payload = _request(
        host,
        port,
        "/api/v1/reviews?limit=1",
        token=token,
        timeout=wait_seconds,
    )
    if review_list_status != 200:
        raise ServiceSupportError("Review list probe did not return HTTP 200.")
    reviews = _items(review_payload, "Review list probe")

    review_status: int | None = None
    evidence_status: int | None = None
    if reviews:
        review_id = quote(_identifier(reviews[0], "Review list probe"), safe="")
        review_status, detail = _request(
            host,
            port,
            f"/api/v1/reviews/{review_id}",
            token=token,
            timeout=wait_seconds,
        )
        if review_status != 200 or not isinstance(detail.get("data"), dict):
            raise ServiceSupportError("Review detail probe did not return HTTP 200.")

        evidence_status, evidence_payload = _request(
            host,
            port,
            f"/api/v1/reviews/{review_id}/evidence",
            token=token,
            timeout=wait_seconds,
        )
        if evidence_status != 200:
            raise ServiceSupportError("Review evidence probe did not return HTTP 200.")
        _items(evidence_payload, "Review evidence probe")

    recovery_list_status, recovery_payload = _request(
        host,
        port,
        "/api/v1/recoveries?limit=1",
        token=token,
        timeout=wait_seconds,
    )
    if recovery_list_status != 200:
        raise ServiceSupportError("Recovery list probe did not return HTTP 200.")
    recoveries = _items(recovery_payload, "Recovery list probe")

    recovery_status: int | None = None
    if recoveries:
        recovery_id = quote(_identifier(recoveries[0], "Recovery list probe"), safe="")
        recovery_status, detail = _request(
            host,
            port,
            f"/api/v1/recoveries/{recovery_id}",
            token=token,
            timeout=wait_seconds,
        )
        if recovery_status != 200 or not isinstance(detail.get("data"), dict):
            raise ServiceSupportError("Recovery detail probe did not return HTTP 200.")

    return ReviewRecoveryProbeResult(
        review_list_status=review_list_status,
        review_status=review_status,
        evidence_status=evidence_status,
        recovery_list_status=recovery_list_status,
        recovery_status=recovery_status,
        review_count=1 if reviews else 0,
        recovery_count=1 if recoveries else 0,
    )
