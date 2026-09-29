"""Local intent-based assistant endpoint."""
from fastapi import APIRouter
from fixmate.schemas import AssistantInput

router = APIRouter()


@router.post("/api/assistant")
def assistant(payload: AssistantInput):
    q = payload.question.lower()
    hi = payload.language == "hi"
    if any(word in q for word in ("book", "booking", "service", "बुक", "सेवा")):
        answer = "सेवा बुक करने के लिए होम स्क्रीन पर सेवा चुनें, अपना पता और समय दें।" if hi else "Choose a service on Home, then enter your address and preferred time. The platform will rank verified, available cooperative workers nearby."
        action = "book"
    elif any(word in q for word in ("worker", "earn", "काम", "कमाई", "verification", "verify")):
        answer = "वर्कर अकाउंट बनाएं, कौशल और प्रमाणपत्र जोड़ें। सहकारी एडमिन सत्यापन के बाद बुकिंग मिल सकती है।" if hi else "Create a worker account, add your skills and certificates, and submit your profile. A cooperative admin must verify it before you can receive bookings."
        action = "worker"
    elif any(word in q for word in ("payment", "pay", "invoice", "भुगतान", "बिल")):
        answer = "भुगतान और बिल बुकिंग पूरी होने के बाद दिखेंगे। डिजिटल भुगतान अभी केवल डेमो रिकॉर्ड है।" if hi else "Payment and invoice details appear after a booking is completed. Digital checkout in this prototype records a demo entry only; it does not transfer money."
        action = "payment"
    elif any(word in q for word in ("emergency", "urgent", "आपात", "तुरंत")):
        answer = "बुकिंग बनाते समय Emergency चुनें। यह अनुरोध को प्राथमिकता देता है; वास्तविक आपातकाल में स्थानीय आपात सेवा से संपर्क करें।" if hi else "Select Emergency while creating a booking to flag it for priority. For immediate danger, contact local emergency services."
        action = "emergency"
    else:
        answer = "मैं सेवा बुकिंग, वर्कर प्रोफाइल, सहकारी सत्यापन और भुगतान में मदद कर सकता हूँ।" if hi else "I can help with service bookings, worker profiles, cooperative verification, demand forecasts, and payment records. Ask about one of those topics."
        action = "help"
    return {"answer": answer, "action": action, "mode": "local_intent_assistant"}
