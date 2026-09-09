"""Reviewed council sources; expansion order and evidence live in docs/research/."""

from __future__ import annotations

TENANTS: list[dict] = [
    {
        "tenant": "milwaukee",
        "slug": "milwaukee",
        "city": "Milwaukee",
        "body_display": "Milwaukee Common Council",
        "body_name": "COMMON COUNCIL",
        # per-member votes verified complete back to at least 2008
        "since": 2008,
        "seats": 15,
        "insite": "https://milwaukee.legistar.com",
    },
    {
        "tenant": "madison",
        "slug": "madison",
        "city": "Madison",
        "body_display": "Madison Common Council",
        "body_name": "COMMON COUNCIL",
        "since": 2025,
        "seats": 20,
        "insite": "https://madison.legistar.com",
        "final_minutes": ("Approved",),
        "max_new_per_run": 5,
        "bootstrap_event_id": 27791,
        "seat_url_pattern": r"https?://www\.cityofmadison\.com/council/district(\d{1,2})/?",
    },
    {
        "tenant": "cityofappleton",
        "slug": "appleton",
        "city": "Appleton",
        "body_display": "Appleton Common Council",
        "body_name": "Common Council",
        "since": 2025,
        "seats": 15,
        "insite": "https://cityofappleton.legistar.com",
        "max_new_per_run": 2,
        "bootstrap_event_id": 6462,
    },
    {
        "tenant": "waukesha",
        "slug": "waukesha",
        "city": "Waukesha",
        "body_display": "Waukesha Common Council",
        "body_name": "City Council",
        "since": 2025,
        "seats": 15,
        "insite": "https://waukesha.legistar.com",
        "max_new_per_run": 2,
        "bootstrap_event_id": 13087,
    },
    {
        "tenant": "westalliswi",
        "slug": "west-allis",
        "city": "West Allis",
        "body_display": "West Allis Common Council",
        "body_name": "Common Council",
        # 2010-14 minutes carry votes on barely half the acted items;
        # from 2015 the record is consistent (see the research note)
        "since": 2015,
        "seats": 5,
        "insite": "https://westalliswi.legistar.com",
    },
]
