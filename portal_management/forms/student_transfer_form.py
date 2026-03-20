# portal_management/forms/student_transfer_form.py

from django import forms
from django.utils import timezone
from core.models import StudentEnrollment, StudentTransferOut, Student, School, Staff, AcademicYear
from .widgets import Select2Widget, DateInput


class StudentTransferOutForm(forms.ModelForm):
    """Form for creating/editing student transfers."""
    
    # Read-only display fields for current enrollment (client-side only)
    current_class = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True,
            'disabled': True,
        })
    )
    
    current_stream = forms.CharField(
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
        model = StudentTransferOut
        fields = [
            'student', 'transfer_date', 'destination_school', 'destination_school_name',
            'reason', 'last_class_level', 'last_academic_year', 'transfer_letter_issued',
            'transcript_issued', 'authorised_by', 'remarks'
        ]
        widgets = {
            'transfer_date': DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'destination_school': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Search for a registered school...',
                'data-allow-clear': 'true',
                'data-minimum-input-length': '2',
            }),
            'destination_school_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter school name if not in registry...',
            }),
            'last_class_level': forms.HiddenInput(),  # Hidden - populated on server
            'last_academic_year': forms.HiddenInput(),  # Hidden - populated on server
            'transfer_letter_issued': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'transcript_issued': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'authorised_by': Select2Widget(attrs={
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['student'].required = True
        self.fields['transfer_date'].required = True
        self.fields['reason'].required = True
        self.fields['authorised_by'].required = False
        self.fields['destination_school'].required = False
        self.fields['destination_school_name'].required = False
        
        # Make last_class_level and last_academic_year NOT required in form
        # They will be set automatically on the server
        self.fields['last_class_level'].required = False
        self.fields['last_academic_year'].required = False
        
        # Staff choices (only those with user accounts)
        staff_queryset = Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
        
        self.fields['authorised_by'].queryset = staff_queryset
        
        # CRITICAL FIX: Set student queryset to ALL students to avoid the "valid choice" error
        # We'll handle eligibility validation in clean_student
        self.fields['student'].queryset = Student.objects.all()
        
        # Handle existing transfer (edit mode)
        if self.instance and self.instance.pk:
            # Disable student field (cannot change student for existing transfer)
            self.fields['student'].disabled = True
            self.fields['student'].widget.attrs['disabled'] = True
            # Still need to ensure the current student is in the queryset
            self.fields['student'].queryset = Student.objects.filter(pk=self.instance.student_id)
            
            # Populate enrollment info for display
            self._populate_enrollment_info(self.instance.student)
        
        # Handle pre-selected student from URL (create mode with student_id)
        elif self.initial.get('student'):
            student = self.initial.get('student')
            if isinstance(student, Student):
                self._populate_enrollment_info(student)
                # Pre-select the student in the dropdown
                self.initial['student'] = student.pk
        
        # Add help texts
        self.fields['transfer_date'].help_text = "Date when the student officially left"
        self.fields['destination_school'].help_text = "Select from registered schools (if available)"
        self.fields['destination_school_name'].help_text = "If school is not in the registry, enter name here"
        self.fields['reason'].help_text = "Reason for the transfer"
        self.fields['authorised_by'].help_text = "Staff member who authorised this transfer"
        self.fields['transfer_letter_issued'].help_text = "Whether an official transfer letter was issued"
        self.fields['transcript_issued'].help_text = "Whether an academic transcript was issued"
    
    def _populate_enrollment_info(self, student):
        """Populate enrollment information for display."""
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        if not current_academic_year:
            return
            
        active_enrollment = student.enrollments.filter(
            status='active',
            academic_year=current_academic_year
        ).select_related('class_level', 'academic_year').first()
        
        if active_enrollment:
            self.initial['current_class'] = active_enrollment.class_level.name
            self.initial['last_class_level'] = active_enrollment.class_level_id
            
            # Get stream info if available
            stream_name = None
            if hasattr(active_enrollment, 'stream_assignment') and active_enrollment.stream_assignment:
                stream_name = active_enrollment.stream_assignment.stream_class.name
            self.initial['current_stream'] = stream_name or 'Not assigned'
            
            self.initial['current_academic_year'] = active_enrollment.academic_year.name
            self.initial['last_academic_year'] = active_enrollment.academic_year_id

    def clean_student(self):
        """Validate that the selected student is eligible for transfer."""
        student = self.cleaned_data.get('student')
        
        if not student:
            return student
        
        # Skip validation for existing records
        if self.instance and self.instance.pk:
            return student
        
        # Check if there's an active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not current_academic_year:
            raise forms.ValidationError(
                "No active academic year configured. Please set an active academic year before processing transfers."
            )
        
        # Check if student has active enrollment in current academic year
        has_active_enrollment = student.enrollments.filter(
            status='active',
            academic_year=current_academic_year
        ).exists()
        
        if not has_active_enrollment:
            raise forms.ValidationError(
                f"{student.full_name} does not have an active enrollment in the current academic year "
                f"({current_academic_year.name}). Only actively enrolled students can be transferred."
            )
        
        # Check for existing transfer record
        if hasattr(student, 'transfer_out'):
            raise forms.ValidationError(
                f"{student.full_name} already has a transfer record. "
                f"Please edit the existing record instead."
            )
        
        return student

    def clean_transfer_date(self):
        """Validate transfer date is not in the future."""
        transfer_date = self.cleaned_data.get('transfer_date')
        
        if transfer_date and transfer_date > timezone.now().date():
            raise forms.ValidationError("Transfer date cannot be in the future.")
        
        return transfer_date

    def clean(self):
        """Comprehensive validation for transfer records."""
        cleaned_data = super().clean()
        
        student = cleaned_data.get('student')
        destination_school = cleaned_data.get('destination_school')
        destination_school_name = cleaned_data.get('destination_school_name')
        transfer_date = cleaned_data.get('transfer_date')
        
        # ============================================
        # VALIDATION 1: At least one destination field must be provided
        # ============================================
        if not destination_school and not destination_school_name:
            self.add_error(
                'destination_school_name',
                'Please provide either a registered school or enter the school name.'
            )
        
        # ============================================
        # VALIDATION 2: Transfer date should be after enrollment date
        # ============================================
        if transfer_date and student:
            current_academic_year = AcademicYear.objects.filter(is_active=True).first()
            if current_academic_year:
                active_enrollment = student.enrollments.filter(
                    status='active',
                    academic_year=current_academic_year
                ).first()
                
                if active_enrollment and transfer_date < active_enrollment.enrollment_date:
                    self.add_error(
                        'transfer_date',
                        f'Transfer date cannot be before enrollment date '
                        f'({active_enrollment.enrollment_date.strftime("%Y-%m-%d")}).'
                    )
        
        return cleaned_data

    def save(self, commit=True):
        """Save the transfer and handle student status."""
        transfer = super().save(commit=False)
        
        # Get current active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        # Ensure last_class_level and last_academic_year are set from the student's active enrollment
        if not transfer.last_class_level and transfer.student and current_academic_year:
            active_enrollment = transfer.student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).first()
            if active_enrollment:
                transfer.last_class_level = active_enrollment.class_level
        
        if not transfer.last_academic_year and current_academic_year:
            transfer.last_academic_year = current_academic_year
        
        if commit:
            transfer.save()
            
            # Update student status to transferred
            transfer.student.status = 'transferred'
            transfer.student.save(update_fields=['status'])
            
            # Update all active enrollments for current academic year to 'transferred'
            if current_academic_year:
                StudentEnrollment.objects.filter(
                    student=transfer.student,
                    academic_year=current_academic_year,
                    status='active'
                ).update(status='transferred')
        
        return transfer