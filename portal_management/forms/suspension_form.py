# portal_management/forms/suspension_form.py

from django import forms
from django.utils import timezone
from core.models import StudentSuspension, Student, StudentEnrollment, Staff, AcademicYear
from .widgets import Select2Widget, DateInput


class StudentSuspensionForm(forms.ModelForm):
    """Form for creating/editing student suspensions."""
    
    # Read-only display field for current enrollment status
    enrollment_status = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True,
            'disabled': True,
        })
    )
    
    current_class = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True,
            'disabled': True,
        })
    )
    
    current_academic_year = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True,
            'disabled': True,
        })
    )
    
    class Meta:
        model = StudentSuspension
        fields = [
            'student', 'suspension_date', 'expected_return_date',
            'reason', 'authorised_by', 'is_lifted', 'lifted_date',
            'lifted_by', 'remarks'
        ]
        widgets = {
            'suspension_date': DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'expected_return_date': DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'lifted_date': DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'authorised_by': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select staff member...',
            }),
            'lifted_by': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select staff member...',
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter any additional notes...',
            }),
            'student': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Search for a student...',
                'data-allow-clear': 'true',
                'data-minimum-input-length': '2',
            }),
            'is_lifted': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['student'].required = True
        self.fields['suspension_date'].required = True
        self.fields['reason'].required = True
        self.fields['authorised_by'].required = False
        self.fields['lifted_by'].required = False
        self.fields['is_lifted'].required = False
        
        # Get current active academic year
        self.current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        # Staff choices (only those with user accounts)
        staff_queryset = Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
        
        self.fields['authorised_by'].queryset = staff_queryset
        self.fields['lifted_by'].queryset = staff_queryset
        
        # CRITICAL FIX: Set student queryset to ALL students to avoid the "valid choice" error
        # We'll handle eligibility validation in clean_student
        self.fields['student'].queryset = Student.objects.all()
        
        # Handle existing suspension (edit mode)
        if self.instance and self.instance.pk:
            # Disable student field (cannot change student for existing suspension)
            self.fields['student'].disabled = True
            self.fields['student'].widget.attrs['disabled'] = True
            # Still need to ensure the current student is in the queryset
            self.fields['student'].queryset = Student.objects.filter(pk=self.instance.student_id)
            
            # Populate enrollment info for display
            self._populate_enrollment_info(self.instance.student)
            
            # Ensure lifting fields are properly configured based on current state
            if self.instance.is_lifted:
                # Make lifted fields required and enabled
                self.fields['lifted_date'].required = True
                self.fields['lifted_by'].required = True
                self.fields['lifted_date'].widget.attrs.pop('disabled', None)
                self.fields['lifted_by'].widget.attrs.pop('disabled', None)
                
                # Pre-populate lifted fields if they exist
                if self.instance.lifted_date:
                    self.initial['lifted_date'] = self.instance.lifted_date.strftime('%Y-%m-%d')
                if self.instance.lifted_by:
                    self.initial['lifted_by'] = self.instance.lifted_by_id
            else:
                # Disable lifted fields
                self.fields['lifted_date'].widget.attrs['disabled'] = True
                self.fields['lifted_by'].widget.attrs['disabled'] = True
                self.fields['lifted_date'].required = False
                self.fields['lifted_by'].required = False
        
        # Handle pre-selected student from URL (create mode with student_id)
        elif self.initial.get('student'):
            student = self.initial.get('student')
            if isinstance(student, Student):
                self._populate_enrollment_info(student)
                # Pre-select the student in the dropdown
                self.initial['student'] = student.pk
        
        # Add help texts
        self.fields['suspension_date'].help_text = "Date when suspension takes effect"
        self.fields['expected_return_date'].help_text = "Expected return date (leave blank if indefinite)"
        self.fields['authorised_by'].help_text = "Staff member who authorised this suspension"
        self.fields['is_lifted'].help_text = "Check this box if the suspension has been lifted"
        self.fields['lifted_date'].help_text = "Date when suspension was lifted (required if lifted)"
        self.fields['lifted_by'].help_text = "Staff member who lifted the suspension (required if lifted)"
        
        # Configure lifting fields visibility based on is_lifted (for new forms)
        if not self.instance or not self.instance.pk:
            self._configure_lifting_fields()
    
    def _populate_enrollment_info(self, student):
        """Populate enrollment information for display."""
        if not self.current_academic_year:
            return
            
        active_enrollment = student.enrollments.filter(
            status='active',
            academic_year=self.current_academic_year
        ).first()
        
        if active_enrollment:
            self.initial['enrollment_status'] = 'Active'
            self.initial['current_class'] = active_enrollment.class_level.name
            self.initial['current_academic_year'] = active_enrollment.academic_year.name
    
    def _configure_lifting_fields(self):
        """Configure lifting fields based on is_lifted state for new forms."""
        self.fields['lifted_date'].widget.attrs['disabled'] = True
        self.fields['lifted_by'].widget.attrs['disabled'] = True
        self.fields['lifted_date'].required = False
        self.fields['lifted_by'].required = False

    def clean_student(self):
        """Validate that the selected student is eligible for suspension."""
        student = self.cleaned_data.get('student')
        
        if not student:
            return student
        
        # Skip validation for existing records
        if self.instance and self.instance.pk:
            return student
        
        # Check if there's an active academic year
        if not self.current_academic_year:
            raise forms.ValidationError(
                "No active academic year configured. Please set an active academic year before suspending students."
            )
        
        # Check if student has active enrollment in current academic year
        has_active_enrollment = StudentEnrollment.objects.filter(
            student=student,
            status='active',
            academic_year=self.current_academic_year
        ).exists()
        
        if not has_active_enrollment:
            raise forms.ValidationError(
                f"{student.full_name} does not have an active enrollment in the current academic year "
                f"({self.current_academic_year.name}). Only enrolled students can be suspended."
            )
        
        # Check for existing active suspension
        has_active_suspension = StudentSuspension.objects.filter(
            student=student,
            is_lifted=False
        ).exists()
        
        if has_active_suspension:
            raise forms.ValidationError(
                f"{student.full_name} already has an active suspension. "
                f"Please lift the existing suspension before creating a new one."
            )
        
        return student

    def clean_suspension_date(self):
        """Validate suspension date is not in the future."""
        suspension_date = self.cleaned_data.get('suspension_date')
        
        if suspension_date and suspension_date > timezone.now().date():
            raise forms.ValidationError("Suspension date cannot be in the future.")
        
        return suspension_date

    def clean(self):
        """Comprehensive validation for suspension records."""
        cleaned_data = super().clean()
        
        suspension_date = cleaned_data.get('suspension_date')
        expected_return_date = cleaned_data.get('expected_return_date')
        is_lifted = cleaned_data.get('is_lifted', False)
        lifted_date = cleaned_data.get('lifted_date')
        lifted_by = cleaned_data.get('lifted_by')
        
        # ============================================
        # VALIDATION 1: Expected return date must be after suspension date
        # ============================================
        if expected_return_date and suspension_date:
            if expected_return_date <= suspension_date:
                self.add_error(
                    'expected_return_date',
                    'Expected return date must be after the suspension date.'
                )
        
        # ============================================
        # VALIDATION 2: Lifting validations
        # ============================================
        if is_lifted:
            if not lifted_date:
                self.add_error(
                    'lifted_date',
                    'Lifted date is required when marking a suspension as lifted.'
                )
            elif not lifted_by:
                self.add_error(
                    'lifted_by',
                    'Lifted by (staff member) is required when marking a suspension as lifted.'
                )
            
            if lifted_date and suspension_date:
                if lifted_date < suspension_date:
                    self.add_error(
                        'lifted_date',
                        'Lifted date cannot be before the suspension date.'
                    )
        
        return cleaned_data

    def save(self, commit=True):
        """Save the suspension and handle student status."""
        suspension = super().save(commit=False)
        
        # For new suspensions, ensure they're not marked as lifted initially
        if not self.instance.pk:
            suspension.is_lifted = False
            suspension.lifted_date = None
            suspension.lifted_by = None
        
        if commit:
            suspension.save()
            
            # Update student status if this is a new suspension
            if not self.instance.pk:
                suspension.student.status = 'suspended'
                suspension.student.save(update_fields=['status'])
        
        return suspension