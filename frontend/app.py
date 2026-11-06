"""
CheckoutPilot - Streamlit frontend.

Run from the project root folder:
    streamlit run frontend/app.py

Then open http://localhost:8501 in your browser.
The page works even if the backend is not running; it will just show a warning.
"""

import streamlit as st

from api_client import check_backend_health, start_scan

# ---------- Page setup ----------
st.set_page_config(page_title="CheckoutPilot", page_icon="🧭", layout="wide")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("CheckoutPilot")
    st.caption("Find, fix and prove PayPal checkout upgrades.")
    if check_backend_health():
        st.success("Backend: connected")
    else:
        st.warning("Backend: not running. Start it with `uvicorn backend.main:app --reload`.")
    st.divider()
    include_mobile = st.toggle("Also scan mobile view", value=True)

# ---------- Header ----------
st.title("🧭 CheckoutPilot")
st.subheader("AI agent that audits, upgrades and verifies a store's PayPal checkout")
st.write(
    "Paste a store URL. CheckoutPilot walks the checkout like a shopper, finds what holds "
    "PayPal conversion back, ranks the fixes and proves them with a PayPal Sandbox purchase."
)

# ---------- Scan input ----------
col_input, col_button = st.columns([4, 1], vertical_alignment="bottom")
with col_input:
    store_url = st.text_input("Store URL", placeholder="https://your-demo-store.example.com")
with col_button:
    scan_clicked = st.button("Scan", type="primary", use_container_width=True)

if scan_clicked:
    if not store_url.strip():
        st.error("Please enter a store URL first.")
    else:
        with st.spinner("Scanning... (placeholder - real scanning not built yet)"):
            st.session_state["scan_result"] = start_scan(store_url.strip(), include_mobile)

result = st.session_state.get("scan_result")

# ---------- Result sections (placeholders) ----------
tab_audit, tab_recommendations, tab_report = st.tabs(
    ["📋 Audit results", "💡 Recommendations", "📄 Report"]
)

with tab_audit:
    st.markdown("#### Checkout gaps found")
    if result:
        st.info(f"Status: **{result.get('status')}** — {result.get('message')}")
        gaps = result.get("gaps", [])
        if gaps:
            st.dataframe(gaps, use_container_width=True)
        else:
            st.caption("No gaps returned yet. The scanner and AI engine are still placeholders.")
    else:
        st.caption("Run a scan to see audit results here.")
    # TODO: show screenshots per checkout step (desktop and mobile).

with tab_recommendations:
    st.markdown("#### Ranked fixes")
    st.caption("Placeholder: fixes ranked by expected business impact will appear here.")
    # TODO: show ranked gaps with labelled impact assumptions.
    # TODO: add a 'Generate upgrade' button that calls the code agent.

with tab_report:
    st.markdown("#### Verification report")
    st.caption("Placeholder: before/after sandbox purchase results and the pull request link.")
    # TODO: show sandbox verification results and a downloadable report.

st.divider()
st.caption("CheckoutPilot · PayPal AI Hackathon 2026 · Uses the PayPal Sandbox only")
