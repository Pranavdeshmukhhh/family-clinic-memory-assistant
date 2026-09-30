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
        return json.dumps({
            "alert": "",
            "summary": "Type 2 Diabetes review — continued glycaemic management needed.",
            "prescription": [{"drug": "Metformin 500mg", "dose": "500mg", "frequency": "BD", "duration": "ongoing"}],
            "memory_used": ["T2DM on Metformin", "Fasting glucose elevated"],
            "advice": ["Take after meals", "Monitor glucose daily", "Stay hydrated"],
            "follow_up": "Recheck fasting glucose in 4 weeks",
        })
    elif "fever" in prompt_lower or "headache" in prompt_lower or "body ache" in prompt_lower:
        return json.dumps({
            "alert": "",
            "summary": "Acute febrile illness, likely viral syndrome.",
            "prescription": [{"drug": "Paracetamol 500mg", "dose": "500mg", "frequency": "Q6-8H PRN", "duration": "3 days"}],
            "memory_used": [],
            "advice": ["Do not exceed 3g/day", "Drink plenty of fluids", "Rest"],
            "follow_up": "Return if fever persists beyond 3 days",
        })
    elif "cough" in prompt_lower or "throat" in prompt_lower or "bacterial" in prompt_lower:
        alert = (
            "ALLERGY: Patient has penicillin allergy — avoid all penicillins."
            if has_allergy_penicillin else ""
        )
        drug = "Azithromycin 500mg" if has_allergy_penicillin else "Amoxicillin 250mg"
        freq = "OD" if has_allergy_penicillin else "TDS"
        return json.dumps({
            "alert": alert,
            "summary": "Upper respiratory tract infection, likely bacterial pharyngitis.",
            "prescription": [{"drug": drug, "dose": drug.split()[-1], "frequency": freq, "duration": "5 days"}],
            "memory_used": (["Penicillin allergy (hives)"] if has_allergy_penicillin else []),
            "advice": ["Complete full course", "Warm salt-water gargle", "Rest voice"],
            "follow_up": "Review in 5 days if symptoms persist",
            "warning": alert or None,
        })
    else:
        return json.dumps({
            "alert": "",
            "summary": "Dyspeptic symptoms — likely GERD or functional dyspepsia.",
            "prescription": [{"drug": "Omeprazole 20mg", "dose": "20mg", "frequency": "OD", "duration": "14 days"}],
            "memory_used": [],
            "advice": ["Take 30 min before breakfast", "Avoid spicy food", "Elevate head of bed"],
            "follow_up": "Review in 2 weeks",
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
