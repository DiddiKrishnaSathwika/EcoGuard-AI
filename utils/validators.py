"""Input validation for the API (pure Python, no framework dependency)."""
import re

INDUSTRIES = ["Textile Manufacturing", "Food Processing", "Automobile", "Chemical Manufacturing",
              "Packaging", "General Manufacturing", "Other"]
STATES = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
          "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
          "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
          "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
          "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry"]
YES_NO = ["Yes", "No", "Unknown"]


class ValidationFailure(Exception):
    def __init__(self, errors):
        super().__init__("Validation failed")
        self.errors = errors


def _text(data, key, errors, max_len, required=False):
    value = data.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            errors[key] = "This field is required."
        return ""
    if not isinstance(value, str):
        errors[key] = "Must be text."
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > max_len:
        errors[key] = f"Must be at most {max_len} characters."
    return value


def _number(data, key, errors):
    value = data.get(key)
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[key] = "Must be a number."
        return None
    if number < 0 or number > 1e9:
        errors[key] = "Must be between 0 and 1,000,000,000."
        return None
    return number


def validate_business_profile(data):
    if not isinstance(data, dict):
        raise ValidationFailure({"_": "Request body must be a JSON object."})
    errors = {}
    out = {"company": _text(data, "company", errors, 150, required=True)}
    for key, options in (("industry", INDUSTRIES), ("state", STATES), ("wastewater", YES_NO),
                         ("air_emissions", YES_NO), ("hazardous_waste", YES_NO)):
        value = data.get(key)
        if value not in options:
            errors[key] = f"Choose one of: {', '.join(options)}."
        out[key] = value
    out["wastewater_volume_lpd"] = _number(data, "wastewater_volume_lpd", errors)
    out["wastewater_treatment"] = _text(data, "wastewater_treatment", errors, 300)
    out["wastewater_disposal"] = _text(data, "wastewater_disposal", errors, 300)
    out["air_sources"] = _text(data, "air_sources", errors, 300)
    out["air_control_equipment"] = _text(data, "air_control_equipment", errors, 300)
    out["hazardous_waste_types"] = _text(data, "hazardous_waste_types", errors, 300)
    out["hazardous_waste_qty_kg_month"] = _number(data, "hazardous_waste_qty_kg_month", errors)
    if out["wastewater"] == "No" and (out["wastewater_volume_lpd"] or 0) > 0:
        errors["wastewater_volume_lpd"] = "Volume given although wastewater is set to No."
    if out["hazardous_waste"] == "No" and (out["hazardous_waste_qty_kg_month"] or 0) > 0:
        errors["hazardous_waste_qty_kg_month"] = "Quantity given although hazardous waste is set to No."
    if errors:
        raise ValidationFailure(errors)
    return out


def validate_assessment_request(data):
    if not isinstance(data, dict):
        raise ValidationFailure({"_": "Request body must be a JSON object."})
    errors = {}
    pid = data.get("profile_id")
    if not isinstance(pid, int) or isinstance(pid, bool):
        errors["profile_id"] = "profile_id (integer) is required."
    ids = data.get("document_ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        errors["document_ids"] = "document_ids must be a list of integers."
    if errors:
        raise ValidationFailure(errors)
    return {"profile_id": pid, "document_ids": ids, "use_ai": bool(data.get("use_ai", False))}


def validate_pdf_bytes(content, filename, max_mb):
    if not filename or not filename.lower().endswith(".pdf"):
        return "Only PDF files are supported."
    if not content:
        return "The uploaded file is empty."
    if len(content) > max_mb * 1024 * 1024:
        return f"File is larger than {max_mb} MB."
    if not content.lstrip()[:5] == b"%PDF-":
        return "The file is not a valid PDF (missing PDF header)."
    return None
