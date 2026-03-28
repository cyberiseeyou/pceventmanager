"""
Submission Parser

Parses HTML-formatted responseText from MVRetail's getLocationResponses API
into structured question/answer/photo data.
"""
import re


def parse_submissions(responses):
    """Parse MVRetail responseText HTML into structured Q&A + photos.

    Args:
        responses: list of dicts with 'responseText' HTML strings

    Returns:
        list of dicts with 'question', 'answer', 'photos' keys
    """
    if not responses:
        return []

    results = []
    for resp in responses:
        html = resp.get('responseText', '')
        if not html:
            continue

        question = _extract_question(html)
        answer = _extract_answer(html)
        photos = _extract_photo_urls(html)

        # Skip entries with no question text
        if not question:
            continue

        results.append({
            'question': question.strip(),
            'answer': answer.strip() if answer else None,
            'photos': photos,
        })

    return results


def _extract_question(html):
    """Extract question text from <strong>Question:</strong> pattern."""
    match = re.search(r'<strong>(.*?):</strong>', html, re.DOTALL)
    if match:
        # Strip any inner HTML tags
        text = re.sub(r'<[^>]+>', '', match.group(1))
        return text.strip()
    return None


def _extract_answer(html):
    """Extract answer text from the div after the question."""
    match = re.search(
        r"white-space:\s*normal;'>\s*(.*?)\s*</div>",
        html,
        re.DOTALL
    )
    if match:
        text = re.sub(r'<[^>]+>', '', match.group(1))
        return text.strip()
    return None


def _extract_photo_urls(html):
    """Extract photo URLs from data-url attributes in the HTML."""
    urls = re.findall(r'data-url=["\']([^"\']+)["\']', html)
    return urls


def parse_activity(activity_data):
    """Parse MVRetail activity timeline into structured data.

    Args:
        activity_data: list of dicts or raw response from getMplanActivity

    Returns:
        list of dicts with 'date', 'activity', 'owner' keys
    """
    if not activity_data:
        return []

    # The API returns a list directly or wrapped in a response object
    entries = activity_data if isinstance(activity_data, list) else []

    results = []
    for entry in entries:
        results.append({
            'date': entry.get('date', ''),
            'raw_date': entry.get('rawDate', ''),
            'activity': entry.get('activity', ''),
            'owner': entry.get('owner', ''),
        })

    return results
