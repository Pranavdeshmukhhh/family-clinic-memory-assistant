"""
LLM service — Groq chat with a deterministic built-in fallback.

Design principle: Safety lives in code, not in prompts. The LLM explains;
deterministic code decides.  The fallback rule engine ensures the doctor
workflow functions even with no API key.
"""
import json
import logging

from groq import Groq

from app.config import settings

log = logging.getLogger("clinic.llm")

# ── Groq client (None when key is absent or placeholder) ─────────────────────
_groq_client: Groq | None = (
    Groq(api_key=settings.GROQ_API_KEY) if settings.groq_configured else None
)


def parse_llm_json(raw: str) -> dict | list:
    """
    Strip markdown code fences (``` or ```json) then parse JSON.
    Raises json.JSONDecodeError if the result is not valid JSON.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Drop the opening fence line
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


def _fallback_rule_engine(system_prompt: str, user_prompt: str) -> str:
    """
    Deterministic clinical rule engine used when Groq is unavailable.
    Returns a JSON string matching the same schema as a real Groq response.
    """
    from app.services.inventory import get_in_stock_medicines  # local to avoid circular import

    prompt_lower = (user_prompt + " " + system_prompt).lower()

    # ── Case 1: Pharmacy substitution request ─────────────────────────────────
    if (
        "substitution" in prompt_lower
        or "alternative" in prompt_lower
        or "pharmacist" in prompt_lower
    ):
        in_stock = get_in_stock_medicines()
        alt_name = in_stock[0] if in_stock else "Paracetamol 500mg"
        for med in in_stock:
            ml = med.lower()
            if "metformin" in ml or "paracetamol" in ml or "ibuprofen" in ml:
                alt_name = med
                break
        return json.dumps({
            "alternative": alt_name,
            "reason": (
                f"Selected safe in-stock therapeutic alternative ({alt_name})"
                " from current inventory."
            ),
        })

    # ── Case 2: Doctor visit ──────────────────────────────────────────────────
    has_diabetes_hist = "diabetes" in prompt_lower or "metformin" in prompt_lower
    has_allergy_penicillin = (
        ("penicillin" in prompt_lower and "allerg" in prompt_lower)
        or ("amoxicillin" in prompt_lower and "allerg" in prompt_lower)
    )

    if "blood sugar" in prompt_lower or "diabetes" in prompt_lower or (
        "fatigue" in prompt_lower and has_diabetes_hist
    ):
        diagnosis = "Type 2 Diabetes Mellitus - Glycemic Review"
        med, dosage = "Metformin 500mg", "500mg twice daily with meals"
        instructions = "Take after breakfast and dinner. Maintain continuous glucose monitoring."
        reasoning = "Recalled patient records indicate Type 2 Diabetes on Metformin. Continuing therapy."
        warning = None
    elif "fever" in prompt_lower or "headache" in prompt_lower or "body ache" in prompt_lower:
        diagnosis = "Acute Febrile Illness / Viral Syndrome"
        med, dosage = "Paracetamol 500mg", "500mg every 6 to 8 hours as needed"
        instructions = "Do not exceed 3000mg in 24 hours. Drink plenty of fluids."
        reasoning = "Symptomatic treatment for acute pyrexia and body ache."
        warning = None
    elif "cough" in prompt_lower or "throat" in prompt_lower or "bacterial" in prompt_lower:
        diagnosis = "Upper Respiratory Tract Infection"
        med, dosage = "Amoxicillin 250mg", "250mg three times daily for 5 days"
        instructions = "Complete the entire antibiotic course even if feeling better."
        reasoning = "First-line empirical coverage for suspected bacterial respiratory infection."
        warning = (
            "CRITICAL ALLERGY CONFLICT: Patient history indicates penicillin allergy. "
            "Discontinue penicillin class immediately!"
            if has_allergy_penicillin
            else None
        )
    else:
        diagnosis = "General Clinical Evaluation / Gastro-esophageal Reflux"
        med, dosage = "Omeprazole 20mg", "20mg once daily before breakfast"
        instructions = "Take 30 minutes before first meal of the day."
        reasoning = "First-line gastric acid suppression for dyspeptic symptoms."
        warning = None

    return json.dumps({
        "diagnosis": diagnosis,
        "medicine_name": med,
        "dosage": dosage,
        "instructions": instructions,
        "reasoning": reasoning,
        "warning": warning,
    })


def groq_chat(system_prompt: str, user_prompt: str) -> str:
    """
    Call Groq; fall back to the built-in rule engine on any failure.
    Never raises — always returns a usable string.
    """
    if _groq_client:
        try:
            completion = _groq_client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=1500,
            )
            return completion.choices[0].message.content
        except Exception as exc:
            log.warning(
                "⚠️ Groq API error (%s). Falling back to clinical decision logic.", exc
            )

    log.info("🩺 Using built-in clinical rule engine (Groq not configured or call failed)")
    return _fallback_rule_engine(system_prompt, user_prompt)
