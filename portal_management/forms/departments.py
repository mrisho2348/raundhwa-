# portal_management/forms/departments.py

from django import forms
from django.core.exceptions import ValidationError
from core.models import Department


class DepartmentForm(forms.ModelForm):
    """Form for creating and updating departments."""
    
    class Meta:
        model = Department
        fields = ['name', 'code', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Computer Science',
                'autocomplete': 'off'
            }),
            'code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., CS',
                'style': 'text-transform: uppercase;',
                'autocomplete': 'off'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Brief description of the department...'
            })
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Add required field indicators
        self.fields['name'].required = True
        self.fields['code'].required = True
        
        # Add help texts
        self.fields['name'].help_text = 'The full name of the department (e.g., "Computer Science")'
        self.fields['code'].help_text = 'Short, unique identifier (e.g., "CS", "MATH", "ENG")'
        self.fields['description'].help_text = 'Brief description of the department\'s focus and offerings (optional)'
    
    def clean_code(self):
        """Validate and normalize department code."""
        code = self.cleaned_data.get('code')
        
        if not code:
            raise ValidationError('Department code is required.')
        
        # Normalize code
        code = code.strip().upper()
        
        # Check length
        if len(code) > 20:
            raise ValidationError('Department code cannot exceed 20 characters.')
        
        # Check for special characters (allow letters, numbers, underscore, hyphen)
        import re
        if not re.match(r'^[A-Z0-9_-]+$', code):
            raise ValidationError(
                'Department code can only contain letters, numbers, underscores, and hyphens.'
            )
        
        # Check uniqueness
        instance = getattr(self, 'instance', None)
        if instance and instance.pk:
            # Updating existing department
            if Department.objects.exclude(pk=instance.pk).filter(code=code).exists():
                raise ValidationError(f'Department with code "{code}" already exists.')
        else:
            # Creating new department
            if Department.objects.filter(code=code).exists():
                raise ValidationError(f'Department with code "{code}" already exists.')
        
        return code
    
    def clean_name(self):
        """Validate department name."""
        name = self.cleaned_data.get('name')
        
        if not name:
            raise ValidationError('Department name is required.')
        
        # Normalize name
        name = name.strip()
        
        # Check length
        if len(name) > 100:
            raise ValidationError('Department name cannot exceed 100 characters.')
        
        # Check for duplicate name (case-insensitive)
        instance = getattr(self, 'instance', None)
        if instance and instance.pk:
            # Updating existing department
            if Department.objects.exclude(pk=instance.pk).filter(name__iexact=name).exists():
                raise ValidationError(f'Department with name "{name}" already exists.')
        else:
            # Creating new department
            if Department.objects.filter(name__iexact=name).exists():
                raise ValidationError(f'Department with name "{name}" already exists.')
        
        return name
    
    def clean(self):
        """Cross-field validation."""
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        code = cleaned_data.get('code')
        
        # Optional: Add validation that code shouldn't be similar to name
        # if code and name and code.lower() in name.lower():
        #     self.add_warning('Consider making the code more distinct from the name.')
        
        return cleaned_data