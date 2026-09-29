"""Small, privacy-conscious platform context for FixMate Helper."""
import json

import platform_db as store


def get_assistant_context() -> dict:
    """Return aggregate operational facts; never send names or contact details."""
    # Safe for API use and direct invocation in tests or one-off scripts.
    store.init_db()
    with store.connect() as db:
        services = [row["name"] for row in db.execute(
            "SELECT name FROM services ORDER BY name"
        )]
        worker_counts = [dict(row) for row in db.execute(
            """SELECT s.name AS service,
                      SUM(CASE WHEN w.verified=1 AND w.available=1 THEN 1 ELSE 0 END) AS available_workers
               FROM services s
               LEFT JOIN workers w ON EXISTS (
                   SELECT 1 FROM json_each(w.skills) skill
                   WHERE lower(skill.value)=lower(s.name)
               )
               GROUP BY s.name ORDER BY s.name"""
        )]
        booking_counts = [dict(row) for row in db.execute(
            "SELECT status, COUNT(*) AS count FROM bookings GROUP BY status ORDER BY status"
        )]

    return {
        "services": services,
        "available_verified_workers_by_service": worker_counts,
        "bookings_by_status": booking_counts,
        "important_limits": [
            "Digital checkout is a demo record; it does not transfer money.",
            "Worker welfare status is a cooperative record, not proof of insurance coverage.",
            "Assistant context contains aggregate counts only, not personal data.",
        ],
    }
