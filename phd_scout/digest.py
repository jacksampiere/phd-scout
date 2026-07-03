"""Render scored listings into an email digest and send it via Gmail SMTP.

Stage 3. Input is the list of *surfaced* scored records (``surface`` True) that
``scoring.score_listing`` produces; output is a subject + plaintext + HTML body,
sent to the configured recipient over Gmail SMTP (app password, per CLAUDE.md).

This module is domain-agnostic on purpose — it knows nothing about specific labs
or countries. The §7 (geography) and §8 (already-aware-of) judgments are made in
the reasoning step from ``profile.md`` and arrive on each record as ``known``,
``location``, and ``geo_out_of_scope``; here we only *present* them:

- ``known`` set → surface anyway, tagged ``[KNOWN]`` (§8).
- ``geo_out_of_scope`` true → advisory geography flag, not a filter (§7).

Every digest also carries a manual-check nudge for FindAPhD, which is
Cloudflare-blocked and cannot be crawled from CI (see ``sources.fetch_findaphd``).

Formatting is pure and offline-testable; only ``send_digest`` touches the network.
"""

from __future__ import annotations

import html
import logging
import os
import smtplib
from datetime import date
from email.message import EmailMessage

from phd_scout.sources import FINDAPHD_SEARCH

logger = logging.getLogger(__name__)

# Gmail SMTP over implicit TLS.
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 465


# --- Formatting ------------------------------------------------------------


# Display labels for role types (profile.md §6b). Omitted types never reach the
# digest, so they need no label.
_POSITION_LABELS = {
    "phd": "PhD",
    "postdoc": "Postdoc",
    "research_staff": "Research staff",
    "unknown": "role?",
}


def _position_label(listing: dict) -> str:
    pt = listing.get("position_type", "unknown")
    return _POSITION_LABELS.get(pt, pt)


def _sort_key(listing: dict) -> tuple[int, int, int]:
    """PhD positions first (the direct target), then strongest-first by A, then B."""
    phd_first = 0 if listing.get("position_type") == "phd" else 1
    return (
        phd_first,
        -int(listing.get("domain_fit", 0)),
        -int(listing.get("robustness", 0)),
    )


def _findaphd_reminder_text() -> str:
    return (
        "Reminder: FindAPhD can't be crawled automatically (Cloudflare-blocked), "
        "so check it by hand:\n"
        f"  {FINDAPHD_SEARCH}"
    )


def _findaphd_reminder_html() -> str:
    url = html.escape(FINDAPHD_SEARCH, quote=True)
    return (
        '<p style="color:#555;font-size:13px;border-top:1px solid #ddd;'
        'padding-top:12px;margin-top:24px;">'
        "Reminder: FindAPhD can't be crawled automatically (Cloudflare-blocked), "
        f'so check it by hand: <a href="{url}">{html.escape(FINDAPHD_SEARCH)}</a>.'
        "</p>"
    )


def _listing_text(listing: dict) -> str:
    known = listing.get("known")
    prefix = f"[{_position_label(listing)}] "
    if known:
        prefix += "[KNOWN] "
    lines = [f"{prefix}{listing.get('title', '(untitled)')}"]
    lines.append(
        f"  A(domain)={listing.get('domain_fit')} "
        f"B(robustness)={listing.get('robustness')} "
        f"core={listing.get('in_core_domain')}  [{listing.get('source', '?')}]"
    )
    if known:
        lines.append(f"  known thread: {known}")
    if listing.get("geo_out_of_scope"):
        loc = listing.get("location") or "unknown"
        lines.append(f"  ⚠ geography? {loc} — verify it's in scope (§7)")
    forms = ", ".join(listing.get("robustness_forms") or []) or "—"
    lines.append(f"  robustness forms: {forms}")
    lines.append(f"  why: {listing.get('justification', '')}")
    lines.append(f"  {listing.get('url', '')}")
    if listing.get("date"):
        lines.append(f"  posted: {listing['date']}")
    return "\n".join(lines)


