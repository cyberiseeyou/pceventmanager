"""Query classification for determining what context to retrieve"""

from enum import Enum
from dataclasses import dataclass
from typing import List
import re
from datetime import datetime, timedelta


class QueryType(Enum):
    """Types of scheduling queries"""
    AVAILABILITY = "availability"          # Who's available?
    SCHEDULE_VIEW = "schedule_view"        # What's the schedule?
    CONFLICT_CHECK = "conflict_check"      # Any conflicts?
    EMPLOYEE_SUGGEST = "employee_suggest"  # Who should I assign?
    WORKLOAD_ANALYSIS = "workload"         # Who's overworked?
    TIME_OFF_IMPACT = "time_off_impact"    # What if X takes off?
    EVENT_INFO = "event_info"              # Tell me about event X
    EMPLOYEE_INFO = "employee_info"        # Tell me about employee X
    GENERAL = "general"                    # General question


@dataclass
class QueryAnalysis:
    """Result of query analysis"""
    query_type: QueryType
    date_range: tuple  # (start_date, end_date)
    mentioned_employees: List[str]
    mentioned_events: List[str]
    keywords: List[str]
    confidence: float


class QueryClassifier:
    """Classify user queries to determine context needs"""

    # Pattern matching for query types
    PATTERNS = {
        QueryType.AVAILABILITY: [
            r'\bavailable?\b', r'\bfree\b', r'\bopen\b',
            r'\bwho can\b', r'\bwho.{0,10}work\b'
        ],
        QueryType.CONFLICT_CHECK: [
            r'\bconflict', r'\boverlap', r'\bdouble.?book',
            r'\bclash', r'\bissue', r'\bproblem'
        ],
        QueryType.EMPLOYEE_SUGGEST: [
            r'\bsuggest\b', r'\brecommend\b', r'\bwho should\b',
            r'\bbest (person|employee|candidate)\b', r'\bassign\b'
        ],
        QueryType.WORKLOAD_ANALYSIS: [
            r'\bworkload\b', r'\boverwork', r'\bhours\b',
            r'\bbusy\b', r'\bovertime\b', r'\bbalance\b'
        ],
        QueryType.TIME_OFF_IMPACT: [
            r'\bif.{0,20}(off|leave|vacation|sick)\b',
            r'\bwhat happens\b', r'\bimpact\b'
        ],
        QueryType.SCHEDULE_VIEW: [
            r'\bschedule\b', r'\bwhat.{0,10}(today|tomorrow|this week)\b',
            r'\bshow\b', r'\blist\b'
        ],
    }

    # Date extraction patterns
    DATE_PATTERNS = {
        'today': lambda: (datetime.now().date(), datetime.now().date()),
        'tomorrow': lambda: (
            (datetime.now() + timedelta(days=1)).date(),
            (datetime.now() + timedelta(days=1)).date()
        ),
        'this week': lambda: (
            datetime.now().date(),
            (datetime.now() + timedelta(days=7)).date()
        ),
        'next week': lambda: (
            (datetime.now() + timedelta(days=7)).date(),
            (datetime.now() + timedelta(days=14)).date()
        ),
        'this month': lambda: (
            datetime.now().date(),
            (datetime.now() + timedelta(days=30)).date()
        ),
    }

    def __init__(self, employees: List[str] = None, events: List[str] = None):
        """Initialize with known employee and event names for extraction"""
        self.known_employees = employees or []
        self.known_events = events or []

    def analyze(self, query: str) -> QueryAnalysis:
        """Analyze a query and return structured analysis"""
        query_lower = query.lower()

        # Determine query type
        query_type = self._classify_type(query_lower)

        # Extract date range
        date_range = self._extract_date_range(query_lower)

        # Extract mentioned entities
        employees = self._extract_employees(query)
        events = self._extract_events(query)

        # Extract keywords
        keywords = self._extract_keywords(query_lower)

        # Calculate confidence
        confidence = self._calculate_confidence(query_type, query_lower)

        return QueryAnalysis(
            query_type=query_type,
            date_range=date_range,
            mentioned_employees=employees,
            mentioned_events=events,
            keywords=keywords,
            confidence=confidence,
        )

    def _classify_type(self, query: str) -> QueryType:
        """Classify the query type based on patterns"""
        scores = {}

        for query_type, patterns in self.PATTERNS.items():
            score = sum(
                1 for pattern in patterns
                if re.search(pattern, query, re.IGNORECASE)
            )
            scores[query_type] = score

        if max(scores.values()) > 0:
            return max(scores, key=scores.get)

        return QueryType.GENERAL

    def _extract_date_range(self, query: str) -> tuple:
        """Extract date range from query"""
        for pattern, date_func in self.DATE_PATTERNS.items():
            if pattern in query:
                return date_func()

        # Default to next 7 days
        return (
            datetime.now().date(),
            (datetime.now() + timedelta(days=7)).date()
        )

    def _extract_employees(self, query: str) -> List[str]:
        """Extract mentioned employee names"""
        mentioned = []
        for name in self.known_employees:
            if name.lower() in query.lower():
                mentioned.append(name)
        return mentioned

    def _extract_events(self, query: str) -> List[str]:
        """Extract mentioned event names"""
        mentioned = []
        for event in self.known_events:
            if event.lower() in query.lower():
                mentioned.append(event)
        return mentioned

    def _extract_keywords(self, query: str) -> List[str]:
        """Extract relevant keywords"""
        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
            'can', 'could', 'would', 'should', 'will', 'do', 'does', 'did',
            'who', 'what', 'when', 'where', 'why', 'how', 'i', 'me', 'my',
            'for', 'to', 'of', 'in', 'on', 'at', 'by', 'with', 'from'
        }

        words = re.findall(r'\b[a-z]+\b', query)
        return [w for w in words if w not in stop_words and len(w) > 2]

    def _calculate_confidence(self, query_type: QueryType, query: str) -> float:
        """Calculate confidence in classification"""
        if query_type == QueryType.GENERAL:
            return 0.5

        # Count matching patterns
        patterns = self.PATTERNS.get(query_type, [])
        matches = sum(
            1 for p in patterns
            if re.search(p, query, re.IGNORECASE)
        )

        # Higher matches = higher confidence
        return min(0.9, 0.6 + (matches * 0.1))
