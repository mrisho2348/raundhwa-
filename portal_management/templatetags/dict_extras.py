# templatetags/dict_extras.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if dictionary is None:
        return 0
    return dictionary.get(key, 0)

@register.filter
def values_sum(dictionary):
    """Sum all values in dictionary"""
    if dictionary is None:
        return 0
    return sum(dictionary.values())