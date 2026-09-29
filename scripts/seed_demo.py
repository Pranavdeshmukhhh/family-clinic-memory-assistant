#!/usr/bin/env python3
"""
Seed script — populates Hindsight memory banks with realistic multi-visit
histories for 3 demo patients. Run once before the demo.

Usage:
    python scripts/seed_demo.py

Requires HINDSIGHT_API_KEY and HINDSIGHT_BASE_URL in .env (or DEMO_MODE=true
for a dry run).
"""
import asyncio
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.config import settings
from app.db import init_db
from app.services.memory import _seed_one_patient

# ─── Patient 1: Ravi Kumar ──────────────────────────────────────────────────
# 58 M, hypertension + type 2 diabetes, penicillin allergy
RAVI = (
    "patient_001",
    "Patient Ravi Kumar",
    [
        (
            "visit_2026_03_15",
            "Patient Ravi Kumar, male, age 58. Visited 2026-03-15. "
            "Chief complaint: routine check-up, occasional headaches. "
            "BP 154/96, pulse 78. Diagnosed Stage 2 Hypertension. "
            "Prescribed Amlodipine 5mg once daily. "
            "Known PENICILLIN ALLERGY — severe hives after Amoxicillin in 2018. "
            "Fasting glucose 168 mg/dL. HbA1c 7.2%. "
            "Started Metformin 500mg twice daily for new-onset Type 2 Diabetes. "
            "No other medications. Advised low-salt, low-sugar diet. "
            "Follow-up in 6 weeks."
        ),
        (
            "visit_2026_04_28",
            "Follow-up 2026-04-28. BP improved to 138/88 on Amlodipine 5mg. "
            "Fasting glucose 148 mg/dL (improved from 168). HbA1c pending. "
            "Patient reports better energy, no headaches. "
            "Continue Amlodipine 5mg + Metformin 500mg BD. "
            "Reiterated penicillin allergy — documented in chart."
        ),
        (
            "visit_2026_06_10",
            "Visit 2026-06-10. Sore throat, mild fever 99.4°F for 2 days. "
            "BP 134/86 (stable). Throat erythematous, no exudate. "
            "Diagnosed viral pharyngitis. "
            "Prescribed Paracetamol 500mg TDS for symptomatic relief. "
            "AVOIDED AMOXICILLIN due to documented penicillin allergy. "
            "If bacterial, consider Azithromycin instead. "
            "Fasting glucose 142 mg/dL — Metformin working. "
            "Continue current medications."
        ),
        (
            "visit_2026_08_22",
            "Visit 2026-08-22. Routine diabetes review. "
            "HbA1c 6.8% (down from 7.2%). Fasting glucose 136 mg/dL. "
            "BP 132/84. Weight stable at 78 kg. "
            "Excellent glycemic control on Metformin 500mg BD. "
            "Amlodipine 5mg controlling hypertension well. "
            "Lipid panel: Total cholesterol 218, LDL 142, HDL 44, TG 160. "
            "Started Atorvastatin 10mg at bedtime. "
            "Next review in 3 months."
        ),
        (
            "visit_2026_09_28",
            "Visit 2026-09-28. Patient reports fatigue and increased thirst × 5 days. "
            "Fasting glucose 172 mg/dL — glycemic control slipping. "
            "BP 136/88. No signs of infection. "
            "Increased Metformin to 1000mg BD. "
            "Advised to monitor blood sugar at home twice daily. "
            "Continue Amlodipine 5mg and Atorvastatin 10mg. "
            "Penicillin allergy re-confirmed. Follow-up in 2 weeks."
        ),
    ],
)

