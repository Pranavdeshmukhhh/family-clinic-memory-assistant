"""
Deterministic drug safety checker — no LLM involvement.

Public API:
    findings = check_prescription(
        patient_allergies=["penicillin"],
        current_meds=["Ecosprin"],
        proposed_items=["Ibugesic 400mg", "Augmentin 625mg"],
    )

Each Finding is a dataclass with:
    severity  : "contraindicated" | "major" | "moderate" | "warning"
    type      : FindingType enum value
    drug      : canonical drug name(s) involved
    reason    : plain English explanation
    source    : always "rule_engine"

The LLM may ONLY receive the list of findings to write a plain-language
summary. It cannot add or remove findings.

Blocking rule (enforced by the doctor router):
    Any "contraindicated" finding MUST be explicitly overridden by the doctor
    (with a written reason). The override is stored in the audit log.

Design notes:
    - Name normalisation strips strengths, map brands -> generic, lowercase.
    - Cross-reactivity rules live in _cross_reactivity section of the KB.
    - Unknown drugs produce a "not_in_kb" warning, NOT silence.
    - Duplicate-therapy detection flags two drugs of the same class.
    - The KB is loaded once at module import; no network calls.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

log = logging.getLogger("clinic.safety")

# -- Load knowledge base once -------------------------------------------------
_KB_PATH = Path(__file__).parent.parent.parent / "data" / "drug_knowledge.json"


def _load_kb() -> dict:
    try:
        with open(_KB_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        log.error("Drug knowledge base not found at %s", _KB_PATH)
        return {}
    except json.JSONDecodeError as exc:
        log.error("Drug knowledge base JSON error: %s", exc)
        return {}


_RAW_KB: dict = _load_kb()

# Separate cross-reactivity rules and metadata comment from drug entries
_CROSS_REACTIVITY: dict = _RAW_KB.pop("_cross_reactivity", {})
_RAW_KB.pop("_comment", "")

# Build brand -> generic lookup (lowercase brand -> canonical key)
_BRAND_TO_GENERIC: dict[str, str] = {}
for _generic, _entry in _RAW_KB.items():
    for _brand in _entry.get("brands", []):
        _BRAND_TO_GENERIC[_brand.lower()] = _generic


# -- Types --------------------------------------------------------------------

class FindingType(str, Enum):
    ALLERGY           = "allergy"           # drug in patient's known allergy list
    CROSS_REACTIVITY  = "cross_reactivity"  # allergen-group cross-reactivity
    INTERACTION       = "interaction"       # drug-drug interaction
    DUPLICATE_THERAPY = "duplicate_therapy" # two drugs of the same class
    NOT_IN_KB         = "not_in_kb"         # drug not found in knowledge base


SEVERITY_RANK: dict[str, int] = {
    "contraindicated": 0,
    "major":           1,
    "moderate":        2,
    "warning":         3,
}


@dataclass
class Finding:
    severity: str          # contraindicated / major / moderate / warning
    type:     FindingType
    drug:     str          # canonical name(s) involved
    reason:   str
    source:   str = field(default="rule_engine", init=False)

    def is_blocking(self) -> bool:
        """Return True if this finding must block approval without an override."""
        return self.severity == "contraindicated"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "type":     self.type.value,
            "drug":     self.drug,
            "reason":   self.reason,
            "source":   self.source,
        }


# -- Normalisation ------------------------------------------------------------
_STRENGTH_RE = re.compile(
    r"\s*\d+\s*(?:mg|mcg|g|ml|iu|%|miu|unit|u)\b.*$",
    re.IGNORECASE,
)


def normalise(name: str) -> str:
    """
    Canonical form of a drug name:
      1. Strip leading/trailing whitespace
      2. Strip dosage strengths (e.g. '500 mg', '5 mcg')
      3. Strip parenthetical formulation notes  e.g. '(SR)', '(film-coated)'
      4. Lowercase
      5. Map brand name -> generic via KB brand lookup
    """
    name = name.strip()
    name = _STRENGTH_RE.sub("", name).strip()
    name = re.sub(r"\s*\([^)]*\)", "", name).strip()
    name = name.lower()
    name = _BRAND_TO_GENERIC.get(name, name)
    return name


def normalise_list(names: list[str]) -> list[str]:
    return [normalise(n) for n in names if n and n.strip()]


# -- Core checker -------------------------------------------------------------

def check_prescription(
    patient_allergies: list[str],
    current_meds: list[str],
    proposed_items: list[str],
) -> list[Finding]:
    """
    Deterministic safety check.  Returns findings sorted by severity.

    Args:
        patient_allergies : known allergy strings (free-text, brand or generic)
        current_meds      : drugs the patient is currently taking
        proposed_items    : drugs being proposed/prescribed

    Returns:
        List[Finding] sorted by severity (contraindicated first).
    """
    findings: list[Finding] = []

    norm_allergies = normalise_list(patient_allergies)
    norm_current   = normalise_list(current_meds)
    norm_proposed  = normalise_list(proposed_items)

    # Collect allergen groups the patient is known to react to
    patient_allergen_groups: set[str] = set()
    for allergy in norm_allergies:
        entry = _RAW_KB.get(allergy)
        if entry:
            patient_allergen_groups.update(entry.get("allergen_groups", []))
        else:
            # The allergy string might itself be a group name (e.g. "penicillin")
            patient_allergen_groups.add(allergy)

    # All drugs in scope for interaction checking
    all_drugs = norm_current + norm_proposed

    # -- Check every proposed drug -------------------------------------------
    for drug in norm_proposed:
        entry = _RAW_KB.get(drug)

        # 1. Unknown drug warning
        if entry is None:
            findings.append(Finding(
                severity="warning",
                type=FindingType.NOT_IN_KB,
                drug=drug,
                reason=(
                    f"'{drug}' is not in the drug knowledge base. "
                    "Safety checks could not be performed for this drug. "
                    "Please verify manually."
                ),
            ))
            continue

        drug_groups = set(entry.get("allergen_groups", []))

        # 2. Direct allergy
        if drug in norm_allergies:
            findings.append(Finding(
                severity="contraindicated",
                type=FindingType.ALLERGY,
                drug=drug,
                reason=(
                    f"Patient has a documented allergy to {drug}. "
                    "Administration is contraindicated."
                ),
            ))

        # 3. Cross-reactivity: patient's allergen groups vs drug's groups
        for rule in _CROSS_REACTIVITY.values():
            if not isinstance(rule, dict) or "from_group" not in rule:
                continue
            from_g = rule["from_group"]
            to_g   = rule["to_group"]
            if from_g in patient_allergen_groups and to_g in drug_groups:
                if drug not in norm_allergies:  # don't duplicate direct allergy
                    findings.append(Finding(
                        severity=rule["severity"],
                        type=FindingType.CROSS_REACTIVITY,
                        drug=drug,
                        reason=rule["reason"],
                    ))

        # 4. Drug-drug interactions (proposed vs ALL drugs in scope)
        interactions: dict = entry.get("interactions", {})
        for other in all_drugs:
            if other == drug:
                continue
            if other in interactions:
                ix   = interactions[other]
                pair = " + ".join(sorted([drug, other]))
                already = any(
                    f.type == FindingType.INTERACTION and f.drug == pair
                    for f in findings
                )
                if not already:
                    findings.append(Finding(
                        severity=ix["severity"],
                        type=FindingType.INTERACTION,
                        drug=pair,
                        reason=ix["reason"],
                    ))

    # 5. Duplicate therapy: two PROPOSED drugs of the same class
    proposed_entries = [
        (drug, _RAW_KB[drug])
        for drug in norm_proposed
        if drug in _RAW_KB
    ]
    for i, (drug_a, entry_a) in enumerate(proposed_entries):
        for drug_b, entry_b in proposed_entries[i + 1:]:
            class_a = entry_a.get("class", "")
            class_b = entry_b.get("class", "")
            if class_a and class_b and class_a == class_b:
                pair = " + ".join(sorted([drug_a, drug_b]))
                findings.append(Finding(
                    severity="major",
                    type=FindingType.DUPLICATE_THERAPY,
                    drug=pair,
                    reason=(
                        f"Both {drug_a} and {drug_b} belong to the same drug "
                        f"class ({class_a}). Concurrent use is usually not indicated."
                    ),
                ))

    # Sort by severity then deduplicate
    findings.sort(key=lambda f: (SEVERITY_RANK.get(f.severity, 9), f.type.value))

    seen: set[tuple] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.severity, f.type, f.drug)
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def has_blocking_findings(findings: list[Finding]) -> bool:
    """True if any finding is contraindicated -- requires doctor override to proceed."""
    return any(f.is_blocking() for f in findings)


def findings_summary(findings: list[Finding]) -> str:
    """
    Read-only plain-text summary for the LLM to paraphrase.
    The LLM MUST NOT add or remove findings.
    """
    if not findings:
        return "No safety concerns identified by the rule engine."
    lines = [f"[{f.severity.upper()}] {f.drug}: {f.reason}" for f in findings]
    return "Safety rule engine findings:\n" + "\n".join(lines)


def extract_allergies_from_memory(memory_text: str) -> list[str]:
    """
    Best-effort heuristic: pull allergy mentions from Hindsight memory text.
    Returns canonical drug names / allergen group names.
    The authoritative allergy list must come from structured patient data.
    """
    if not memory_text:
        return []
    patterns = [
        r"allerg(?:y|ic|ies)\s+to\s+([\w\s,/+\-]+?)(?:\.|,|\n|;|$)",
        r"known\s+allerg(?:y|ies)\s*[:\-]?\s*([\w\s,/+\-]+?)(?:\.|,|\n|;|$)",
        r"adverse\s+reaction\s+to\s+([\w\s,/+\-]+?)(?:\.|,|\n|;|$)",
    ]
    found: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, memory_text, re.IGNORECASE):
            raw = match.group(1).strip()
            # Split on comma, slash, or the word 'and'
            for part in re.split(r"[,/]|\band\b", raw, flags=re.IGNORECASE):
                part = part.strip()
                norm = normalise(part)
                # Only accept tokens that look like drug names (2-30 chars, no spaces)
                if norm and 2 < len(norm) <= 30 and " " not in norm:
                    found.append(norm)
    return list(dict.fromkeys(found))  # unique, order-preserving
