# portal_management/forms/parent_form.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import Parent, StudentParent, Student
from .widgets import Select2Widget


class ParentForm(forms.ModelForm):
    """Form for creating/editing parent/guardian information."""
    
    class Meta:
        model = Parent
        fields = ['full_name', 'relationship', 'address', 'email', 'phone_number', 'alternate_phone']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full name',
            }),
            'relationship': forms.Select(attrs={
                'class': 'form-select',
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter physical address',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 0712345678',
            }),
            'alternate_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Alternative phone number (optional)',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['full_name'].required = True
        self.fields['relationship'].required = True
        self.fields['address'].required = True
        self.fields['phone_number'].required = True
        self.fields['email'].required = False
        self.fields['alternate_phone'].required = False
        
        # Add CSS classes to all fields
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs') and 'class' not in field.widget.attrs:
                if field.widget.__class__.__name__ != 'CheckboxInput':
                    field.widget.attrs['class'] = 'form-control'
        
        # Add help texts
        self._add_help_texts()
    
    def _add_help_texts(self):
        """Add helpful help texts for each field."""
        self.fields['full_name'].help_text = "Parent/Guardian's full name (e.g., John Doe)"
        self.fields['relationship'].help_text = "Relationship to the student"
        self.fields['address'].help_text = "Physical address of parent/guardian"
        self.fields['email'].help_text = "Email address for communication (optional)"
        self.fields['phone_number'].help_text = "Primary contact number (9-12 digits)"
        self.fields['alternate_phone'].help_text = "Alternative contact number (optional)"
    
    def clean_phone_number(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone_number')
        
        if phone:
            # Remove any non-digit characters
            phone = ''.join(filter(str.isdigit, phone))
            
            # Basic phone number validation
            if len(phone) < 9:
                raise forms.ValidationError("Phone number must be at least 9 digits.")
            
            if len(phone) > 12:
                raise forms.ValidationError("Phone number cannot exceed 12 digits.")
            
            # Check if starts with valid prefix (0 or 255)
            if not phone.startswith(('0', '255', '7')):
                raise forms.ValidationError(
                    "Phone number should start with 0 (e.g., 0712345678) or 255 (e.g., 255712345678)."
                )
        
        return phone
    
    def clean_alternate_phone(self):
        """Validate alternate phone number."""
        alternate = self.cleaned_data.get('alternate_phone')
        phone = self.cleaned_data.get('phone_number')
        
        if alternate:
            # Remove any non-digit characters
            alternate = ''.join(filter(str.isdigit, alternate))
            
            # Check if same as primary
            if alternate == phone:
                raise forms.ValidationError(
                    "Alternate phone number cannot be the same as the primary phone number."
                )
            
            # Basic validation
            if len(alternate) < 9:
                raise forms.ValidationError("Phone number must be at least 9 digits.")
            
            if len(alternate) > 12:
                raise forms.ValidationError("Phone number cannot exceed 12 digits.")
        
        return alternate
    
    def clean_email(self):
        """Clean email field and check for duplicates."""
        email = self.cleaned_data.get('email')
        
        if email:
            email = email.lower().strip()
            
            # Check if email already exists (for existing parents)
            existing = Parent.objects.filter(
                email=email
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise forms.ValidationError(
                    "A parent with this email already exists."
                )
        
        return email
    
    def clean_full_name(self):
        """Clean and format full name."""
        full_name = self.cleaned_data.get('full_name')
        
        if full_name:
            # Capitalize first letter of each word
            full_name = ' '.join(word.capitalize() for word in full_name.split())
        
        return full_name
    
    def clean(self):
        """Additional cross-field validation."""
        cleaned_data = super().clean()
        
        phone = cleaned_data.get('phone_number')
        email = cleaned_data.get('email')
        
        # Ensure at least one contact method is provided
        if not phone and not email:
            self.add_error(
                'phone_number',
                'Please provide at least a phone number or email address for contact.'
            )
        
        return cleaned_data


class StudentParentForm(forms.ModelForm):
    """Form for linking a student with a parent."""
    
    student = forms.ModelChoiceField(
        queryset=Student.objects.all(),
        widget=Select2Widget(attrs={
            'class': 'form-select select2-student',
            'data-placeholder': 'Search for a student...',
            'data-allow-clear': 'true',
            'data-minimum-input-length': '2',
        }),
        required=True,
        error_messages={
            'required': 'Please select a student.',
            'invalid_choice': 'Please select a valid student.',
        }
    )
    
    parent = forms.ModelChoiceField(
        queryset=Parent.objects.all(),
        widget=Select2Widget(attrs={
            'class': 'form-select select2-parent',
            'data-placeholder': 'Search for a parent...',
            'data-allow-clear': 'true',
            'data-minimum-input-length': '2',
        }),
        required=True,
        error_messages={
            'required': 'Please select a parent/guardian.',
            'invalid_choice': 'Please select a valid parent/guardian.',
        }
    )
    
    class Meta:
        model = StudentParent
        fields = ['student', 'parent', 'is_primary_contact', 'is_fee_responsible', 'fee_responsible_from']
        widgets = {
            'fee_responsible_from': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'is_primary_contact': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'is_fee_responsible': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['student'].required = True
        self.fields['parent'].required = True
        self.fields['is_primary_contact'].required = False
        self.fields['is_fee_responsible'].required = False
        self.fields['fee_responsible_from'].required = False
        
        # Add help texts
        self._add_help_texts()
        
        # Add CSS classes
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs') and field.widget.__class__.__name__ not in ['CheckboxInput', 'Select2Widget']:
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'form-control'
    
    def _add_help_texts(self):
        """Add helpful help texts for each field."""
        self.fields['student'].help_text = "Select the student to link"
        self.fields['parent'].help_text = "Select the parent/guardian to link"
        self.fields['is_primary_contact'].help_text = "Check if this is the primary contact for this student"
        self.fields['is_fee_responsible'].help_text = "Check if this parent is responsible for paying fees"
        self.fields['fee_responsible_from'].help_text = "Date from which this parent became fee responsible (if applicable)"
    
    def clean_fee_responsible_from(self):
        """Validate fee responsible from date."""
        fee_date = self.cleaned_data.get('fee_responsible_from')
        is_fee_responsible = self.cleaned_data.get('is_fee_responsible')
        
        if is_fee_responsible and not fee_date:
            raise forms.ValidationError(
                "Please specify the date from which this parent became fee responsible."
            )
        
        if fee_date and fee_date > timezone.now().date():
            raise forms.ValidationError(
                "Fee responsible date cannot be in the future."
            )
        
        return fee_date
    
    def clean(self):
        """Validate the student-parent relationship."""
        cleaned_data = super().clean()
        
        student = cleaned_data.get('student')
        parent = cleaned_data.get('parent')
        
        if student and parent:
            # Check if relationship already exists
            existing = StudentParent.objects.filter(
                student=student,
                parent=parent
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise ValidationError(
                    f"{parent.full_name} is already linked to {student.full_name}."
                )
            
            # If this parent is marked as primary contact, ensure no other primary contact for this student
            is_primary = cleaned_data.get('is_primary_contact')
            if is_primary:
                other_primary = StudentParent.objects.filter(
                    student=student,
                    is_primary_contact=True
                ).exclude(pk=self.instance.pk if self.instance else None)
                
                if other_primary.exists():
                    other_parent = other_primary.first().parent
                    self.add_error(
                        'is_primary_contact',
                        f"{student.full_name} already has {other_parent.full_name} as the primary contact. "
                        f"Only one parent can be the primary contact per student."
                    )
            
            # If this parent is marked as fee responsible, ensure no other fee responsible for this student
            is_fee = cleaned_data.get('is_fee_responsible')
            if is_fee:
                other_fee = StudentParent.objects.filter(
                    student=student,
                    is_fee_responsible=True
                ).exclude(pk=self.instance.pk if self.instance else None)
                
                if other_fee.exists():
                    other_parent = other_fee.first().parent
                    self.add_error(
                        'is_fee_responsible',
                        f"{student.full_name} already has {other_parent.full_name} as the fee responsible parent. "
                        f"Only one parent can be the fee responsible per student."
                    )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the student-parent relationship."""
        relationship = super().save(commit=False)
        
        # Ensure fee_responsible_from is set if fee responsible
        if relationship.is_fee_responsible and not relationship.fee_responsible_from:
            relationship.fee_responsible_from = timezone.now().date()
        
        if commit:
            relationship.save()
            
            # If this is the only relationship for the student, automatically make it primary contact
            if not StudentParent.objects.filter(student=relationship.student).exclude(pk=relationship.pk).exists():
                relationship.is_primary_contact = True
                relationship.save(update_fields=['is_primary_contact'])
        
        return relationship


class ParentQuickCreateForm(forms.ModelForm):
    """Simplified form for quick parent creation (used in modals)."""
    
    class Meta:
        model = Parent
        fields = ['full_name', 'relationship', 'phone_number', 'email']
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter full name',
            }),
            'relationship': forms.Select(attrs={
                'class': 'form-select',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 0712345678',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['full_name'].required = True
        self.fields['relationship'].required = True
        self.fields['phone_number'].required = True
        self.fields['email'].required = False
    
    def clean_phone_number(self):
        """Validate phone number format."""
        phone = self.cleaned_data.get('phone_number')
        
        if phone:
            phone = ''.join(filter(str.isdigit, phone))
            
            if len(phone) < 9 or len(phone) > 12:
                raise forms.ValidationError("Phone number must be between 9 and 12 digits.")
        
        return phone
    
    def clean_full_name(self):
        """Clean and format full name."""
        full_name = self.cleaned_data.get('full_name')
        
        if full_name:
            full_name = ' '.join(word.capitalize() for word in full_name.split())
        
        return full_name
    
    def save(self, commit=True):
        """Save the parent with default address."""
        parent = super().save(commit=False)
        
        # Set default address if not provided
        if not parent.address:
            parent.address = "Not provided"
        
        if commit:
            parent.save()
        
        return parent