# ─── Patient 2: Lakshmi Devi ────────────────────────────────────────────────
# 45 F, type 2 diabetes, hypothyroidism
LAKSHMI = (
    "patient_002",
    "Patient Lakshmi Devi",
    [
        (
            "visit_2026_05_10",
            "Patient Lakshmi Devi, female, age 45. Visited 2026-05-10. "
            "Fatigue, weight gain of 4 kg in 3 months, hair thinning. "
            "TSH 12.4 mIU/L (elevated), Free T4 0.6 ng/dL (low). "
            "Fasting glucose 186 mg/dL. HbA1c 7.8%. "
            "Diagnosed Hypothyroidism + Type 2 Diabetes Mellitus. "
            "Started Levothyroxine 50mcg before breakfast. "
            "Started Metformin 500mg BD with meals. "
            "No known drug allergies. Advised 30 min walking daily."
        ),
        (
            "visit_2026_07_05",
            "Follow-up 2026-07-05. Energy improving. Weight stable at 72 kg. "
            "TSH 6.8 (improving from 12.4). Fasting glucose 158 mg/dL. "
            "Increased Levothyroxine to 75mcg. "
            "Continue Metformin 500mg BD. "
            "Renal function: Creatinine 0.9, eGFR > 90 — normal. "
            "Next HbA1c in 6 weeks."
        ),
        (
            "visit_2026_08_18",
            "Visit 2026-08-18. HbA1c 7.1% (improved from 7.8%). "
            "TSH 4.2 — now within normal range on Levothyroxine 75mcg. "
            "Fasting glucose 144 mg/dL. BP 126/82. "
            "Hair regrowth noted. Patient feeling much better. "
            "Continue all current medications unchanged. "
            "Ophthalmology referral for diabetic retinal screening."
        ),
        (
            "visit_2026_09_26",
            "Visit 2026-09-26. Tingling in feet × 2 weeks, worsening at night. "
            "Monofilament test: reduced sensation bilateral feet. "
            "Fasting glucose 152 mg/dL. HbA1c pending. "
            "Diagnosed early diabetic peripheral neuropathy. "
            "Added Pregabalin 75mg at bedtime for neuropathic pain. "
            "Reinforced foot care education. Continue Metformin, Levothyroxine. "
            "Urgent HbA1c ordered."
        ),
    ],
)

# ─── Patient 3: Arjun Reddy ─────────────────────────────────────────────────
# 30 M, recurring migraine, NSAID sensitivity
ARJUN = (
    "patient_003",
    "Patient Arjun Reddy",
    [
        (
            "visit_2026_06_02",
            "Patient Arjun Reddy, male, age 30. Visited 2026-06-02. "
            "Severe unilateral headache with nausea and photophobia × 6 hours. "
            "No aura. BP 118/76. Neuro exam normal. "
            "History of similar episodes 2-3 times/month since 2024. "
            "Diagnosed Migraine without aura. "
            "Prescribed Sumatriptan 50mg PRN at onset. "
            "Known NSAID sensitivity — ibuprofen causes GI bleeding. "
            "Advised migraine diary, trigger avoidance."
        ),
        (
            "visit_2026_07_20",
            "Follow-up 2026-07-20. 4 migraine episodes in 6 weeks despite Sumatriptan. "
            "Duration averaging 8 hours per attack. Missing work 2 days/month. "
            "Meets criteria for prophylaxis. "
            "Started Propranolol 20mg BD for migraine prevention. "
            "Continue Sumatriptan 50mg PRN for acute attacks. "
            "Avoid NSAIDs — use Paracetamol for mild headaches only."
        ),
        (
            "visit_2026_09_10",
            "Visit 2026-09-10. Migraine frequency reduced to 1 per month on Propranolol. "
            "Pulse 64 (expected on beta-blocker). BP 112/72. "
            "Patient tolerating Propranolol well, no fatigue or dizziness. "
            "Continue Propranolol 20mg BD + Sumatriptan PRN. "
            "NSAID sensitivity re-documented. "
            "Review in 3 months — consider tapering if remission continues."
        ),
    ],
)


async def main():
    print("🏥 Initializing database...")
    init_db()

    if not settings.hindsight_configured:
        print("⚠️  Hindsight not configured (DEMO_MODE). Seeding will be a no-op.")
        print("   Set HINDSIGHT_API_KEY in .env to seed real memory banks.\n")

    patients = [RAVI, LAKSHMI, ARJUN]
    for bank_id, name, items in patients:
        print(f"📋 Seeding {name} ({bank_id}) — {len(items)} visits...")
        await _seed_one_patient(bank_id, name, items)
        print(f"   ✅ Done.\n")

    print("🎉 All 3 patients seeded successfully!")
    print("   Run the app:  python -m uvicorn main:app --port 8000 --reload")
    print("   Open:         http://localhost:8000")


if __name__ == "__main__":
    asyncio.run(main())
