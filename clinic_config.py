"""
Clinic profile for Reception360.

This is the single source of truth for everything the AI knows about the
clinic itself — hours, location, services, providers, insurance, pricing.

In a multi-tenant version, each clinic would have its own config like this,
looked up by the Twilio phone number the call came in on.
"""

CLINIC = {
    "name": "Reception360 Demo Dental Clinic",
    "vertical": "dental",

    # --- Location & logistics ---
    "address": "123 Main Street, New York, NY 10001",
    "parking": "Street parking is available, and there's a paid garage on 2nd Avenue half a block away.",
    "directions_note": "We're on the ground floor, entrance is next to the coffee shop.",

    # --- Hours ---
    # Keep this human-readable; the AI reads it as text.
    "hours_text": "Monday through Friday, 9 AM to 5 PM. Closed Saturday and Sunday.",
    "closed_days": ["Saturday", "Sunday"],

    # --- New patients ---
    "accepting_new_patients": True,
    "new_patient_note": "New patients should arrive 15 minutes early to fill out intake forms, and bring a photo ID and insurance card.",

    # --- Providers ---
    # Each provider: name, role, and which days they work.
    "providers": [
        {"name": "Dr. Sarah Chen", "role": "General Dentist", "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]},
        {"name": "Dr. Marcus Reed", "role": "Orthodontist", "days": ["Tuesday", "Thursday"]},
        {"name": "Dr. Priya Nair", "role": "Periodontist", "days": ["Monday", "Wednesday"]},
    ],

    # --- Services offered ---
    # Simple list the AI can check against.
    "services": [
        "Routine cleanings and checkups",
        "Fillings",
        "Root canals",
        "Crowns and bridges",
        "Tooth extractions",
        "Teeth whitening",
        "Orthodontics (braces and aligners)",
        "Periodontal (gum) treatment",
        "Dental implants",
        "Pediatric dental care",
    ],

    # Services explicitly NOT offered — helps the AI say a clear "no"
    "services_not_offered": [
        "Oral surgery requiring general anesthesia",
        "Cosmetic facial procedures",
    ],

    # --- Insurance ---
    "insurance_accepted": [
        "Delta Dental",
        "Cigna",
        "MetLife",
        "Aetna",
        "Guardian",
        "United Healthcare",
    ],
    "insurance_note": "We're in-network with the plans listed. We also accept out-of-network patients, but coverage and costs vary — patients should check with their insurance for specifics.",

    # --- Cost estimates ---
    # ALWAYS ranges, never exact. The AI must present these as estimates only.
    "price_ranges": {
        "Routine cleaning and checkup": "$120 to $250",
        "Filling": "$150 to $400 depending on size and material",
        "Root canal": "$700 to $1,500 depending on the tooth",
        "Crown": "$1,000 to $2,000",
        "Tooth extraction": "$150 to $400 for a simple extraction",
        "Teeth whitening": "$300 to $650",
        "New patient exam with X-rays": "$150 to $350",
    },
    "pricing_disclaimer": "These are general estimates only. The actual cost depends on the exam, the specific treatment needed, and your insurance coverage. We provide a detailed estimate after your first visit.",

    # --- Emergency guidance ---
    "emergency_note": "For a medical emergency, hang up and call 911. For urgent dental pain after hours, we'll have a clinician follow up the next business day.",
}