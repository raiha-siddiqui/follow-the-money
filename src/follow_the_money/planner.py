"""Deterministic bounded planner; goals never alter hard safety policies."""

from follow_the_money.cases import TraceRequest


def plan(request: TraceRequest) -> dict:
    return {
        "goal": request.goal,
        "chain": request.chain,
        "seed": request.seed,
        "max_calls": request.max_calls,
        "max_hops": request.max_hops,
        "stop_conditions": [
            "budget_exhausted",
            "hop_limit",
            "frontier_exhausted",
            "coinjoin",
            "service_or_cluster_cap",
            "recorded_evidence_missing",
        ],
        "network_mode": "replay",
        "actions": "human-reviewed drafts only",
        "ranking": request.strategy,
        "llm_required": False,
    }
