"""The local governments whose council votes we carry.

One entry per Legistar tenant: the API client id, the council body name
exactly as the tenant spells it, the year recorded votes become reliable
(verified in docs/research/local-votes-2026-08.md), and the display
strings the site shows. Adding a government is adding a row here and
re-running the fetch; nothing else is tenant-specific.
"""

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
