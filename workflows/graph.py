"""Assessment workflow: profile -> documents -> retrieval -> applicability ->
compliance -> recommendations -> ethics review.

Uses LangGraph when installed, otherwise an equivalent sequential runner."""
from datetime import date, datetime, timezone

from agents.compliance_agent import assess_compliance, generate_ai_explanations, summarize_overall
from agents.ethics_agent import review_assessment
from agents.fact_extractor import TOPIC_LABELS, extract_facts, merge_document_facts
from agents.llm_utils import AI_UNAVAILABLE_MESSAGE, llm_status
from agents.recommendation_agent import generate_recommendations
from rag.retriever import retrieve_regulations
from regulation_engine.applicability_checker import check_applicability
from regulation_engine.knowledge_base import get_entries, load_knowledge_base
from workflows.state import STANDARD_LIMITATIONS, AssessmentState


def _d(state):
    return date.fromisoformat(state["assessment_date"])


def node_documents(state):
    per_doc = []
    for doc in state.get("documents", []):
        if doc.get("text"):
            per_doc.append((doc["filename"], extract_facts(doc["text"], _d(state))))
    state["document_facts"] = merge_document_facts(per_doc)
    state["trace"].append(f"Analysed {len(per_doc)} document(s) with the evidence extractor.")
    return state


def node_retrieve(state):
    labels = [TOPIC_LABELS[t] for t, v in state["document_facts"]["topics"].items() if v["status"] != "none"]
    text = " ".join(d.get("text", "")[:800] for d in state.get("documents", []))
    state["retrieved"] = retrieve_regulations(state["profile"], get_entries(), labels, text)
    state["trace"].append(f"Retrieved regulations using {state['retrieved']['method']}.")
    return state


def node_applicability(state):
    state["applicability"] = check_applicability(state["profile"], state["document_facts"])
    state["trace"].append("Checked applicability of each requirement.")
    return state


def node_compliance(state):
    entries = get_entries()
    state["findings"] = assess_compliance(entries, state["applicability"], state["document_facts"])
    state["overall"] = summarize_overall(state["findings"], state["applicability"])
    state["trace"].append(f"Assessed {len(state['findings'])} applicable requirement(s).")
    return state


def node_recommend(state):
    state["recommendations"] = generate_recommendations(state["findings"], state["applicability"])
    state["trace"].append(f"Generated {len(state['recommendations'])} recommendation(s).")
    return state


def node_ai(state):
    status = llm_status()
    ai = {
        "requested": bool(state.get("use_ai")),
        "available": status["available"],
        "model": status["model"],
        "narrative": None,
        "interpretations": [],
        "errors": [],
        "label": "AI-generated explanations; not verified legal advice. Deterministic findings and statuses are unchanged.",
    }
    if state.get("use_ai"):
        if status["available"]:
            explanations = generate_ai_explanations(
                state["profile"],
                state["findings"],
                state["overall"],
                get_entries(),
                state["applicability"],
            )
            if explanations["ok"]:
                ai["narrative"] = explanations["narrative"]
                ai["interpretations"] = explanations["interpretations"]
            else:
                ai["errors"] = [AI_UNAVAILABLE_MESSAGE]
                ai["available"] = False
        else:
            ai["errors"] = [AI_UNAVAILABLE_MESSAGE]
    state["ai"] = ai
    state["trace"].append(
        "Generated OpenRouter explanations." if ai["narrative"]
        else "AI explanations skipped or unavailable."
    )
    return state


def node_finalize(state):
    kb = load_knowledge_base()
    used = {f["requirement_id"] for f in state["findings"]}
    ranks = {r["requirement_id"]: r for r in state["retrieved"]["results"]}
    regs = []
    for e in get_entries():
        regs.append({"id": e["id"], "title": e["title"], "instrument": e["instrument"], "citation": e["citation"],
                     "summary": e["summary"], "sources": e["sources"], "verification": e["verification"],
                     "assessed": e["id"] in used, "relevance_score": ranks.get(e["id"], {}).get("score"),
                     "relevance_rank": ranks.get(e["id"], {}).get("rank")})
    result = {
        "assessment_date": state["assessment_date"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": state["profile"],
        "documents": [{"id": d.get("id"), "filename": d["filename"], "pages": d.get("pages")} for d in state.get("documents", [])],
        "overall": state["overall"], "applicability": state["applicability"], "findings": state["findings"],
        "recommendations": state["recommendations"], "regulations": regs,
        "retrieval": {k: state["retrieved"][k] for k in ("method", "note")},
        "regulatory_coverage": {"jurisdiction": kb["jurisdiction"], "curated_on": kb["curated_on"],
                                "disclaimer": kb["disclaimer"], "limitations": kb["coverage_limitations"]},
        "ai": state["ai"], "limitations": STANDARD_LIMITATIONS, "trace": state["trace"],
        "documents_analysed": len(state.get("documents", [])),
    }
    if not state.get("documents"):
        result["limitations"] = ["No documents were supplied: every requirement is reported as insufficient evidence."] + STANDARD_LIMITATIONS
    result["ethics_review"] = review_assessment(result)
    state["result"] = result
    return state


NODES = [("documents", node_documents), ("retrieve", node_retrieve), ("applicability", node_applicability),
         ("compliance", node_compliance), ("recommend", node_recommend), ("ai", node_ai), ("finalize", node_finalize)]


def _build_langgraph():
    from langgraph.graph import END, StateGraph
    g = StateGraph(AssessmentState)
    for name, fn in NODES:
        g.add_node(name, fn)
    g.set_entry_point(NODES[0][0])
    for (a, _), (b, _) in zip(NODES, NODES[1:]):
        g.add_edge(a, b)
    g.add_edge(NODES[-1][0], END)
    return g.compile()


def run_assessment(profile, documents, assessment_date=None, use_ai=False):
    state = {"profile": profile, "documents": documents, "use_ai": use_ai, "trace": [],
             "assessment_date": (assessment_date or date.today()).isoformat()}
    try:
        graph = _build_langgraph()
    except ImportError:
        graph = None
    if graph is not None:
        state, engine = graph.invoke(state), "langgraph"
    else:
        engine = "sequential"
        for _, fn in NODES:
            state = fn(state)
    result = state["result"]
    result["workflow_engine"] = engine
    return result
