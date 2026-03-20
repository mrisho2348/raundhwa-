# portal_management/forms/student_withdrawal_form.py

from django import forms
from django.utils import timezone
from core.models import StudentEnrollment, StudentWithdrawal, Student, Staff, AcademicYear, ClassLevel
from .widgets import Select2Widget, DateInput


class StudentWithdrawalForm(forms.ModelForm):
    """Form for creating/editing student withdrawals."""
    
    # Read-only display fields for current enrollment
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
        model = StudentWithdrawal
        fields = [
            'student', 'withdrawal_date', 'reason', 'last_class_level',
            'last_academic_year', 'authorised_by', 'transcript_issued', 'remarks'
        ]
        widgets = {
            'withdrawal_date': DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'last_class_level': forms.HiddenInput(),  # Hidden - populated on server
            'last_academic_year': forms.HiddenInput(),  # Hidden - populated on server
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
        self.fields['withdrawal_date'].required = True
        self.fields['reason'].required = True
        self.fields['authorised_by'].required = False
        
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
        
        # Handle existing withdrawal (edit mode)
        if self.instance and self.instance.pk:
            # Disable student field (cannot change student for existing withdrawal)
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
        self.fields['withdrawal_date'].help_text = "The last date the student attended school"
        self.fields['reason'].help_text = "Reason for the withdrawal"
        self.fields['authorised_by'].help_text = "Staff member who authorised this withdrawal"
        self.fields['transcript_issued'].help_text = "Whether an academic transcript was issued"
        self.fields['remarks'].help_text = "Additional notes about this withdrawal"
    
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
        """Validate that the selected student is eligible for withdrawal."""
        student = self.cleaned_data.get('student')
        
        if not student:
            return student
        
        # Skip validation for existing records
        if self.instance and self.instance.pk:
            return student
        
        # Check if student already has a withdrawal record
        if hasattr(student, 'withdrawal'):
            raise forms.ValidationError(
                f"{student.full_name} already has a withdrawal record. "
                f"Please edit the existing record instead."
            )
        
        # Check if student has a transfer record (mutually exclusive)
        if hasattr(student, 'transfer_out'):
            raise forms.ValidationError(
                f"{student.full_name} already has a transfer out record. "
                f"A student cannot be both transferred and withdrawn."
            )
        
        # Check if there's an active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not current_academic_year:
            raise forms.ValidationError(
                "No active academic year configured. Please set an active academic year before processing withdrawals."
            )
        
        # Check if student has active enrollment in current academic year
        has_active_enrollment = student.enrollments.filter(
            status='active',
            academic_year=current_academic_year
        ).exists()
        
        if not has_active_enrollment:
            raise forms.ValidationError(
                f"{student.full_name} does not have an active enrollment in the current academic year "
                f"({current_academic_year.name}). Only actively enrolled students can be withdrawn."
            )
        
        return student

    def clean_withdrawal_date(self):
        """Validate withdrawal date is not in the future."""
        withdrawal_date = self.cleaned_data.get('withdrawal_date')
        
        if withdrawal_date and withdrawal_date > timezone.now().date():
            raise forms.ValidationError("Withdrawal date cannot be in the future.")
        
        return withdrawal_date

    def clean(self):
        """Comprehensive validation for withdrawal records."""
        cleaned_data = super().clean()
        
        student = cleaned_data.get('student')
        withdrawal_date = cleaned_data.get('withdrawal_date')
        
        # ============================================
        # VALIDATION 1: Withdrawal date should be after enrollment date
        # ============================================
        if withdrawal_date and student:
            current_academic_year = AcademicYear.objects.filter(is_active=True).first()
            if current_academic_year:
                active_enrollment = student.enrollments.filter(
                    status='active',
                    academic_year=current_academic_year
                ).first()
                
                if active_enrollment and withdrawal_date < active_enrollment.enrollment_date:
                    self.add_error(
                        'withdrawal_date',
                        f'Withdrawal date cannot be before enrollment date '
                        f'({active_enrollment.enrollment_date.strftime("%Y-%m-%d")}).'
                    )
        
        return cleaned_data

    def save(self, commit=True):
        """Save the withdrawal and handle student status."""
        withdrawal = super().save(commit=False)
        
        # Get current active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        # Ensure last_class_level and last_academic_year are set from the student's active enrollment
        if not withdrawal.last_class_level and withdrawal.student and current_academic_year:
            active_enrollment = withdrawal.student.enrollments.filter(
                status='active',
                academic_year=current_academic_year
            ).first()
            if active_enrollment:
                withdrawal.last_class_level = active_enrollment.class_level
        
        if not withdrawal.last_academic_year and current_academic_year:
            withdrawal.last_academic_year = current_academic_year
        
        if commit:
            withdrawal.save()
            
            # Update student status to withdrawn
            withdrawal.student.status = 'withdrawn'
            withdrawal.student.save(update_fields=['status'])
            
            # Update all active enrollments for current academic year to 'withdrawn'
            if current_academic_year:
                StudentEnrollment.objects.filter(
                    student=withdrawal.student,
                    academic_year=current_academic_year,
                    status='active'
                ).update(status='withdrawn')
        
        return withdrawal