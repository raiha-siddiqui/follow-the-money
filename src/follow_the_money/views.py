"""Bounded views for untrusted model clients; human-only evidence stays local."""

from follow_the_money.contracts import NOTICE


def case_summary(case: dict) -> dict:
    """Only the human-approved report can supply claims to a model client."""
    state = case.get("state") or {}
    claims = (
        (state.get("report") or {}).get("claims", [])
        if case["status"] in {"completed", "rejected"}
        else []
    )
    return {
        "case_id": case["case_id"],
        "status": case["status"],
        "next_action": case["next_action"],
        "evidence_sha256": state.get("evidence_sha256"),
        "claims": claims[:50],
        "claims_truncated": len(claims) > 50,
        "review_status": "reviewed"
        if case["status"] in {"completed", "rejected"}
        else "unreviewed",
        "withdrawn_claims": sum(not c["retained"] for c in state.get("critic", [])),
        "budget": state.get("budget"),
        "stop_reason": state.get("stop_reason"),
        "notice": NOTICE,
    }


def memory_summary(value: dict) -> dict:
    """Omit analyst notes/rule text from model-visible overlap metadata."""
    return {
        "links": [
            {
                k: v
                for k, v in link.items()
                if k
                in {
                    "case_id",
                    "entry_id",
                    "addresses",
                    "txids",
                    "chain",
                    "prior_case_id",
                    "cluster_id",
                    "shared_addresses",
                    "revision",
                    "evidence_sha256",
                }
            }
            for link in value.get("links", [])[:50]
        ],
        "notice": NOTICE,
    }
