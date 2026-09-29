"""
Safety helpers — purely deterministic, no LLM involved.

Design principle 1: Safety lives in code, not in prompts.
These functions are called by router handlers to enforce hard safety rules
independent of what the LLM suggests.
"""


def has_penicillin_allergy(text: str) -> bool:
    """
    Return True if the recalled patient text indicates a penicillin-class
    allergy.  Amoxicillin is a penicillin-class antibiotic, so an
    Amoxicillin allergy is treated as equivalent.
    """
    lower = text.lower()
    return (
        ("penicillin" in lower and "allerg" in lower)
        or ("amoxicillin" in lower and "allerg" in lower)
    )


def is_penicillin_class(medicine_name: str) -> bool:
    """
    Return True if the medicine name belongs to the penicillin drug class.
    Used for cross-checking prescriptions against known allergies.
    """
    lower = medicine_name.lower()
    penicillin_keywords = [
        "amoxicillin", "ampicillin", "penicillin", "oxacillin",
        "cloxacillin", "dicloxacillin", "flucloxacillin", "piperacillin",
        "amoxicillin+clavulanate", "co-amoxiclav",
    ]
    return any(kw in lower for kw in penicillin_keywords)
