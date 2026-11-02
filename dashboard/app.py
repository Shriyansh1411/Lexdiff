"""Lexdiff dashboard (Streamlit). Run with:  python -m lexdiff dashboard   or   streamlit run dashboard/app.py

Shows the certificate and every stage's output, lets a named human approve obligations, and can run the
whole pipeline on the bundled demo. All logic lives in the lexdiff package; this file is only a view.
"""
import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lexdiff.llm import LLMClient  # noqa: E402
from lexdiff.obligations import approve, load_obligations  # noqa: E402
from lexdiff.pipeline import Workspace, run_pipeline  # noqa: E402

GRADE_ICON = {"Verified": "🟢", "Partially verified": "🔵", "Unverified": "🔴", "Human review required": "🟡"}


def _args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    known, _ = ap.parse_known_args()
    return known


def _load(ws: Workspace, name: str):
    p = ws.out / name
    return json.loads(p.read_text()) if p.exists() else None


def main():
    args = _args()
    root = Path(args.root)
    ws = Workspace(root)
    st.set_page_config(page_title="Lexdiff", layout="wide")
    st.title("Lexdiff")
    st.caption("Diff the law. Test the code. AI proposes; deterministic checks decide.")

    with st.sidebar:
        st.header("Run the pipeline")
        base = st.text_input("Base (directory or repo@ref)", str(root / "demo" / "lendwise_base"))
        head = st.text_input("Head (directory or repo@ref)", str(root / "demo" / "lendwise_fixed"))
        reg_old = st.text_input("Regulation, old", str(root / "data" / "regulation" / "ftc_safeguards_2021-01-01.txt"))
        reg_new = st.text_input("Regulation, new", str(root / "data" / "regulation" / "ftc_safeguards_2026-09-01.txt"))
        approver = st.text_input("Approver (a named human)", "")
        client = LLMClient()
        st.caption(f"LLM provider: **{client.provider}**" + ("" if client.online else " (deterministic offline drafter)"))
        if st.button("Run all 9 stages", type="primary"):
            buf = io.StringIO()
            with redirect_stdout(buf):
                result = run_pipeline(root, base, head, reg_old, reg_new, approver.strip(), client, log=print)
            st.session_state["log"] = buf.getvalue()
            if "stopped" in result:
                st.warning("Obligations drafted but not approved. Enter an approver name and run again.")

    cert = _load(ws, "certificate.json")
    tabs = st.tabs(["Certificate", "Redline", "Obligations", "Code graph", "Canary", "Guard", "Run log"])

    with tabs[0]:
        if not cert:
            st.info("No certificate yet. Run the pipeline from the sidebar.")
        else:
            cols = st.columns(4)
            for col, (grade, n) in zip(cols, cert["summary"].items()):
                col.metric(f"{GRADE_ICON[grade]} {grade}", n)
            c = cert["canary"]
            st.metric("Canary hits (base → fix)", f"{c['base_hits']} → {c['head_hits']}")
            for ob in cert["obligations"]:
                with st.expander(f"{GRADE_ICON[ob['grade']]} {ob['id']} · {ob['clause']} · {ob['grade']}"):
                    st.write(ob["note"])
                    st.caption(f"Quote: “{ob['quote']}”  ·  approved by {ob['approved_by'] or 'n/a'}")
                    if ob["tests"]:
                        st.dataframe(ob["tests"], use_container_width=True)
            st.warning(" ".join(cert["caveats"][:1]))
            st.download_button("Download certificate (JSON)", json.dumps(cert, indent=2), "certificate.json")
            html_path = ws.out / "certificate.html"
            if html_path.exists():
                st.download_button("Download certificate (HTML)", html_path.read_text(), "certificate.html")

    with tabs[1]:
        red = _load(ws, "redline.json")
        if red:
            st.write(f"{red['old_words']} → {red['new_words']} words")
            for ch in red["changes"]:
                st.markdown(f"**{ch['kind']}** · §{ch['key']}")
                st.code(ch["new_text"] or ch["old_text"], language="text")
        else:
            st.info("No redline yet.")

    with tabs[2]:
        obligations = load_obligations(ws.obligations) if ws.obligations.exists() else []
        if not obligations:
            st.info("No obligations yet.")
        for ob in obligations:
            st.markdown(f"**{ob.id}** · §{ob.clause} · `{ob.status}`")
            st.code(ob.quote, language="text")
            if ob.status != "approved" and st.button(f"Approve {ob.id} as {approver or '…'}", key=ob.id):
                if approver.strip():
                    approve(ws.obligations, ob.id, approver.strip())
                    st.rerun()
                else:
                    st.error("Enter an approver name in the sidebar first.")

    with tabs[3]:
        graph = _load(ws, "graph.json")
        if graph:
            st.json(graph["stats"])
            st.subheader("Routes")
            st.dataframe(graph["routes"], use_container_width=True)
            st.subheader("Traces of sensitive data")
            for t in graph["traces"]:
                st.code(t, language="text")
        else:
            st.info("No graph yet.")

    with tabs[4]:
        before = _load(ws, "canary_base.json")
        if before:
            st.json(before["by_store"])
            st.dataframe(before["hits"], use_container_width=True)
        else:
            st.info("No canary run yet.")

    with tabs[5]:
        ver = _load(ws, "verification.json")
        if ver:
            st.write(f"Guard findings on the fix: **{len(ver['guard_head'])}**")
            st.dataframe(ver["guard_head"], use_container_width=True)
            st.write("Fail-before / pass-after")
            st.dataframe([{"test": k, **v} for k, v in ver["tests"].items()], use_container_width=True)
        else:
            st.info("No verification yet.")

    with tabs[6]:
        st.code(st.session_state.get("log", "Nothing run in this session."), language="text")


main()
