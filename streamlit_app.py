#!/usr/bin/env python3
"""
Streamlit UI for Fabric Data Agent Client

This app provides a simple UI to interact with the Fabric Data Agent via the
existing FabricDataAgentClient in `fabric_data_agent_client.py`.

Features:
- Configure TENANT_ID, DATA_AGENT_URL, and optional AUTH_TOKEN in the sidebar
- Two modes: Simple (ask) and Detailed (get_run_details with optional analysis info)
- Persists authenticated client across interactions via session_state
- Renders previews when available (e.g., tables or structured text)
"""

import os
import sys
import textwrap
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

# Make sure we can import the local client when running via `streamlit run`
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from fabric_data_agent_client import FabricDataAgentClient

# Load .env at startup (does not override pre-set env)
load_dotenv(override=False)


def _init_client(tenant_id: str, data_agent_url: str, auth_token: Optional[str]):
    """Initialize and return a FabricDataAgentClient instance."""
    return FabricDataAgentClient(
        tenant_id=tenant_id,
        data_agent_url=data_agent_url,
        auth_token=auth_token,
    )


def _get_session_client(tenant_id: str, data_agent_url: str, auth_token: Optional[str]):
    """Get or create a client and keep it stable in the session unless config changes."""
    # Detect configuration change
    cfg = {
        "tenant_id": tenant_id or "",
        "data_agent_url": data_agent_url or "",
        "auth_token": auth_token or "",
    }

    if "client_cfg" not in st.session_state or st.session_state.get("client_cfg") != cfg:
        st.session_state["client_cfg"] = cfg
        st.session_state["fabric_client"] = None

    if st.session_state.get("fabric_client") is None:
        with st.spinner("Initializing client and authenticating (browser may open)..."):
            st.session_state["fabric_client"] = _init_client(
                tenant_id=tenant_id,
                data_agent_url=data_agent_url,
                auth_token=auth_token,
            )
    return st.session_state["fabric_client"]


def _render_data_preview(preview):
    """Render preview which may be a markdown table string or list of lines."""
    if not preview:
        return
    if isinstance(preview, list):
        # If it's list-of-lines, try to join and render as markdown
        text = "\n".join(preview)
        st.markdown(text)
    elif isinstance(preview, str):
        st.markdown(preview)
    else:
        st.write(preview)


