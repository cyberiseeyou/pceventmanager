"""
Constraint Modifier Service
Maps natural language scheduling preferences to CP-SAT weight multipliers
stored in SystemSetting for persistence across scheduler runs.
"""
import json
import logging
from app.models import get_models, get_db

logger = logging.getLogger(__name__)

# Key prefix for all scheduling preference overrides
PREF_KEY_PREFIX = 'scheduling_pref_'


class ConstraintModifier:
    """Maps NL preferences to CP-SAT weight adjustments stored in SystemSetting."""

    # Maps NL keywords to CP-SAT weight constant names
    PREFERENCE_MAP = {
        'fairness': 'WEIGHT_FAIRNESS',
        'balance': 'WEIGHT_SHIFT_BALANCE',
        'workload balance': 'WEIGHT_SHIFT_BALANCE',
        'rotation': 'WEIGHT_ROTATION',
        'experience': 'WEIGHT_ML_AFFINITY',
        'ml': 'WEIGHT_ML_AFFINITY',
        'affinity': 'WEIGHT_ML_AFFINITY',
        'supervisor': 'WEIGHT_SUPERVISOR_MISUSE',
        'core limit': 'WEIGHT_JUICER_WEEKLY',
        'juicer limit': 'WEIGHT_JUICER_WEEKLY',
        'urgency': 'WEIGHT_URGENCY',
        'priority': 'WEIGHT_TYPE_PRIORITY',
        'event priority': 'WEIGHT_TYPE_PRIORITY',
        'proximity': 'WEIGHT_PROXIMITY',
        'time proximity': 'WEIGHT_PROXIMITY',
        'duplicate product': 'WEIGHT_DUPLICATE_PRODUCT',
        'lead block': 'WEIGHT_LEAD_BLOCK1',
        'lead daily': 'WEIGHT_LEAD_DAILY',
        'bump': 'WEIGHT_BUMP',
        'bumping': 'WEIGHT_BUMP',
        'scheduling': 'WEIGHT_UNSCHEDULED',
        'coverage': 'WEIGHT_UNSCHEDULED',
    }

    # Direction keywords to multiplier
    DIRECTION_MAP = {
        'increase': 1.5,
        'more': 1.5,
        'higher': 1.5,
        'boost': 2.0,
        'maximize': 2.5,
        'decrease': 0.5,
        'less': 0.5,
        'lower': 0.5,
        'reduce': 0.5,
        'minimize': 0.25,
        'reset': 1.0,
        'default': 1.0,
        'normal': 1.0,
    }

    # Human-readable descriptions for each weight
    WEIGHT_DESCRIPTIONS = {
        'WEIGHT_FAIRNESS': 'workload fairness between employees',
        'WEIGHT_SHIFT_BALANCE': 'daily shift balance',
        'WEIGHT_ROTATION': 'rotation assignment matching',
        'WEIGHT_ML_AFFINITY': 'ML-predicted employee-event affinity',
        'WEIGHT_SUPERVISOR_MISUSE': 'supervisor role enforcement',
        'WEIGHT_JUICER_WEEKLY': 'weekly Juicer event limits',
        'WEIGHT_URGENCY': 'event urgency priority',
        'WEIGHT_TYPE_PRIORITY': 'event type priority ordering',
        'WEIGHT_PROXIMITY': 'time proximity between events',
        'WEIGHT_DUPLICATE_PRODUCT': 'duplicate product avoidance',
        'WEIGHT_LEAD_BLOCK1': 'Primary Lead on Block 1 preference',
        'WEIGHT_LEAD_DAILY': 'Primary Lead on daily events preference',
        'WEIGHT_BUMP': 'existing schedule protection',
        'WEIGHT_UNSCHEDULED': 'event coverage maximization',
        'WEIGHT_SUP_ASSIGNMENT': 'correct Supervisor assignment',
    }

    def __init__(self):
        self.models = get_models()
        self.db = get_db()
        self.SystemSetting = self.models['SystemSetting']

    def apply_preference(self, preference_text, direction='increase'):
        """
        Parse a natural language preference and store the corresponding
        weight multiplier in SystemSetting.

        Args:
            preference_text: NL description of the preference (e.g., 'fairness', 'rotation matching')
            direction: 'increase', 'decrease', 'reset', etc.

        Returns:
            dict with success status and human-readable summary
        """
        # Find matching weight
        weight_name = self._match_preference(preference_text)
        if not weight_name:
            available = sorted(set(self.PREFERENCE_MAP.values()))
            return {
                'success': False,
                'message': f"Could not match '{preference_text}' to a scheduling weight. "
                           f"Available preferences: {', '.join(self.WEIGHT_DESCRIPTIONS.get(w, w) for w in available)}"
            }

        # Determine multiplier from direction
        multiplier = self._parse_direction(direction)

        # Store in SystemSetting
        key = f"{PREF_KEY_PREFIX}{weight_name}"
        value = json.dumps({
            'multiplier': multiplier,
            'set_by': 'ai',
            'preference_text': preference_text,
            'direction': direction,
        })

        description = self.WEIGHT_DESCRIPTIONS.get(weight_name, weight_name)

        self.SystemSetting.set_setting(
            key=key,
            value=value,
            setting_type='string',
            user='ai_assistant',
            description=f"AI-set preference for {description}"
        )

        if multiplier == 1.0:
            action = 'Reset to default'
        elif multiplier > 1.0:
            action = f'Increased by {multiplier:.0%}'
        else:
            action = f'Decreased to {multiplier:.0%}'

        return {
            'success': True,
            'message': f"{action}: {description}",
            'weight_name': weight_name,
            'multiplier': multiplier,
        }

    def get_active_preferences(self):
        """
        Query all SystemSetting entries for scheduling preferences.

        Returns:
            list of dicts with weight_name, multiplier, description, preference_text
        """
        prefs = []
        # Query all settings with the scheduling_pref_ prefix
        settings = self.SystemSetting.query.filter(
            self.SystemSetting.setting_key.like(f'{PREF_KEY_PREFIX}%')
        ).all()

        for setting in settings:
            weight_name = setting.setting_key[len(PREF_KEY_PREFIX):]
            try:
                data = json.loads(setting.setting_value)
            except (json.JSONDecodeError, TypeError):
                continue

            multiplier = data.get('multiplier', 1.0)
            if multiplier == 1.0:
                continue  # Skip defaults

            prefs.append({
                'weight_name': weight_name,
                'multiplier': multiplier,
                'description': self.WEIGHT_DESCRIPTIONS.get(weight_name, weight_name),
                'preference_text': data.get('preference_text', ''),
                'direction': data.get('direction', ''),
                'updated_at': setting.updated_at.isoformat() if setting.updated_at else None,
            })

        return prefs

    def clear_preference(self, weight_name):
        """
        Remove a specific preference override by setting multiplier to 1.0.

        Args:
            weight_name: CP-SAT weight constant name (e.g., 'WEIGHT_FAIRNESS')

        Returns:
            dict with success status
        """
        key = f"{PREF_KEY_PREFIX}{weight_name}"
        description = self.WEIGHT_DESCRIPTIONS.get(weight_name, weight_name)

        self.SystemSetting.set_setting(
            key=key,
            value=json.dumps({'multiplier': 1.0, 'set_by': 'ai', 'direction': 'reset'}),
            setting_type='string',
            user='ai_assistant',
            description=f"Reset preference for {description}"
        )

        return {
            'success': True,
            'message': f"Reset {description} to default weight",
        }

    def clear_all_preferences(self):
        """Remove all scheduling preference overrides."""
        settings = self.SystemSetting.query.filter(
            self.SystemSetting.setting_key.like(f'{PREF_KEY_PREFIX}%')
        ).all()

        count = 0
        for setting in settings:
            self.db.session.delete(setting)
            count += 1

        if count > 0:
            self.db.session.commit()

        return {
            'success': True,
            'message': f"Cleared {count} scheduling preference(s)",
            'cleared_count': count,
        }

    def get_multipliers(self):
        """
        Load all active preference multipliers for use by CP-SAT scheduler.

        Returns:
            dict[weight_name -> float] of multipliers (only non-1.0 values)
        """
        multipliers = {}
        settings = self.SystemSetting.query.filter(
            self.SystemSetting.setting_key.like(f'{PREF_KEY_PREFIX}%')
        ).all()

        for setting in settings:
            weight_name = setting.setting_key[len(PREF_KEY_PREFIX):]
            try:
                data = json.loads(setting.setting_value)
                multiplier = float(data.get('multiplier', 1.0))
                if multiplier != 1.0:
                    multipliers[weight_name] = multiplier
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        return multipliers

    def _match_preference(self, text):
        """Match NL text to a weight constant name."""
        text_lower = text.lower().strip()

        # Direct match
        if text_lower in self.PREFERENCE_MAP:
            return self.PREFERENCE_MAP[text_lower]

        # Substring match — find the longest matching key
        best_match = None
        best_len = 0
        for keyword, weight in self.PREFERENCE_MAP.items():
            if keyword in text_lower and len(keyword) > best_len:
                best_match = weight
                best_len = len(keyword)

        return best_match

    def _parse_direction(self, direction):
        """Parse direction keyword to multiplier."""
        direction_lower = direction.lower().strip()

        # Direct match
        if direction_lower in self.DIRECTION_MAP:
            return self.DIRECTION_MAP[direction_lower]

        # Substring match
        for keyword, mult in self.DIRECTION_MAP.items():
            if keyword in direction_lower:
                return mult

        # Default to increase
        return 1.5
