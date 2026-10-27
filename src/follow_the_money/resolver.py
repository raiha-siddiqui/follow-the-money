"""Sanctioned-wallet owner names are resolved through Polyglot Watchlist's public v2 service.

That project is optional: install it alongside this one to enable resolution.
"""

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from follow_the_money.contracts import Label, digest


@dataclass
class EntityResolver:
    service: Any = None

    @classmethod
    def from_workspace(cls, workspace, config):
        """Opt in to the existing Project 1 public service; never initialize it silently."""
        if workspace is None and config is None:
            return cls()
        if workspace is None or config is None:
            raise ValueError("Both --p1-workspace and --p1-config are required")
        try:
            from watchlist.review.service import ReviewService
        except ImportError as exc:
            raise ValueError(
                "Name resolution needs the Polyglot Watchlist package (watchlist); "
                "install it alongside this project"
            ) from exc

        return cls(ReviewService.open(workspace, config))

    def resolve_entity_name(self, label: Label, *, case_id: str) -> dict:
        if label.category != "sanctioned" or not label.owner_name:
            return {
                "status": "not_applicable",
                "reason": "No published sanctioned-wallet owner name",
            }
        if self.service is None:
            return {
                "status": "unavailable",
                "reason": "Polyglot Watchlist name resolution is not configured",
                "label_sha256": digest(label.to_dict()),
            }
        request_id = str(
            uuid5(NAMESPACE_URL, f"ftm:{case_id}:{digest(label.to_dict())}")
        )
        view = self.service.start_case(
            label.owner_name,
            origin="unknown",
            actor="ftm-resolver",
            request_id=request_id,
        )
        return {
            "status": "human_review_required",
            "project1_case_id": view.case_id,
            "project1_status": view.status,
            "label_sha256": digest(label.to_dict()),
            "notice": "Possible record matches only. The published name and wallet attribution remain unverified.",
        }
