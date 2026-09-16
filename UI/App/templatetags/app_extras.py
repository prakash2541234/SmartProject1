from django import template
import json

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, "")


@register.filter
def to_json(value):
    """Convert a Python object to JSON string."""
    try:
        return json.dumps(value, indent=2)
    except (TypeError, ValueError):
        return str(value)

