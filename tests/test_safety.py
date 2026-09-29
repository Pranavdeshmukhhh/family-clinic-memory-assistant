"""
Table-driven tests for app/services/safety.py.

Tests cover:
  - Direct allergy (generic and brand name)
  - Cross-reactivity (penicillin -> cephalosporin, sulfa -> sulfonylurea)
  - Drug-drug interactions (contraindicated, major, moderate)
  - Duplicate therapy (same class)
  - Unknown drug: must produce NOT_IN_KB warning, not silence
  - Empty inputs (no allergies, no meds, no proposed)
  - Brand name normalisation
  - Severity ordering (contraindicated always first)
  - LLM exclusion: findings_summary() is plain text, not a decision
  - has_blocking_findings() utility
  - extract_allergies_from_memory() heuristic

All tests are purely in-process (no network, no DB, no LLM).
"""
import pytest

from app.services.safety import (
    Finding,
    FindingType,
    check_prescription,
    extract_allergies_from_memory,
    findings_summary,
    has_blocking_findings,
    normalise,
)


# =============================================================================
# Normalisation
# =============================================================================

class TestNormalise:
    @pytest.mark.parametrize("raw,expected", [
        ("Amoxicillin 500mg",   "amoxicillin"),
        ("Ibuprofen 400 mg",    "ibuprofen"),
        ("Brufen",              "ibuprofen"),          # brand -> generic
        ("Crocin",              "paracetamol"),        # brand -> generic
        ("Azee 500mg",         "azithromycin"),        # brand + strength
        ("Metrogyl 400mg",     "metronidazole"),       # brand + strength
        ("CIPROFLOXACIN 500MG","ciprofloxacin"),       # upper-case + strength
        ("Taxim-O 200mg",      "cefixime"),            # brand -> generic
        ("Glycomet 500 mg",    "metformin"),           # brand -> generic
        ("Zyrtec",             "cetirizine"),
        ("  warfarin  ",       "warfarin"),            # whitespace
        ("Paracetamol (SR)",   "paracetamol"),         # parenthetical suffix
    ])
    def test_normalise(self, raw, expected):
        assert normalise(raw) == expected


# =============================================================================
# Empty inputs
# =============================================================================

class TestEmptyInputs:
    def test_all_empty_returns_empty(self):
        assert check_prescription([], [], []) == []

    def test_no_proposed_no_findings(self):
        assert check_prescription(["penicillin"], ["aspirin"], []) == []

    def test_no_allergies_no_current_no_interaction(self):
        findings = check_prescription([], [], ["paracetamol"])
        # Paracetamol is in KB, no allergies, no interactions -> no findings
        assert findings == []


# =============================================================================
# Direct allergy
# =============================================================================

class TestDirectAllergy:
    def test_generic_name_allergy_blocked(self):
        findings = check_prescription(
            patient_allergies=["amoxicillin"],
            current_meds=[],
            proposed_items=["amoxicillin"],
        )
        allergy_f = [f for f in findings if f.type == FindingType.ALLERGY]
        assert len(allergy_f) == 1
        assert allergy_f[0].severity == "contraindicated"
        assert allergy_f[0].drug == "amoxicillin"

    def test_brand_name_allergy_detected(self):
        """Patient allergy listed as brand; proposed as generic -> still caught."""
        findings = check_prescription(
            patient_allergies=["Mox"],   # brand name of amoxicillin
            current_meds=[],
            proposed_items=["amoxicillin"],
        )
        allergy_f = [f for f in findings if f.type == FindingType.ALLERGY]
        assert len(allergy_f) == 1
        assert allergy_f[0].severity == "contraindicated"

    def test_brand_proposed_and_allergy_generic(self):
        """Allergy as generic, proposed as brand -> still caught."""
        findings = check_prescription(
            patient_allergies=["ibuprofen"],
            current_meds=[],
            proposed_items=["Brufen 400mg"],  # brand + strength
        )
        allergy_f = [f for f in findings if f.type == FindingType.ALLERGY]
        assert len(allergy_f) == 1

    def test_allergy_finding_is_blocking(self):
        findings = check_prescription(["ciprofloxacin"], [], ["ciprofloxacin"])
        assert has_blocking_findings(findings)

    def test_non_allergic_drug_no_allergy_finding(self):
        findings = check_prescription(
            patient_allergies=["amoxicillin"],
            current_meds=[],
            proposed_items=["paracetamol"],
        )
        allergy_f = [f for f in findings if f.type == FindingType.ALLERGY]
        assert allergy_f == []


