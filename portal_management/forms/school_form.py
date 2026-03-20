# portal_management/forms/school_form.py

from django import forms
from django.core.exceptions import ValidationError
from core.models import School, EducationalLevel
from .widgets import Select2Widget


class SchoolForm(forms.ModelForm):
    """Form for creating/editing schools."""
    
    class Meta:
        model = School
        fields = ['name', 'educational_level', 'location', 'registration_number']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter school name',
                'autocomplete': 'off',
            }),
            'educational_level': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select educational level...',
                'data-allow-clear': 'true',
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter school location (e.g., City, Region)',
                'autocomplete': 'off',
            }),
            'registration_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter registration number (optional)',
                'autocomplete': 'off',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['name'].required = True
        self.fields['educational_level'].required = True
        self.fields['location'].required = False
        self.fields['registration_number'].required = False
        
        # Order educational levels
        self.fields['educational_level'].queryset = EducationalLevel.objects.all().order_by('level_type', 'name')
        
        # Add help texts
        self.fields['name'].help_text = "Full name of the school"
        self.fields['educational_level'].help_text = "Educational level offered by this school"
        self.fields['location'].help_text = "City, region, or district where school is located"
        self.fields['registration_number'].help_text = "Official school registration number (if available)"

    def clean(self):
        """Intelligent validation for school records."""
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        educational_level = cleaned_data.get('educational_level')
        location = cleaned_data.get('location')
        
        if not name or not educational_level:
            return cleaned_data
        
        # CASE 1: Check for exact duplicate (same name, same level, same location)
        if location:
            exact_duplicate = School.objects.filter(
                name__iexact=name,
                educational_level=educational_level,
                location__iexact=location
            )
            
            if self.instance and self.instance.pk:
                exact_duplicate = exact_duplicate.exclude(pk=self.instance.pk)
            
            if exact_duplicate.exists():
                school = exact_duplicate.first()
                raise ValidationError(
                    f"A school named '{name}' in '{location}' offering "
                    f"'{educational_level.name}' already exists. "
                    f"This appears to be a duplicate record."
                )
        
        # CASE 2: Check for same name and level in different locations
        # This is ALLOWED, but we'll show a warning
        different_location = School.objects.filter(
            name__iexact=name,
            educational_level=educational_level
        )
        
        if self.instance and self.instance.pk:
            different_location = different_location.exclude(pk=self.instance.pk)
        
        if different_location.exists() and location:
            # This is allowed, but we'll add a warning message
            locations = [s.location for s in different_location if s.location]
            if locations:
                locations_str = ', '.join(locations)
                self.add_warning(
                    f"Note: '{name}' offering '{educational_level.name}' already exists in: {locations_str}. "
                    f"You are adding it in '{location}'. This is allowed as long as the locations are different."
                )
        
        # CASE 3: Check for same name in different location with different level
        # This is also ALLOWED
        
        return cleaned_data
    
    def add_warning(self, message):
        """Add a warning message to the form (non-blocking)."""
        if not hasattr(self, 'warnings'):
            self.warnings = []
        self.warnings.append(message)