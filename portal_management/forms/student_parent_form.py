"""
portal_management/forms/parent_form.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Form for creating and editing parent/guardian records.
"""

from django import forms
from django.core.exceptions import ValidationError
import re

from core.models import Parent
from .widgets import Select2Widget, DateInput


class StudentParentForm(forms.ModelForm):
    """
    Form for creating and editing parent/guardian records.
    Used in standalone parent creation and linking to students.
    """
    
    # Additional fields for linking to student (used in StudentAddParentView)
    is_primary_contact = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'role': 'switch',
        }),
        label='Primary Contact'
    )
    
    is_fee_responsible = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'role': 'switch',
        }),
        label='Fee Responsible'
    )
    
    class Meta:
        model = Parent
        fields = [
            'full_name', 'relationship', 'phone_number',
            'alternate_phone', 'email', 'address',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full name',
                'autocomplete': 'name',
            }),
            'relationship': Select2Widget(attrs={
                'data-placeholder': 'Select relationship',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 0712 345 678',
                'autocomplete': 'tel',
            }),
            'alternate_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional alternate number',
                'autocomplete': 'tel',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'parent@example.com',
                'autocomplete': 'email',
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Physical address',
                'autocomplete': 'address-line1',
            }),
        }

    def __init__(self, *args, **kwargs):
        """Initialize form with custom attributes."""
        super().__init__(*args, **kwargs)
        
        # Make email optional
        self.fields['email'].required = False
        self.fields['alternate_phone'].required = False
        self.fields['address'].required = False
        
        # Add help text and icons
        self._add_field_help()

    def _add_field_help(self):
        """Add help text and icons to fields."""
        help_texts = {
            'full_name': ('bi bi-person', 'Full name of parent/guardian'),
            'relationship': ('bi bi-tag', 'Relationship to student'),
            'phone_number': ('bi bi-telephone', 'Primary contact number'),
            'alternate_phone': ('bi bi-telephone', 'Alternate contact number (optional)'),
            'email': ('bi bi-envelope', 'Email address (optional)'),
            'address': ('bi bi-house', 'Physical address (optional)'),
        }
        
        for field_name, (icon, hint) in help_texts.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs['data-icon'] = icon
                self.fields[field_name].widget.attrs['data-hint'] = hint

    def clean_phone_number(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone_number')
        if phone:
            # Remove common separators
            phone = re.sub(r'[\s\-\(\)]', '', phone)
            
            # Basic Tanzania phone validation
            if not re.match(r'^(?:\+?255|0)[67]\d{8}$', phone):
                raise ValidationError(
                    'Enter a valid Tanzania phone number (e.g., 0712 345 678 or +255712345678)'
                )
            
            # Store cleaned number
            return phone
        return phone

    def clean_alternate_phone(self):
        """Validate alternate phone number if provided."""
        alt_phone = self.cleaned_data.get('alternate_phone')
        if alt_phone:
            alt_phone = re.sub(r'[\s\-\(\)]', '', alt_phone)
            if not re.match(r'^(?:\+?255|0)[67]\d{8}$', alt_phone):
                raise ValidationError(
                    'Enter a valid Tanzania phone number (e.g., 0712 345 678 or +255712345678)'
                )
        return alt_phone

    def clean_email(self):
        """Normalize email address."""
        email = self.cleaned_data.get('email')
        if email:
            return email.lower().strip()
        return email

    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()
        
        phone = cleaned_data.get('phone_number')
        alt_phone = cleaned_data.get('alternate_phone')
        
        # Check if primary and alternate are the same
        if phone and alt_phone and phone == alt_phone:
            self.add_error(
                'alternate_phone',
                'Alternate phone should be different from primary phone'
            )
        
        return cleaned_data

    def save(self, commit=True):
        """Save the parent instance."""
        parent = super().save(commit=False)
        
        if commit:
            try:
                parent.save()
                
                # Log the action
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Parent saved: {parent.full_name} (ID: {parent.pk})")
                
            except Exception as e:
                raise ValidationError(f"Error saving parent: {str(e)}")
        
        return parent


class StudentParentSearchForm(forms.Form):
    """
    Form for searching parents in AJAX lookups.
    """
    q = forms.CharField(
        required=False,
        min_length=2,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name or phone...',
            'autocomplete': 'off',
        })
    )


class StudentParentLinkForm(forms.Form):
    """
    Form for linking an existing parent to a student.
    """
    parent_id = forms.IntegerField(
        required=True,
        widget=forms.HiddenInput()
    )
    
    is_primary_contact = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'role': 'switch',
        })
    )
    
    is_fee_responsible = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
            'role': 'switch',
        })
    )
    
    def clean_parent_id(self):
        """Validate that the parent exists."""
        parent_id = self.cleaned_data.get('parent_id')
        try:
            parent = Parent.objects.get(pk=parent_id)
            return parent
        except Parent.DoesNotExist:
            raise ValidationError('Selected parent does not exist.')