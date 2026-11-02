"""Turn approved obligations into concrete checks, using the code graph of the target (Step 5)."""
from __future__ import annotations

from ..graph import Graph
from ..util import slug
from .model import Obligation

STORE_TEST = {
    "logs": "logs_exclude_customer_data",
    "exports": "exports_exclude_customer_data",
    "db": "database_protects_customer_data_at_rest",
}


def plan_checks(ob: Obligation, graph: Graph, cfg: dict) -> list[dict]:
    n = ob.id.lower().replace("-", "")
    checks: list[dict] = []
    if ob.kind == "mfa_required":
        public = set(cfg.get("public_routes", []))
        for r in graph.routes:
            if r.path in public:
                continue
            checks.append({"name": f"test_{n}_{r.method.lower()}_{slug(r.path)}_requires_second_factor",
                           "type": "route_requires_mfa", "method": r.method, "path": r.path})
    elif ob.kind == "no_plaintext_customer_data":
        for store in cfg.get("canary", {}).get("stores", {}):
            checks.append({"name": f"test_{n}_{STORE_TEST.get(store, store + '_exclude_customer_data')}",
                           "type": "canary_clean", "store": store})
    elif ob.kind == "breach_notice":
        checks.append({"name": f"test_{n}_ftc_notice_for_notification_events", "type": "ftc_notice",
                       "days": ob.params.get("days", 30), "min_consumers": ob.params.get("min_consumers", 500)})
    return checks  # manual_review obligations get no automated checks
