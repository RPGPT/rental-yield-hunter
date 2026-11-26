"""Pipeline step for evaluating ``saved_searches`` and dispatching deal alerts.

Supported delivery channels (all optional, configured via environment variables or per-search JSONB):
- Telegram Bot API: ``TELEGRAM_BOT_TOKEN`` + (``TELEGRAM_CHAT_ID`` or ``filters.telegram_chat_id``)
- Resend Email API: ``RESEND_API_KEY`` + ``ALERT_FROM_EMAIL`` + user email (``neon_auth.user`` or ``ALERT_TO_EMAIL``)
- Webhook JSON POST: ``ALERT_WEBHOOK_URL`` or ``filters.webhook_url``
"""

from __future__ import annotations

import html
import json
import logging
import os
import urllib.request

from yieldhunter.analysis.alerts import format_alert_digest_markdown
from yieldhunter.db.repository.alerts import find_pending_saved_search_alerts, record_sent_alerts
from yieldhunter.db.session import session_scope
from yieldhunter.pipeline.stats import write_stats_file

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict, headers: dict[str, str] | None = None) -> bool:
    req_headers = {"Content-Type": "application/json", "User-Agent": "rental-yield-hunter/1.0"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception:
        logger.exception("Alert HTTP delivery failed for %s", url)
        return False


def _deliver_alert_bundle(bundle: dict) -> bool:
    search = bundle["saved_search"]
    filters = search["filters"]
    matches = bundle["matches"]
    digest_md = format_alert_digest_markdown(search["name"], matches)

    delivered = False

    # 1. Telegram
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = filters.get("telegram_chat_id") or os.environ.get("TELEGRAM_CHAT_ID")
    if tg_token and tg_chat:
        ok = _post_json(
            f"https://api.telegram.org/bot{tg_token}/sendMessage",
            {"chat_id": tg_chat, "text": digest_md, "disable_web_page_preview": True},
        )
        delivered = delivered or ok

    # 2. Resend Email
    resend_key = os.environ.get("RESEND_API_KEY")
    to_email = search.get("user_email") or os.environ.get("ALERT_TO_EMAIL")
    from_email = os.environ.get("ALERT_FROM_EMAIL", "alerts@yieldhunter.pt")
    if resend_key and to_email:
        html_body = "<pre style='font-family:sans-serif;white-space:pre-wrap'>" + html.escape(digest_md) + "</pre>"
        ok = _post_json(
            "https://api.resend.com/emails",
            {
                "from": from_email,
                "to": [to_email],
                "subject": f"[Yield Hunter] {len(matches)} new deal(s) for '{search['name']}'",
                "html": html_body,
            },
            headers={"Authorization": f"Bearer {resend_key}"},
        )
        delivered = delivered or ok

    # 3. Webhook
    webhook_url = filters.get("webhook_url") or os.environ.get("ALERT_WEBHOOK_URL")
    if webhook_url:
        ok = _post_json(
            webhook_url,
            {
                "saved_search_id": search["id"],
                "saved_search_name": search["name"],
                "count": len(matches),
                "text": digest_md,
                "listings": [
                    {
                        "id": m["id"],
                        "url": m["url"],
                        "city": m["city"],
                        "neighborhood": m["neighborhood"],
                        "typology": m["typology"],
                        "area": m["area"],
                        "price": m["price"],
                        "previous_price": m.get("previous_price"),
                        "trigger_type": m["trigger_type"],
                        "estimated_rent": m.get("estimated_rent"),
                        "rental_yield": float(m["rental_yield"]) if m.get("rental_yield") is not None else None,
                    }
                    for m in matches
                ],
            },
        )
        delivered = delivered or ok

    return delivered


def run_send_alerts() -> dict:
    """Evaluate all saved searches and send alerts for new matching deals and price drops."""
    logger.info("Evaluating saved-search deal alerts…")
    with session_scope() as db:
        bundles = find_pending_saved_search_alerts(db)

    matched_listings = sum(len(b["matches"]) for b in bundles)
    notified_searches = 0
    sent_notifications = 0

    for bundle in bundles:
        if _deliver_alert_bundle(bundle):
            with session_scope() as db:
                sent_notifications += record_sent_alerts(db, bundle["saved_search"]["id"], bundle["matches"])
            notified_searches += 1
        else:
            logger.info(
                "Saved search %r matched %d listing(s), but no delivery channel is configured/succeeded",
                bundle["saved_search"]["name"],
                len(bundle["matches"]),
            )

    stats = {
        "type": "alerts",
        "searches_matched": len(bundles),
        "searches_notified": notified_searches,
        "listings_matched": matched_listings,
        "notifications_sent": sent_notifications,
    }
    write_stats_file("stats-alerts.json", stats)
    logger.info(
        "Alerts done — %d searches matched (%d notified), %d listing matches (%d notifications recorded)",
        len(bundles),
        notified_searches,
        matched_listings,
        sent_notifications,
    )
    return stats
