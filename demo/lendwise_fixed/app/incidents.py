"""FTC Safeguards Rule 314.4(j): breach-notification handling."""
import datetime as dt
import json

from . import config

NOTIFY_THRESHOLD = 500   # consumers
NOTIFY_WITHIN_DAYS = 30  # days after discovery


def handle_notification_event(event: dict) -> dict:
    """Decide whether the FTC must be notified and by when. Stores no consumer data."""
    affected = int(event.get("affected_consumers", 0))
    discovered = dt.date.fromisoformat(event["discovered_on"])
    result = {"required": affected >= NOTIFY_THRESHOLD, "affected_consumers": affected}
    if result["required"]:
        result["notify_by"] = (discovered + dt.timedelta(days=NOTIFY_WITHIN_DAYS)).isoformat()
        with open(config.path("notices.json"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"discovered_on": event["discovered_on"], **result}) + "\n")
    return result
