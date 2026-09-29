"""Local, data-aware helper for common FixMate questions."""
import json
import re

import platform_db as store
from fastapi import APIRouter
from fixmate.schemas import AssistantInput

router = APIRouter()

SERVICE_ALIASES = {
    "Electrical": ("electrician", "electricians", "electrical", "electric", "बिजली", "इलेक्ट्रीशियन"),
    "Plumbing": ("plumber", "plumbers", "plumbing", "प्लंबर", "नलसाजी"),
    "Carpentry": ("carpenter", "carpenters", "carpentry", "बढ़ई", "सुतार"),
    "Cleaning": ("cleaner", "cleaners", "cleaning", "सफाई"),
    "Painting": ("painter", "painters", "painting", "पेंटिंग"),
    "Caregiving": ("caregiver", "caregivers", "caregiving", "देखभाल"),
    "Driving": ("driver", "drivers", "driving", "ड्राइवर"),
    "Gardening": ("gardener", "gardeners", "gardening", "बागवानी"),
    "Technician": ("technician", "technicians", "तकनीशियन"),
}


def _requested_service(question: str) -> str | None:
    normalized = re.sub(r"[^\w\s]", " ", question.casefold())
    for service, aliases in SERVICE_ALIASES.items():
        if any(re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized) for alias in aliases):
            return service
    return None


def _available_workers(service: str | None) -> int:
    """Count verified, available workers in the live roster, optionally by skill."""
    with store.connect() as db:
        rows = db.execute(
            "SELECT skills FROM workers WHERE verified = 1 AND available = 1"
        ).fetchall()
    if service is None:
        return len(rows)
    return sum(
        service.casefold() in {str(skill).casefold() for skill in json.loads(row["skills"] or "[]")}
        for row in rows
    )


def _is_worker_count_question(question: str) -> bool:
    q = question.casefold()
    asks_count = any(term in q for term in (
        "how many", "number of", "count of", "कितने", "कितनी", "कितना",
    ))
    mentions_workers = any(term in q for term in (
        "worker", "workers", "कामगार", "कर्मचारी",
    ))
    return asks_count and (mentions_workers or _requested_service(question) is not None)


@router.post("/api/assistant")
def assistant(payload: AssistantInput):
    question = payload.question.strip()
    q = question.casefold()
    language = payload.language

    if _is_worker_count_question(question):
        service = _requested_service(question)
        count = _available_workers(service)
        if language == "hi":
            if service:
                answer = (
                    f"सहकारी सूची में अभी {service} कौशल वाले {count} सत्यापित और उपलब्ध कामगार हैं। "
                    "यह पूरे सहकारी क्षेत्र की संख्या है; किसी बुकिंग में दूरी, समय-सारणी और मौजूदा काम के आधार पर पात्रता अलग हो सकती है।"
                )
            else:
                answer = f"सहकारी सूची में अभी {count} सत्यापित और उपलब्ध कामगार हैं। किसी खास सेवा का नाम बताएँ तो मैं उसका अलग आँकड़ा दे सकता हूँ।"
        elif service:
            answer = (
                f"There are {count} verified, currently available workers with {service} listed as a skill "
                "in the cooperative roster. This is a roster-wide count; a booking may find fewer after "
                "checking distance, schedule, and current workload."
            )
        else:
            answer = (
                f"There are {count} verified, currently available workers in the cooperative roster. "
                "Name a service if you want its separate count. A booking may find fewer after checking distance, schedule, and workload."
            )
        return {"answer": answer, "action": "worker_count", "mode": "live_roster"}

    if any(word in q for word in ("book", "booking", "service", "बुक", "सेवा")):
        answer = "सेवा बुक करने के लिए होम स्क्रीन पर सेवा चुनें, अपना पता और समय दें।" if language == "hi" else "Choose a service on Home, then enter your address and preferred time. FixMate ranks verified, available cooperative workers for the booking."
        action = "book"
    elif any(word in q for word in ("payment", "pay", "invoice", "भुगतान", "बिल")):
        answer = "भुगतान और बिल बुकिंग पूरी होने के बाद दिखेंगे। डिजिटल भुगतान अभी केवल डेमो रिकॉर्ड है।" if language == "hi" else "Payment and invoice details appear after a booking is completed. Digital checkout records a demo entry only; it does not transfer money."
        action = "payment"
    elif any(word in q for word in ("emergency", "urgent", "आपात", "तुरंत")):
        answer = "बुकिंग बनाते समय Emergency चुनें। यह अनुरोध को प्राथमिकता देता है; वास्तविक आपातकाल में स्थानीय आपात सेवा से संपर्क करें।" if language == "hi" else "Select Emergency while creating a booking to flag it for priority. For immediate danger, contact local emergency services."
        action = "emergency"
    elif any(word in q for word in ("worker", "earn", "काम", "कमाई", "verification", "verify", "certificate")):
        answer = "वर्कर अकाउंट बनाएं, कौशल और प्रमाणपत्र जोड़ें। सहकारी एडमिन सत्यापन के बाद बुकिंग मिल सकती है।" if language == "hi" else "Create a worker account, add your skills and certificates, and submit your profile. A cooperative admin must verify it before you can receive bookings."
        action = "worker"
    elif any(word in q for word in ("forecast", "future", "demand", "पूर्वानुमान", "मांग")):
        answer = "मांग पूर्वानुमान सहकारी डैशबोर्ड के Demand insights पेज पर सेवा और क्षेत्र चुनकर देखें।" if language == "hi" else "Open Demand insights in the cooperative dashboard, then choose a service and locality to view the demand forecast and staffing gap."
        action = "forecast"
    else:
        answer = "मैं बुकिंग, उपलब्ध कामगारों की संख्या, कामगार प्रोफ़ाइल, मांग पूर्वानुमान और भुगतान में मदद कर सकता हूँ। अपनी सेवा या सवाल थोड़ा स्पष्ट बताएँ।" if language == "hi" else "I can help with bookings, live worker counts, worker profiles, demand forecasts, and payment records. Tell me the service or question you have in mind."
        action = "help"

    return {"answer": answer, "action": action, "mode": "local_intent_assistant"}