def main():
    st.set_page_config(page_title="Fabric Data Agent UI", page_icon="🤖", layout="wide")
    st.title("🤖 Fabric Data Agent UI")
    st.caption("Interact with your Microsoft Fabric Data Agent using a simple Streamlit app.")

    # Sidebar configuration
    st.sidebar.header("Configuration")

    # Read defaults from environment to reduce friction
    default_tenant = os.getenv("TENANT_ID", "")
    default_agent_url = os.getenv("DATA_AGENT_URL", "")
    default_auth_token = os.getenv("AUTH_TOKEN", "")

    tenant_id = st.sidebar.text_input("Tenant ID", value=default_tenant, placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")
    data_agent_url = st.sidebar.text_input("Data Agent URL", value=default_agent_url, placeholder="https://<your-agent-endpoint>")
    auth_token = st.sidebar.text_input("Auth Token (optional)", value=default_auth_token, type="password", help="If provided, token-based auth will be used. Leave empty for interactive browser auth.")

    mode = st.sidebar.radio("Mode", ["Simple", "Detailed"], help="Simple = quick answer. Detailed = run details and agent analysis when available.")
    timeout = st.sidebar.slider("Timeout (seconds)", min_value=30, max_value=300, value=120, step=10)

    st.sidebar.markdown("---")
    st.sidebar.info(
        "Authentication uses either the provided token or interactive browser login.\n"
        "If interactive login is used, your browser may open for Microsoft sign-in."
    )

    # Sample healthcare questions (quick-fill)
    SAMPLE_QUESTIONS = [
        "Summarize monthly hospital admissions for 2023 and highlight peak months.",
        "What are the top 10 medications by total prescriptions in 2022?",
        "Compare 30-day readmission rates across hospitals and identify outliers.",
        "Show the average length of stay by diagnosis group and age band.",
        "List the top 5 procedures by cost and their year-over-year trend.",
        "Which states have the highest per-capita spending on diabetes care?",
        "Find anomalies in ER visit volumes over the last 12 months.",
        "Provide a breakdown of claims by payer type and specialty.",
    ]

    # Main query input
    with st.container():
        st.subheader("Ask a question")
        user_query = st.text_area(
            "Your question",
            key="user_query",
            height=120,
            placeholder="e.g., Summarize monthly hospital admissions for 2023 and highlight peak months.",
        )
        col1, col2 = st.columns([1,1])
        with col1:
            run_btn = st.button("Run", type="primary")
        with col2:
            clear_btn = st.button("Clear")

    with st.expander("Sample healthcare questions"):
        for q in SAMPLE_QUESTIONS:
            if st.button(f"Use: {q}"):
                st.session_state["user_query"] = q
                st.experimental_rerun()

    if clear_btn:
        st.session_state.pop("last_result", None)
        st.session_state.pop("last_error", None)
        st.experimental_rerun()

    # Validate required config
    missing_cfg = []
    if not tenant_id:
        missing_cfg.append("TENANT_ID")
    if not data_agent_url:
        missing_cfg.append("DATA_AGENT_URL")

    if missing_cfg:
        st.warning("Missing configuration: " + ", ".join(missing_cfg) + ". Please fill in the sidebar.")
        st.stop()

    if run_btn:
        if not user_query or not user_query.strip():
            st.warning("Please enter a question to ask.")
        else:
            try:
                client = _get_session_client(tenant_id, data_agent_url, auth_token or None)

                if mode == "Simple":
                    with st.spinner("Querying data agent..."):
                        response = client.ask(user_query.strip(), timeout=timeout)
                    st.session_state["last_result"] = {"mode": mode, "response": response}
                    st.session_state.pop("last_error", None)
                else:
                    with st.spinner("Running detailed analysis (this may take a bit)..."):
                        details = client.get_run_details(user_query.strip())
                    st.session_state["last_result"] = {"mode": mode, "details": details}
                    st.session_state.pop("last_error", None)
            except Exception as e:
                st.session_state["last_error"] = str(e)

    # Show results
    if st.session_state.get("last_error"):
        st.error(st.session_state.get("last_error"))

    last = st.session_state.get("last_result")
    if last:
        if last.get("mode") == "Simple":
            st.subheader("Response")
            st.write(last.get("response", "No response."))
        else:
            details = last.get("details", {})
            if not details or "error" in details:
                st.error(details.get("error", "No details available."))
            else:
                st.subheader("Run Summary")
                cols = st.columns(3)
                cols[0].metric("Status", details.get("run_status", "-"))
                try:
                    cols[1].metric("Steps", len(details.get("run_steps", {}).get("data", [])))
                except Exception:
                    cols[1].metric("Steps", "-")
                try:
                    cols[2].metric("Messages", len(details.get("messages", {}).get("data", [])))
                except Exception:
                    cols[2].metric("Messages", "-")

                # Agent final message if available
                messages = details.get("messages", {}).get("data", [])
                assistant_messages = [m for m in messages if m.get("role") == "assistant"]
                if assistant_messages:
                    st.markdown("### Agent Response")
                    latest_message = assistant_messages[-1]
                    content = latest_message.get("content", [])
                    if content:
                        item = content[0]
                        # multiple shapes possible; try common ones
                        if isinstance(item, dict) and "text" in item:
                            txt = item["text"]["value"] if isinstance(item["text"], dict) and "value" in item["text"] else str(item["text"])
                            st.write(txt)
                        else:
                            st.write(str(item))

                # Optional analysis details (if available)
                if details.get("sql_queries"):
                    st.markdown("### Query Analysis")
                    st.code("\n\n".join(details.get("sql_queries")), language="sql")

                if details.get("data_retrieval_query"):
                    st.markdown("#### Data Retrieval Query (if applicable)")
                    st.code(details.get("data_retrieval_query"), language="sql")

                previews = details.get("sql_data_previews")
                if previews:
                    st.markdown("### Data Preview (if available)")
                    # Choose the retrieval preview if index is given, else show first non-empty
                    idx = details.get("data_retrieval_query_index")
                    preview_to_show = None
                    if isinstance(idx, int) and idx > 0 and idx <= len(previews):
                        preview_to_show = previews[idx - 1]
                    else:
                        for pv in previews:
                            if pv:
                                preview_to_show = pv
                                break
                    _render_data_preview(preview_to_show)

    # Footer help
    st.markdown("---")
    with st.expander("Help & Tips"):
        st.markdown(
            textwrap.dedent(
                f"""
                - Ensure `TENANT_ID` and `DATA_AGENT_URL` are correct. You can also set them in a `.env` file in `{APP_DIR}`.
                - If you set `AUTH_TOKEN`, the client will use token-based auth; otherwise it will open a browser for interactive login.
                - Use Detailed mode to introspect the run. Depending on your agent's tools, you may see additional analysis such as SQL and data previews when applicable.
                - If you encounter auth issues, try clearing the token field to force interactive login.
                """
            )
        )


if __name__ == "__main__":
    main()