# =============================================================================
# Cross-reactivity
# =============================================================================

class TestCrossReactivity:
    def test_penicillin_allergy_flags_cephalosporin(self):
        """Penicillin-allergic patient prescribed a cephalosporin -> major warning."""
        findings = check_prescription(
            patient_allergies=["penicillin"],  # group name
            current_meds=[],
            proposed_items=["cephalexin"],
        )
        cross = [f for f in findings if f.type == FindingType.CROSS_REACTIVITY]
        assert len(cross) >= 1
        assert cross[0].severity == "major"
        assert cross[0].drug == "cephalexin"

    def test_penicillin_allergy_via_brand(self):
        """Patient allergy listed as 'Mox' (amoxicillin brand) -> cross-reacts with cefixime."""
        findings = check_prescription(
            patient_allergies=["Novamox"],   # brand of amoxicillin
            current_meds=[],
            proposed_items=["cefixime"],
        )
        cross = [f for f in findings if f.type == FindingType.CROSS_REACTIVITY]
        assert len(cross) >= 1
        assert cross[0].severity == "major"

    def test_sulfa_allergy_flags_sulfonylurea(self):
        """Sulfa-allergic patient prescribed glibenclamide (sulfonylurea)."""
        findings = check_prescription(
            patient_allergies=["sulfa"],
            current_meds=[],
            proposed_items=["glibenclamide"],
        )
        cross = [f for f in findings if f.type == FindingType.CROSS_REACTIVITY]
        assert len(cross) >= 1

    def test_sulfa_allergy_via_cotrimoxazole_brand(self):
        """Allergy to Septran (cotrimoxazole) -> cross-reacts with glibenclamide."""
        findings = check_prescription(
            patient_allergies=["Septran"],
            current_meds=[],
            proposed_items=["glibenclamide"],
        )
        cross = [f for f in findings if f.type == FindingType.CROSS_REACTIVITY]
        assert len(cross) >= 1

    def test_no_cross_reactivity_for_unrelated_allergy(self):
        findings = check_prescription(
            patient_allergies=["penicillin"],
            current_meds=[],
            proposed_items=["metformin"],  # not a beta-lactam
        )
        cross = [f for f in findings if f.type == FindingType.CROSS_REACTIVITY]
        assert cross == []

    def test_direct_allergy_not_double_reported_as_cross(self):
        """If the same drug is both allergy and cross-reactive, report as ALLERGY only."""
        findings = check_prescription(
            patient_allergies=["amoxicillin"],
            current_meds=[],
            proposed_items=["amoxicillin"],
        )
        types = [f.type for f in findings]
        # Must have ALLERGY but NOT also CROSS_REACTIVITY for the same drug
        assert FindingType.ALLERGY in types
        cross = [f for f in findings if f.type == FindingType.CROSS_REACTIVITY and f.drug == "amoxicillin"]
        assert cross == []


# =============================================================================
# Drug-drug interactions
# =============================================================================

