"""Streamlit human review client. Run with `python -m follow_the_money ui`."""

import json
import os
from uuid import uuid4

import httpx
import streamlit as st

from follow_the_money.security import local_url


def api_request(base: str, token: str, method: str, path: str, body=None):
    base = local_url(base)
    with httpx.Client(
        base_url=base,
        headers={"Authorization": "Bearer " + token},
        timeout=120,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        response = (
            client.request(method, path, json=body)
            if body is not None
            else client.request(method, path)
        )
    if response.status_code >= 400:
        raise ValueError(
            f"API rejected the operation ({response.status_code}): {response.json().get('error', 'request_failed')}"
        )
    return response.json()


def main():
    st.set_page_config(page_title="Follow the Money", layout="wide")
    st.title("Follow the Money")
    st.caption(
        "Research leads for human review. Scores and clusters do not establish ownership or wrongdoing. Requests remain drafts; nothing is sent."
    )
    base = st.sidebar.text_input(
        "Local API", os.environ.get("FTM_API_URL", "http://127.0.0.1:8765")
    )
    token = st.sidebar.text_input("Reviewer or viewer key", type="password")
    if not token:
        st.info("Enter a locally issued key to open the analyst workspace.")
        return
    try:
        local_url(base)
        with st.expander("Start a replay trace"):
            with st.form("start"):
                chain = st.selectbox("Chain", ["bitcoin", "tron"])
                seed = st.text_input("Seed address", "syn_seed_a")
                calls = st.number_input("Maximum tool queries", 1, 100, 12)
                hops = st.number_input("Maximum hops", 0, 12, 5)
                draft = st.checkbox(
                    "Include a draft information request after approval"
                )
                start = st.form_submit_button("Start trace")
            if start:
                signature = (chain, seed, calls, hops, draft)
                if st.session_state.get("start_signature") != signature:
                    st.session_state.start_id = str(uuid4())
                    st.session_state.start_signature = signature
                case = api_request(
                    base,
                    token,
                    "POST",
                    "/v1/cases",
                    {
                        "chain": chain,
                        "seed": seed,
                        "max_calls": calls,
                        "max_hops": hops,
                        "draft_request": draft,
                        "request_id": st.session_state.start_id,
                    },
                )
                st.session_state.selected = case["case_id"]
                # A completed response starts a new request on a later click; timeouts reuse the UUID.
                st.session_state.pop("start_signature", None)
        rows = api_request(base, token, "GET", "/v1/cases")["cases"]
        if not rows:
            st.info("No cases yet. Start the fictional replay example above.")
            return
        ids = [r["case_id"] for r in rows]
        selected = st.session_state.get("selected")
        case_id = st.selectbox(
            "Case", ids, index=ids.index(selected) if selected in ids else 0
        )
        case = api_request(base, token, "GET", f"/v1/cases/{case_id}")
        st.write("Status:", case["status"])
        state = case.get("state") or {}
        if case["next_action"] == "recover":
            if st.button("Recover interrupted case"):
                api_request(base, token, "POST", f"/v1/cases/{case_id}/recover")
                st.rerun()
            return
        trace, critic, evidence, memory = st.tabs(
            ["Trace", "Critic and claims", "Evidence", "Case memory"]
        )
        with trace:
            st.json(
                {
                    "budget": state.get("budget"),
                    "stop_reason": state.get("stop_reason"),
                    "endpoints": state.get("endpoints"),
                }
            )
            st.dataframe(state.get("trace", []), use_container_width=True)
        with critic:
            outcomes = state.get("critic", [])
            st.metric("Withdrawn claims", sum(not c["retained"] for c in outcomes))
            st.dataframe(outcomes, use_container_width=True)
            st.json(state.get("claims", []))
        with evidence:
            st.json(state.get("evidence", {}))
            st.json(state.get("labels", []))
        with memory:
            st.json(state.get("memory_context", {}))
        if case["status"] == "awaiting_approval":
            digest = state["evidence_sha256"]
            st.code(digest, language=None)
            with st.form("approval"):
                inspected = st.checkbox(
                    "I reviewed the cited transactions, critic objections, and draft-only scope"
                )
                decision = st.radio("Decision", ["reject", "approve"])
                note = st.text_area("Reviewer note", max_chars=1000)
                submit = st.form_submit_button("Record human decision")
            if submit and inspected:
                key = f"decision-{case_id}-{digest}-{decision}-{note}"
                request_id = st.session_state.setdefault(key, str(uuid4()))
                api_request(
                    base,
                    token,
                    "POST",
                    f"/v1/cases/{case_id}/approval",
                    {
                        "request_id": request_id,
                        "evidence_sha256": digest,
                        "decision": decision,
                        "note": note,
                    },
                )
                st.rerun()
            elif submit:
                st.warning("Review the evidence and check the acknowledgement first.")
        else:
            st.json(state.get("report", {}))
        st.download_button(
            "Download case JSON",
            json.dumps(case, indent=2),
            file_name=f"case-{case_id}.json",
            mime="application/json",
        )
    except (ValueError, httpx.HTTPError) as exc:
        st.error(
            str(exc)
            if isinstance(exc, ValueError)
            else "Local API unavailable; retry with the same pending request."
        )


if __name__ == "__main__":
    main()
