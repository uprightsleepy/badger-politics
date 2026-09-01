# Courtesy notes to the city clerks (owner action)

The local-votes module reads each council's records through the public
Legistar Web API, throttled and cached, exactly as its own documentation
suggests. Nothing requires permission, but a short note to each clerk is
good practice before the one-time backfill traffic and gives them a
contact if anything ever looks off. Send from your own address; adjust
freely.

## City of Milwaukee: City Clerk's office (Legislative Reference Bureau)

Subject: Heads-up: badgerpolitics.org now mirrors Common Council votes

Hello,

I run badgerpolitics.org, a free, independent site that tracks the
Wisconsin Legislature from official records. I'm adding a section that
shows how Common Council members vote, item by item, using the public
Legistar Web API (webapi.legistar.com/v1/milwaukee). Every item links
back to its page on milwaukee.legistar.com, and district boundaries come
from the city's open data portal under its Creative Commons license.

The initial history fetch is a few thousand cached requests spread over
several hours at a slow, throttled pace, identified with the User-Agent
"badgerpolitics.org data pipeline"; after that it's a small nightly
refresh. If you'd ever like anything adjusted, or spot an error in how a
vote is presented, please email me and I'll fix it promptly.

Thank you for keeping these records public and machine-readable.

## City of West Allis: City Clerk

Subject: Heads-up: badgerpolitics.org now mirrors Common Council votes

Hello,

I run badgerpolitics.org, a free, independent site that tracks the
Wisconsin Legislature from official records. I'm adding a section that
shows how West Allis Common Council members vote, item by item, using
the public Legistar Web API (webapi.legistar.com/v1/westalliswi). Every
item links back to its page on westalliswi.legistar.com; the district
map comes from the city's own GIS server, and the alderperson-to-district
roster from the district pages on westalliswi.gov.

The initial history fetch is a few thousand cached requests spread over
an hour or two at a slow, throttled pace, identified with the User-Agent
"badgerpolitics.org data pipeline"; after that it's a small nightly
refresh. If you'd ever like anything adjusted, or spot an error in how a
vote is presented, please email me and I'll fix it promptly.

Thank you for keeping these records public and machine-readable.