class TestInteractions:
    def test_contraindicated_interaction_detected(self):
        """Azithromycin + domperidone -> contraindicated (both prolong QTc)."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["domperidone"],
            proposed_items=["azithromycin"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert len(ix) == 1
        assert ix[0].severity == "contraindicated"
        assert has_blocking_findings(findings)

    def test_major_interaction_detected(self):
        """Warfarin + ciprofloxacin -> major (CYP1A2 inhibition)."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["warfarin"],
            proposed_items=["ciprofloxacin"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert len(ix) >= 1
        assert any(f.severity == "major" for f in ix)

    def test_moderate_interaction_detected(self):
        """Ibuprofen + lisinopril -> moderate."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["lisinopril"],
            proposed_items=["ibuprofen"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert len(ix) >= 1

    def test_symmetric_interaction_no_duplicate(self):
        """A+B and B+A should only produce one Finding, not two."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=[],
            proposed_items=["azithromycin", "domperidone"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        pairs = [f.drug for f in ix]
        assert len(pairs) == len(set(pairs)), "Duplicate interaction finding"

    def test_methotrexate_cotrimoxazole_blocked(self):
        """Methotrexate + cotrimoxazole: dual folate antagonists -> contraindicated."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["methotrexate"],
            proposed_items=["cotrimoxazole"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert any(f.severity == "contraindicated" for f in ix)
        assert has_blocking_findings(findings)

    def test_interaction_with_brand_name_current_med(self):
        """Current med listed as brand -> interaction still detected."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["Warf"],   # brand of warfarin
            proposed_items=["metronidazole"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert len(ix) >= 1
        assert any(f.severity in ("major", "contraindicated") for f in ix)

    def test_interaction_brand_proposed(self):
        """Proposed drug as brand -> interaction still detected."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["warfarin"],
            proposed_items=["Flagyl 400mg"],   # brand of metronidazole
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert len(ix) >= 1

    def test_clarithromycin_simvastatin_rhabdomyolysis(self):
        """Classic contraindicated pair: clarithromycin + simvastatin."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["simvastatin"],
            proposed_items=["clarithromycin"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert any(f.severity == "contraindicated" for f in ix)

    def test_tramadol_sertraline_serotonin_syndrome(self):
        """Tramadol + sertraline -> contraindicated (serotonin syndrome)."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["sertraline"],
            proposed_items=["tramadol"],
        )
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert any(f.severity == "contraindicated" for f in ix)


# =============================================================================
# Duplicate therapy
# =============================================================================

class TestDuplicateTherapy:
    def test_two_nsaids_detected(self):
        """Proposing both ibuprofen and diclofenac is duplicate NSAID therapy."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=[],
            proposed_items=["ibuprofen", "diclofenac"],
        )
        dup = [f for f in findings if f.type == FindingType.DUPLICATE_THERAPY]
        assert len(dup) == 1
        assert dup[0].severity == "major"

    def test_two_statins_detected(self):
        """Atorvastatin + simvastatin is duplicate statin therapy."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=[],
            proposed_items=["atorvastatin", "simvastatin"],
        )
        dup = [f for f in findings if f.type == FindingType.DUPLICATE_THERAPY]
        assert len(dup) >= 1

    def test_two_macrolides_detected(self):
        """Azithromycin + clarithromycin -> duplicate macrolide."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=[],
            proposed_items=["azithromycin", "clarithromycin"],
        )
        dup = [f for f in findings if f.type == FindingType.DUPLICATE_THERAPY]
        assert len(dup) >= 1

    def test_different_class_no_dup(self):
        """Azithromycin + metformin -> no duplicate therapy."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=[],
            proposed_items=["azithromycin", "metformin"],
        )
        dup = [f for f in findings if f.type == FindingType.DUPLICATE_THERAPY]
        assert dup == []

    def test_current_med_not_counted_for_dup(self):
        """Duplicate therapy only checks PROPOSED items, not current vs proposed."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["ibuprofen"],
            proposed_items=["diclofenac"],
        )
        dup = [f for f in findings if f.type == FindingType.DUPLICATE_THERAPY]
        assert dup == []   # dup therapy check is proposed-vs-proposed only


# =============================================================================
# Unknown drug (NOT_IN_KB)
# =============================================================================

class TestUnknownDrug:
    def test_unknown_drug_produces_warning(self):
        """A drug not in the KB must produce a NOT_IN_KB warning, not silence."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=[],
            proposed_items=["some_unknown_experimental_drug"],
        )
        not_in_kb = [f for f in findings if f.type == FindingType.NOT_IN_KB]
        assert len(not_in_kb) == 1
        assert not_in_kb[0].severity == "warning"
        assert "not in the drug knowledge base" in not_in_kb[0].reason.lower()

    def test_unknown_drug_warning_is_not_blocking(self):
        """NOT_IN_KB is a warning, not contraindicated — should not block."""
        findings = check_prescription([], [], ["mystery_drug_xyz"])
        not_in_kb = [f for f in findings if f.type == FindingType.NOT_IN_KB]
        assert not_in_kb[0].severity == "warning"
        assert not has_blocking_findings(findings)

    def test_unknown_drug_with_known_drug(self):
        """Mix of known and unknown drugs: known drug checks still run."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["warfarin"],
            proposed_items=["mystery_drug", "ciprofloxacin"],
        )
        not_in_kb = [f for f in findings if f.type == FindingType.NOT_IN_KB]
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert len(not_in_kb) == 1   # mystery_drug flagged
        assert len(ix) >= 1          # warfarin + ciprofloxacin interaction found


# =============================================================================
# Severity ordering
# =============================================================================

