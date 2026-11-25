"""Rule-based applicability of knowledge-base requirements to a business."""
from regulation_engine.knowledge_base import get_entries
from workflows.state import (APPLICABLE, CONDITIONALLY_APPLICABLE,
                             NEEDS_INFORMATION, NOT_APPLICABLE)

FIELD_LABELS = {"wastewater": "wastewater generation", "air_emissions": "air emissions",
                "hazardous_waste": "hazardous waste generation"}


def _document_signal(field, facts):
    if not facts:
        return None
    if field == "wastewater" and facts.get("wastewater_reported"):
        return "Documents report wastewater generation."
    if field == "air_emissions" and facts.get("air_sources"):
        return "Documents mention emission sources (e.g. diesel generator)."
    if field == "hazardous_waste" and facts.get("hazardous_waste_reported") == "reported":
        return "Documents report hazardous waste quantities."
    return None


def check_applicability(profile, merged_facts=None, entries=None):
    results = []
    for e in entries or get_entries():
        field = e["applies_when"]["profile_field"]
        declared = profile.get(field)
        signal = _document_signal(field, merged_facts)
        label = FIELD_LABELS.get(field, field)
        notes, discrepancy = [], None
        if declared == "Yes":
            status, reason = APPLICABLE, f"Business declares {label}."
        elif declared == "Unknown":
            if signal:
                status, reason = APPLICABLE, f"{label.capitalize()} declared as unknown, but evidence found. {signal}"
            else:
                status, reason = NEEDS_INFORMATION, f"{label.capitalize()} is marked Unknown; applicability cannot be decided."
        else:  # "No"
            if signal:
                status, reason = APPLICABLE, f"Declared No, but {signal.lower()}"
                discrepancy = f"Business profile says no {label}, but the uploaded documents indicate otherwise. Review the profile."
            else:
                status, reason = NOT_APPLICABLE, f"Business declares no {label}."
        if status == APPLICABLE and e.get("location_condition"):
            status = CONDITIONALLY_APPLICABLE
            reason += " Applies only if the premises is in a declared air pollution control area."
        results.append({
            "requirement_id": e["id"], "status": status, "reason": reason,
            "conditions_to_confirm": e.get("conditions_to_confirm", []) if status != NOT_APPLICABLE else [],
            "discrepancy": discrepancy,
        })
    return results
