# portal_management/forms/student_combination_assignment_form.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import (
    StudentCombinationAssignment, Student, StudentEnrollment,
    Combination, AcademicYear, ClassLevel
)
from .widgets import Select2Widget


class StudentCombinationAssignmentForm(forms.ModelForm):
    """Form for creating/editing student combination assignments."""
    
    # Display fields
    student_full_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True,
            'disabled': True,
        })
    )
    
    student_registration = forms.CharField(
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
    
    class Meta:
        model = StudentCombinationAssignment
        fields = ['student', 'enrollment', 'combination', 'assigned_date', 'is_active', 'remarks']
        widgets = {
            'student': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Search for a student...',
                'data-allow-clear': 'true',
                'data-minimum-input-length': '2',
            }),
            'enrollment': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select enrollment...',
                'data-allow-clear': 'true',
            }),
            'combination': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select combination...',
                'data-allow-clear': 'true',
            }),
            'assigned_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any notes about this assignment (reason for change, etc.)',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['student'].required = True
        self.fields['enrollment'].required = True
        self.fields['combination'].required = True
        self.fields['assigned_date'].required = False
        self.fields['is_active'].required = False
        self.fields['remarks'].required = False
        
        # Set initial assigned date
        if not self.instance.pk and not self.initial.get('assigned_date'):
            self.initial['assigned_date'] = timezone.now().date()
        
        # Get current active academic year
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        
        # Get all eligible students (A-Level students with active enrollments)
        eligible_students = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL',
            status='active'
        ).distinct().order_by('first_name', 'last_name')
        
        self.fields['student'].queryset = eligible_students
        
        # Filter combinations to only A-Level combinations
        self.fields['combination'].queryset = Combination.objects.filter(
            educational_level__level_type='A_LEVEL'
        ).order_by('code')
        
        # IMPORTANT FIX: Set enrollment queryset based on selected student
        student_id = self.initial.get('student')
        if student_id and isinstance(student_id, Student):
            student_id = student_id.pk
        elif self.instance.pk and self.instance.student_id:
            student_id = self.instance.student_id
        
        if student_id:
            # Get all A-Level enrollments for this student
            self.fields['enrollment'].queryset = StudentEnrollment.objects.filter(
                student_id=student_id,
                class_level__educational_level__level_type='A_LEVEL'
            ).select_related('class_level', 'academic_year')
        else:
            # If no student selected, show all A-Level enrollments (will be filtered later)
            self.fields['enrollment'].queryset = StudentEnrollment.objects.filter(
                class_level__educational_level__level_type='A_LEVEL'
            ).select_related('class_level', 'academic_year')
        
        # Add help texts
        self._add_help_texts()
        
        # Add CSS classes
        for field_name, field in self.fields.items():
            if hasattr(field.widget, 'attrs') and field.widget.__class__.__name__ not in ['CheckboxInput', 'Select2Widget']:
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'form-control'
    
    def _add_help_texts(self):
        """Add helpful help texts for each field."""
        self.fields['student'].help_text = "Select the A-Level student"
        self.fields['enrollment'].help_text = "Select the enrollment for this student"
        self.fields['combination'].help_text = "Select the subject combination"
        self.fields['assigned_date'].help_text = "Date when this combination was assigned"
        self.fields['is_active'].help_text = "Whether this is the current active combination"
        self.fields['remarks'].help_text = "Any notes about this assignment"
    
    def clean_assigned_date(self):
        """Validate assigned date."""
        assigned_date = self.cleaned_data.get('assigned_date')
        
        if assigned_date and assigned_date > timezone.now().date():
            raise forms.ValidationError("Assigned date cannot be in the future.")
        
        return assigned_date
    
    def clean(self):
        """Validate the combination assignment."""
        cleaned_data = super().clean()
        
        student = cleaned_data.get('student')
        enrollment = cleaned_data.get('enrollment')
        combination = cleaned_data.get('combination')
        is_active = cleaned_data.get('is_active')
        
        # ============================================
        # VALIDATION 1: Student must be selected
        # ============================================
        if not student:
            self.add_error('student', 'Please select a student.')
            return cleaned_data
        
        # ============================================
        # VALIDATION 2: Enrollment must belong to the selected student
        # ============================================
        if enrollment and student:
            if enrollment.student_id != student.pk:
                self.add_error(
                    'enrollment',
                    f"The selected enrollment does not belong to {student.full_name}. "
                    f"Please select the correct enrollment for this student."
                )
        
        # ============================================
        # VALIDATION 3: Only A-Level students
        # ============================================
        if enrollment and enrollment.class_level.educational_level.level_type != 'A_LEVEL':
            self.add_error(
                'enrollment',
                f"This enrollment is for {enrollment.class_level.name} which is not an A-Level class. "
                f"Combination assignments are only applicable to A-Level students."
            )
        
        # ============================================
        # VALIDATION 4: Combination must match educational level
        # ============================================
        if combination and enrollment:
            if combination.educational_level != enrollment.class_level.educational_level:
                self.add_error(
                    'combination',
                    f"Combination '{combination.code}' is for {combination.educational_level.name} "
                    f"but the student is enrolled in {enrollment.class_level.educational_level.name}. "
                    f"The combination must match the student's educational level."
                )
        
        # ============================================
        # VALIDATION 5: Enrollment must be active
        # ============================================
        if enrollment and enrollment.status != 'active':
            self.add_error(
                'enrollment',
                f"This enrollment is {enrollment.get_status_display()}. "
                f"Only active enrollments can be assigned combinations."
            )
        
        # ============================================
        # VALIDATION 6: Student must be active
        # ============================================
        if student and student.status != 'active':
            self.add_error(
                'student',
                f"{student.full_name} is {student.get_status_display()}. "
                f"Only active students can be assigned combinations."
            )
        
        # ============================================
        # VALIDATION 7: Prevent duplicate active assignments
        # ============================================
        if is_active and enrollment:
            # Check if there's already an active assignment for this enrollment
            existing = StudentCombinationAssignment.objects.filter(
                enrollment=enrollment,
                is_active=True
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                # This is a warning - the save() method will handle deactivation
                self.add_warning(
                    f"This student already has an active combination assignment. "
                    f"The previous assignment will be deactivated automatically."
                )
        
        return cleaned_data
    
    def add_warning(self, message):
        """Add a warning message to the form."""
        if not hasattr(self, 'warnings'):
            self.warnings = []
        self.warnings.append(message)


class StudentCombinationAssignmentQuickForm(forms.ModelForm):
    """Simplified form for quick combination assignment."""
    
    class Meta:
        model = StudentCombinationAssignment
        fields = ['student', 'combination', 'assigned_date', 'remarks']
        widgets = {
            'student': Select2Widget(attrs={
                'class': 'form-select select2-student',
                'data-placeholder': 'Search for student...',
                'data-allow-clear': 'true',
                'data-minimum-input-length': '2',
            }),
            'combination': Select2Widget(attrs={
                'class': 'form-select select2-combination',
                'data-placeholder': 'Select combination...',
                'data-allow-clear': 'true',
            }),
            'assigned_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Optional notes...',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        self.fields['student'].required = True
        self.fields['combination'].required = True
        self.fields['assigned_date'].required = False
        self.fields['remarks'].required = False
        
        if not self.initial.get('assigned_date'):
            self.initial['assigned_date'] = timezone.now().date()
        
        # Filter students to A-Level students with active enrollments
        self.fields['student'].queryset = Student.objects.filter(
            enrollments__class_level__educational_level__level_type='A_LEVEL',
            status='active'
        ).distinct().order_by('first_name', 'last_name')
        
        self.fields['combination'].queryset = Combination.objects.filter(
            educational_level__level_type='A_LEVEL'
        ).order_by('code')