"""
Bakery Prep Service
Fetches bakery prep items from Walmart Event Management API and
builds an HTML email for the bakery department.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Walmart Event Management browse-data endpoint
BROWSE_DATA_URL = (
    "https://retaillink2.wal-mart.com/EventManagement/api/browse-event/browse-data"
)

# Bakery department numbers
BAKERY_DEPARTMENTS = [77, 37, '77', '37']

# Standard browser-like headers for Walmart API
_API_HEADERS = {
    'accept': '*/*',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://retaillink2.wal-mart.com',
    'referer': 'https://retaillink2.wal-mart.com/EventManagement/browse-event',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    ),
}


def fetch_bakery_prep_items(session, store_number):
    """Fetch bakery prep items from Walmart API.

    Args:
        session: An authenticated ``requests.Session`` (from edr_authenticator).
        store_number: Store number string (e.g. ``"8135"``).

    Returns:
        dict with keys ``items`` (list), ``date_range`` (dict), ``store`` (str).

    Raises:
        RuntimeError: On API or parsing errors.
    """
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    two_weeks_out = (datetime.now() + timedelta(days=14)).date()

    payload = {
        "itemNbr": None,
        "vendorNbr": None,
        "startDate": tomorrow.strftime('%Y-%m-%d'),
        "endDate": two_weeks_out.strftime('%Y-%m-%d'),
        "billType": None,
        "eventType": list(range(1, 58)),
        "userId": None,
        "primItem": None,
        "storeNbr": store_number,
        "deptNbr": None,
    }

    logger.info(
        f"Fetching bakery prep events {tomorrow} to {two_weeks_out} for store {store_number}"
    )

    response = session.post(
        BROWSE_DATA_URL, headers=_API_HEADERS, json=payload, timeout=30
    )

    if response.status_code == 404:
        raise RuntimeError(
            'Walmart API endpoint not found. The session may have expired - please re-authenticate.'
        )

    if response.status_code != 200:
        raise RuntimeError(
            f'Walmart API returned status {response.status_code}. Try re-authenticating.'
        )

    try:
        data = response.json()
    except Exception:
        raise RuntimeError(
            'Invalid response from Walmart API. Session may have expired - please re-authenticate.'
        )

    # Handle both list and dict response formats
    if isinstance(data, list):
        events = data
    elif isinstance(data, dict):
        events = data.get('data', [])
    else:
        events = []

    logger.info(f"Retrieved {len(events)} events from API")

    # Filter to bakery departments only
    filtered = [e for e in events if e.get('deptNbr') in BAKERY_DEPARTMENTS]
    logger.info(f"After bakery filter (dept 77/37): {len(filtered)} events")

    # Extract and normalize fields
    items = []
    for event in filtered:
        items.append({
            'eventId': event.get('eventId') or event.get('EventId') or 'N/A',
            'eventDate': event.get('eventDate') or event.get('EventDate') or 'N/A',
            'itemDesc': event.get('itemDesc') or event.get('ItemDesc') or 'N/A',
            'itemNbr': event.get('itemNbr') or event.get('ItemNbr') or 'N/A',
        })

    items.sort(key=lambda x: x['eventDate'] if x['eventDate'] != 'N/A' else '9999-99-99')

    date_range = {
        'start': tomorrow.strftime('%Y-%m-%d'),
        'end': two_weeks_out.strftime('%Y-%m-%d'),
        'formatted': f"{tomorrow.strftime('%B %d')} - {two_weeks_out.strftime('%B %d, %Y')}",
    }

    return {'items': items, 'date_range': date_range, 'store': store_number}


def build_bakery_prep_html_email(items, date_range, store_number):
    """Build a clean HTML table email for bakery prep.

    Args:
        items: List of item dicts from ``fetch_bakery_prep_items``.
        date_range: Dict with ``formatted`` key.
        store_number: Store number string.

    Returns:
        HTML string ready for email body.
    """
    now = datetime.now().strftime('%B %d, %Y %I:%M %p')

    rows = ''
    for item in items:
        rows += (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #ddd;">{item["eventDate"]}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #ddd;">{item["itemDesc"]}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #ddd;">{item["itemNbr"]}</td>'
            f'</tr>'
        )

    if not items:
        rows = (
            '<tr><td colspan="3" style="padding:20px;text-align:center;color:#666;">'
            'No bakery prep items found for this period.</td></tr>'
        )

    return f"""\
<html>
<body style="font-family:Arial,sans-serif;color:#333;max-width:700px;margin:0 auto;">
  <h2 style="color:#2E4C73;border-bottom:2px solid #2E4C73;padding-bottom:8px;">
    Bakery Prep List &mdash; Store {store_number}
  </h2>
  <p style="color:#555;">
    <strong>Date Range:</strong> {date_range.get('formatted', '')}
  </p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0;">
    <thead>
      <tr style="background:#2E4C73;color:#fff;">
        <th style="padding:10px 12px;text-align:left;">Event Date</th>
        <th style="padding:10px 12px;text-align:left;">Item Description</th>
        <th style="padding:10px 12px;text-align:left;">Item Number</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  <p style="color:#888;font-size:0.9em;">
    Total items: {len(items)} &bull; Generated {now}
  </p>
</body>
</html>"""
