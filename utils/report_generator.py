"""PDF compliance report (ReportLab)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

GREEN, DARK, GREY = colors.HexColor("#15803d"), colors.HexColor("#14532d"), colors.HexColor("#6b7280")
STATUS_COLORS = {"COMPLIANT": "#15803d", "PARTIALLY_COMPLIANT": "#b45309", "NON_COMPLIANT": "#b91c1c",
                 "INSUFFICIENT_EVIDENCE": "#4b5563"}
RISK_COLORS = {"High": "#b91c1c", "Medium": "#b45309", "Low": "#15803d", "Undetermined": "#4b5563"}


def _p(text, style):
    return Paragraph(escape(str(text if text is not None else "")), style)


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], textColor=DARK, fontSize=22, alignment=0, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=ss["Normal"], textColor=GREY, fontSize=10),
        "h1": ParagraphStyle("h1", parent=ss["Heading2"], textColor=DARK, fontSize=14, spaceBefore=14, spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=ss["Heading3"], textColor=colors.black, fontSize=11, spaceBefore=8, spaceAfter=2),
        "body": ParagraphStyle("b", parent=ss["Normal"], fontSize=9.5, leading=13),
        "small": ParagraphStyle("sm", parent=ss["Normal"], fontSize=8, leading=10.5, textColor=GREY),
        "cell": ParagraphStyle("c", parent=ss["Normal"], fontSize=8.5, leading=11),
        "cellb": ParagraphStyle("cb", parent=ss["Normal"], fontSize=8.5, leading=11, textColor=colors.white),
    }


def _table(rows, widths, header=True):
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), GREEN)]
    t.setStyle(TableStyle(style))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 10 * mm, "EcoGuard AI - screening aid, not legal advice. Verify with official sources and your State Pollution Control Board.")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def generate_report_pdf(assessment):
    """assessment: dict from the database (with 'result'); returns PDF bytes."""
    r = assessment["result"]
    st = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title="EcoGuard AI Compliance Report", author="EcoGuard AI")
    W = A4[0] - 36 * mm
    s = []
    prof, overall = r["profile"], r["overall"]
    s += [_p("EcoGuard AI", st["title"]), _p("Environmental Compliance Assessment Report", st["sub"]),
          _p(f"Assessment #{assessment['id']}  |  Assessment date: {r['assessment_date']}  |  Generated: {r['generated_at'][:19].replace('T', ' ')} UTC", st["small"]),
          Spacer(1, 8)]

    s.append(_p("1. Company information", st["h1"]))
    rows = [("Company", prof.get("company")), ("Industry", prof.get("industry")), ("State / UT", prof.get("state")),
            ("Wastewater discharge", prof.get("wastewater")), ("Wastewater details", ", ".join(x for x in [
                f"{prof['wastewater_volume_lpd']:g} L/day" if prof.get("wastewater_volume_lpd") else "",
                prof.get("wastewater_treatment") or "", prof.get("wastewater_disposal") or ""] if x) or "Not provided"),
            ("Air emissions", prof.get("air_emissions")), ("Air emission details", ", ".join(x for x in [prof.get("air_sources") or "", prof.get("air_control_equipment") or ""] if x) or "Not provided"),
            ("Hazardous waste", prof.get("hazardous_waste")), ("Hazardous waste details", ", ".join(x for x in [
                prof.get("hazardous_waste_types") or "", f"{prof['hazardous_waste_qty_kg_month']:g} kg/month" if prof.get("hazardous_waste_qty_kg_month") else ""] if x) or "Not provided"),
            ("Documents analysed", ", ".join(d["filename"] for d in r["documents"]) or "None submitted")]
    t = _table([[_p(k, st["cell"]), _p(v, st["cell"])] for k, v in rows], [42 * mm, W - 42 * mm], header=False)
    s.append(t)

    s.append(_p("2. Overall assessment", st["h1"]))
    c = overall["counts"]
    s.append(_p(f"{overall['label']}  -  highest risk level: {overall['risk_level']}", st["h2"]))
    s.append(_p(overall["summary"], st["body"]))
    s.append(Spacer(1, 4))
    s.append(_table([[_p(h, st["cellb"]) for h in ("Compliant", "Partially compliant", "Non-compliant", "Insufficient evidence", "Not applicable")],
                     [_p(x, st["cell"]) for x in (c["COMPLIANT"], c["PARTIALLY_COMPLIANT"], c["NON_COMPLIANT"], c["INSUFFICIENT_EVIDENCE"], overall["not_applicable"])]],
                    [W / 5] * 5))

    s.append(_p("3. Findings", st["h1"]))
    if not r["findings"]:
        s.append(_p("No applicable requirements were assessed.", st["body"]))
    for f in r["findings"]:
        col = STATUS_COLORS[f["status"]]
        head = Paragraph(f"<b>{escape(f['title'])}</b><br/><font size=8 color='#6b7280'>{escape(f['instrument'])}, {escape(f['citation'])}</font>", st["cell"])
        badge = Paragraph(f"<font color='{col}'><b>{escape(f['status_label'])}</b></font><br/><font size=8 color='{RISK_COLORS[f['risk_level']]}'>Risk: {f['risk_level']}</font>", st["cell"])
        ev = "<br/>".join(f"p.{e['page']} ({escape(e.get('document', ''))}): {escape(e['line'])}" for e in f["evidence"][:3]) or "No evidence found in the submitted documents."
        body = [[head, badge],
                [Paragraph(f"<b>Explanation:</b> {escape(f['explanation'])}", st["cell"]), ""],
                [Paragraph(f"<b>Evidence:</b> {ev}", st["cell"]), ""]]
        if f["missing_information"]:
            body.append([Paragraph("<b>Missing:</b> " + escape("; ".join(f["missing_information"])), st["cell"]), ""])
        if f["notes"]:
            body.append([Paragraph("<b>Notes:</b> " + escape(" ".join(f["notes"])), st["cell"]), ""])
        tb = Table(body, colWidths=[W - 40 * mm, 40 * mm])
        tb.setStyle(TableStyle([("SPAN", (0, i), (1, i)) for i in range(1, len(body))] + [
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d1d5db")), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0fdf4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        s += [KeepTogether([tb]), Spacer(1, 5)]

    s.append(_p("4. Regulatory references", st["h1"]))
    s.append(_p("Summaries below are paraphrased from a curated knowledge base. They are NOT legal text and amendment status has not been verified. "
                f"Knowledge base curated on {r['regulatory_coverage']['curated_on']}.", st["small"]))
    seen, rows = set(), [[_p(h, st["cellb"]) for h in ("Instrument / provision", "Official / reference sources", "Verification")]]
    for f in r["findings"]:
        if f["requirement_id"] in seen:
            continue
        seen.add(f["requirement_id"])
        src = "<br/>".join(f"{escape(x['label'])} [{x['kind'].replace('_', ' ')}]<br/><font size=7 color='#6b7280'>{escape(x['url'])}</font>" for x in f["references"])
        rows.append([Paragraph(f"<b>{escape(f['instrument'])}</b><br/>{escape(f['citation'])}", st["cell"]), Paragraph(src, st["cell"]),
                     Paragraph(escape(f["verification"]["status"].replace("_", " ").title()) + f"<br/>on {f['verification']['verified_on']}", st["cell"])])
    s.append(_table(rows, [48 * mm, W - 78 * mm, 30 * mm]) if len(rows) > 1 else _p("None.", st["body"]))

    s.append(_p("5. Identified gaps", st["h1"]))
    gaps = [f for f in r["findings"] if f["status"] != "COMPLIANT"]
    if gaps:
        for f in gaps:
            s.append(_p(f"- {f['title']} ({f['status_label']}): {f['explanation']}", st["body"]))
    else:
        s.append(_p("No gaps were identified in the submitted evidence for the assessed requirements.", st["body"]))

    s.append(_p("6. Recommendations", st["h1"]))
    if r["recommendations"]:
        rows = [[_p(h, st["cellb"]) for h in ("Priority", "Recommendation", "Why it is needed / actions")]]
        for rec in r["recommendations"]:
            rows.append([Paragraph(f"<b>{escape(rec['priority_label'])}</b><br/>{escape(rec['suggested_timeframe'])}", st["cell"]),
                         Paragraph(escape(rec["title"]), st["cell"]),
                         Paragraph(escape(rec["why"]) + "<br/><b>Actions:</b> " + escape(" ".join(rec["actions"])), st["cell"])])
        s.append(_table(rows, [30 * mm, 42 * mm, W - 72 * mm]))
    else:
        s.append(_p("No corrective actions are required based on the assessed evidence.", st["body"]))

    ai = r.get("ai") or {}
    if ai.get("narrative") or ai.get("interpretations"):
        s.append(_p("7. AI-generated explanations (not verified legal advice)", st["h1"]))
        if ai.get("narrative"):
            s.append(_p(ai["narrative"], st["body"]))
        for item in ai.get("interpretations", []):
            s.append(_p(f"{item['instrument']}: {item['text']}", st["body"]))
        s.append(_p(ai.get("label", "AI-generated text is not verified legal advice."), st["small"]))

    s.append(_p("Limitations and regulatory coverage", st["h1"]))
    for x in r["limitations"] + r["regulatory_coverage"]["limitations"]:
        s.append(_p(f"- {x}", st["small"]))
    doc.build(s, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