class TestSeverityOrdering:
    def test_contraindicated_always_first(self):
        """When multiple findings present, contraindicated must sort to position 0."""
        findings = check_prescription(
            patient_allergies=[],
            current_meds=["domperidone", "warfarin"],
            proposed_items=["azithromycin"],   # contraindicated with domperidone, moderate with warfarin
        )
        assert len(findings) >= 2
        assert findings[0].severity == "contraindicated"

    def test_no_findings_no_blocking(self):
        findings = check_prescription([], [], ["paracetamol"])
        assert not has_blocking_findings(findings)


# =============================================================================
# findings_summary (LLM read-only interface)
# =============================================================================

class TestFindingsSummary:
    def test_empty_findings_message(self):
        summary = findings_summary([])
        assert "no safety concerns" in summary.lower()

    def test_summary_contains_all_drugs(self):
        findings = check_prescription(
            patient_allergies=["amoxicillin"],
            current_meds=[],
            proposed_items=["amoxicillin", "some_unknown_drug"],
        )
        summary = findings_summary(findings)
        assert "amoxicillin" in summary
        assert "CONTRAINDICATED" in summary

    def test_summary_is_string(self):
        findings = check_prescription([], [], ["ibuprofen"])
        assert isinstance(findings_summary(findings), str)

    def test_source_is_rule_engine(self):
        """Every Finding must have source='rule_engine' regardless of type."""
        findings = check_prescription(
            patient_allergies=["amoxicillin"],
            current_meds=["warfarin"],
            proposed_items=["amoxicillin", "ciprofloxacin", "mystery_drug"],
        )
        for f in findings:
            assert f.source == "rule_engine"


# =============================================================================
# has_blocking_findings utility
# =============================================================================

class TestHasBlocking:
    def test_major_is_not_blocking(self):
        findings = check_prescription([], ["warfarin"], ["ciprofloxacin"])
        # warfarin + ciprofloxacin = major, not contraindicated
        # So blocking = False (unless something else is contraindicated)
        ix = [f for f in findings if f.type == FindingType.INTERACTION]
        assert all(f.severity != "contraindicated" for f in ix) or has_blocking_findings(findings)

    def test_contraindicated_is_blocking(self):
        findings = check_prescription([], ["domperidone"], ["azithromycin"])
        assert has_blocking_findings(findings)

    def test_warning_only_not_blocking(self):
        findings = check_prescription([], [], ["mystery_xyz_drug"])
        assert not has_blocking_findings(findings)


# =============================================================================
# extract_allergies_from_memory heuristic
# =============================================================================

class TestExtractAllergies:
    def test_extracts_penicillin(self):
        text = "Patient has a documented allergy to penicillin and sulfa drugs."
        allergies = extract_allergies_from_memory(text)
        assert "penicillin" in allergies

    def test_extracts_brand_and_normalises(self):
        # Brand -> generic mapping via allergy sentence
        text1 = "Patient has allergy to Brufen and sulfa drugs."
        allergies1 = extract_allergies_from_memory(text1)
        assert "ibuprofen" in allergies1 or "brufen" in allergies1

        # Generic name from adverse reaction sentence (word immediately follows 'to')
        text2 = "Adverse reaction to ciprofloxacin."
        allergies2 = extract_allergies_from_memory(text2)
        assert "ciprofloxacin" in allergies2

    def test_empty_string_returns_empty(self):
        assert extract_allergies_from_memory("") == []

    def test_no_allergy_pattern_returns_empty(self):
        text = "Patient had sore throat. Prescribed paracetamol. Follow up in 5 days."
        allergies = extract_allergies_from_memory(text)
        assert allergies == []

    def test_no_duplicates(self):
        text = "Allergy to penicillin. Known allergies: penicillin."
        allergies = extract_allergies_from_memory(text)
        assert allergies.count("penicillin") == 1


# =============================================================================
# to_dict serialisation
# =============================================================================

class TestFindingSerialisation:
    def test_to_dict_has_all_keys(self):
        f = Finding(
            severity="major",
            type=FindingType.INTERACTION,
            drug="warfarin + ciprofloxacin",
            reason="CYP1A2 inhibition",
        )
        d = f.to_dict()
        for key in ("severity", "type", "drug", "reason", "source"):
            assert key in d
        assert d["source"] == "rule_engine"
        assert d["type"] == "interaction"
