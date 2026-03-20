"""
portal_management/forms/widgets.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Custom widgets for forms with premium styling.
"""

from django import forms


class Select2Widget(forms.Select):
    """
    Custom select widget with Select2 integration.
    """
    def __init__(self, attrs=None, choices=()):
        default_attrs = {'class': 'form-select select2'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, choices=choices)


class Select2MultipleWidget(forms.SelectMultiple):
    """
    Custom multiple select widget with Select2 integration.
    """
    def __init__(self, attrs=None, choices=()):
        default_attrs = {'class': 'form-select select2'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, choices=choices)


class DateInput(forms.DateInput):
    """
    Custom date input widget with HTML5 date picker.
    """
    input_type = 'date'
    
    def __init__(self, attrs=None, format=None):
        default_attrs = {'class': 'form-control'}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, format=format)


class PhoneInput(forms.TextInput):
    """
    Custom phone input widget with input masking.
    """
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control',
            'type': 'tel',
            'data-mask': 'phone',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class FileUploadInput(forms.FileInput):
    """
    Custom file upload widget with preview capability.
    """
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control',
            'accept': 'image/*',
            'data-preview': 'true',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)


class ToggleSwitchInput(forms.CheckboxInput):
    """
    Custom toggle switch widget for boolean fields.
    """
    def __init__(self, attrs=None, check_test=None):
        default_attrs = {
            'class': 'form-check-input',
            'role': 'switch',
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs, check_test=check_test)