def _listing_html(listing: dict) -> str:
    def esc(value: object) -> str:
        return html.escape(str(value if value is not None else ""))

    known = listing.get("known")
    is_phd = listing.get("position_type") == "phd"
    title = esc(listing.get("title", "(untitled)"))
    url = html.escape(str(listing.get("url", "")), quote=True)
    # PhD (the target) gets a green badge; other kept roles a neutral grey one.
    pos_colors = "#d7f0d0;color:#1c5222" if is_phd else "#e4e6eb;color:#3a3f47"
    badge = (
        f'<span style="background:{pos_colors};font-size:11px;'
        f'padding:1px 6px;border-radius:3px;margin-right:6px;">'
        f"{esc(_position_label(listing))}</span>"
    )
    if known:
        badge += (
            '<span style="background:#ffe08a;color:#5a4500;font-size:11px;'
            'padding:1px 6px;border-radius:3px;margin-right:6px;">KNOWN</span>'
        )
    parts = [
        '<div style="margin:0 0 20px 0;">',
        f'<div style="font-size:15px;font-weight:600;">{badge}'
        f'<a href="{url}" style="color:#1a4fd6;'
        f'text-decoration:none;">{title}</a></div>',
        f'<div style="color:#333;font-size:13px;margin:2px 0;">'
        f"A(domain)={esc(listing.get('domain_fit'))} · "
        f"B(robustness)={esc(listing.get('robustness'))} · "
        f"core={esc(listing.get('in_core_domain'))} · "
        f"{esc(listing.get('source', '?'))}</div>",
    ]
    if known:
        parts.append(
            '<div style="color:#5a4500;font-size:12px;">'
            f"known thread: {esc(known)}</div>"
        )
    if listing.get("geo_out_of_scope"):
        parts.append(
            '<div style="color:#b00;font-size:12px;">⚠ geography? '
            f"{esc(listing.get('location') or 'unknown')} — "
            "verify it's in scope (§7)</div>"
        )
    forms = ", ".join(listing.get("robustness_forms") or []) or "—"
    parts.append(
        f'<div style="color:#333;font-size:12px;">robustness forms: {esc(forms)}</div>'
    )
    parts.append(
        f'<div style="color:#444;font-size:13px;margin-top:2px;">'
        f"{esc(listing.get('justification', ''))}</div>"
    )
    parts.append("</div>")
    return "\n".join(parts)


def format_digest(
    listings: list[dict], today: date | None = None
) -> tuple[str, str, str]:
    """Render surfaced listings into ``(subject, text_body, html_body)``.

    ``listings`` should already be the surfaced, new records — this function does
    not re-apply the surface decision or dedup, it only presents. Listings are
    sorted strongest-first. Always appends the FindAPhD manual-check reminder.
    """
    today = today or date.today()
    n = len(listings)
    plural = "es" if n != 1 else ""
    subject = f"PhD Scout — {n} new match{plural} — {today.isoformat()}"
    ordered = sorted(listings, key=_sort_key)

    text_body = "\n\n".join(
        [f"{n} new match{plural} scored to surface:"]
        + [_listing_text(item) for item in ordered]
        + ["\n" + _findaphd_reminder_text()]
    )

    html_items = "\n".join(_listing_html(item) for item in ordered)
    html_body = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'max-width:680px;">'
        f'<h2 style="font-size:17px;">{n} new match{plural} scored to surface</h2>'
        f"{html_items}"
        f"{_findaphd_reminder_html()}"
        "</div>"
    )
    return subject, text_body, html_body


# --- Sending ---------------------------------------------------------------


def send_digest(
    subject: str,
    text_body: str,
    html_body: str,
    *,
    sender: str | None = None,
    password: str | None = None,
    recipient: str | None = None,
) -> None:
    """Send the digest over Gmail SMTP.

    Credentials come from the environment unless passed explicitly:
    ``GMAIL_ADDRESS``, ``GMAIL_APP_PASSWORD``, and ``DIGEST_RECIPIENT``
    (defaults to the sender). Raises if credentials are missing or the send
    fails — the caller must not mark listings seen unless this returns cleanly.
    """
    sender = sender or os.environ.get("GMAIL_ADDRESS")
    password = password or os.environ.get("GMAIL_APP_PASSWORD")
    recipient = recipient or os.environ.get("DIGEST_RECIPIENT") or sender
    if not sender or not password:
        raise RuntimeError(
            "GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set to send the digest."
        )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP_SSL(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)
    logger.info("digest: sent %r to %s", subject, recipient)
