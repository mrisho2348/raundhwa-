# portal_management/forms/school_profile_form.py

from django import forms
from core.models import SchoolProfile, EducationalLevel, Staff

class SchoolProfileForm(forms.ModelForm):
    """Form for creating and updating school profiles."""
    
    class Meta:
        model = SchoolProfile
        fields = [
            'code', 'name', 'registration_number', 'educational_level',
            'address', 'phone', 'alternative_phone', 'email', 'website',
            'motto', 'vision', 'mission', 'established_year',
            'logo', 'contact_person', 'is_active'
        ]
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
            'vision': forms.Textarea(attrs={'rows': 3}),
            'mission': forms.Textarea(attrs={'rows': 3}),
            'established_year': forms.NumberInput(attrs={'min': 1900, 'max': 2100}),
        }
        help_texts = {
            'code': 'Unique school identifier (e.g., RISS-PRIMARY)',
            'registration_number': 'Official government registration number',
            'educational_level': 'Leave blank for main school record',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Limit educational levels to only the defined types
        self.fields['educational_level'].queryset = EducationalLevel.objects.all()
        self.fields['educational_level'].required = False
        self.fields['educational_level'].empty_label = "Main School (No Specific Level)"
        
        # Limit staff to those who can be contact persons
        self.fields['contact_person'].queryset = Staff.objects.filter(
            user__is_active=True
        ).select_related('user')
        self.fields['contact_person'].required = False
        
        # Add CSS classes
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})
        
        # Special styling for textareas
        self.fields['address'].widget.attrs.update({'class': 'form-control', 'rows': 3})
        self.fields['vision'].widget.attrs.update({'class': 'form-control', 'rows': 3})
        self.fields['mission'].widget.attrs.update({'class': 'form-control', 'rows': 3})
        
        # Add placeholder for phone
        self.fields['phone'].widget.attrs.update({'placeholder': '+255 XXX XXX XXX'})
    
    def clean_code(self):
        """Validate code uniqueness with educational level consideration."""
        code = self.cleaned_data.get('code')
        educational_level = self.cleaned_data.get('educational_level')
        
        if self.instance.pk:
            # Update case - exclude current instance
            exists = SchoolProfile.objects.filter(
                code=code,
                educational_level=educational_level
            ).exclude(pk=self.instance.pk).exists()
        else:
            # Create case
            exists = SchoolProfile.objects.filter(
                code=code,
                educational_level=educational_level
            ).exists()
        
        if exists:
            if educational_level:
                raise forms.ValidationError(
                    f'A school profile with code "{code}" already exists for '
                    f'{educational_level.name}.'
                )
            else:
                raise forms.ValidationError(
                    f'A main school profile with code "{code}" already exists.'
                )
        
        return code
    
    def clean_registration_number(self):
        """Validate registration number uniqueness."""
        reg_no = self.cleaned_data.get('registration_number')
        
        if self.instance.pk:
            exists = SchoolProfile.objects.filter(
                registration_number=reg_no
            ).exclude(pk=self.instance.pk).exists()
        else:
            exists = SchoolProfile.objects.filter(registration_number=reg_no).exists()
        
        if exists:
            raise forms.ValidationError(
                f'Registration number "{reg_no}" is already in use.'
            )
        
        return reg_no