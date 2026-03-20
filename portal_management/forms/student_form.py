"""
portal_management/forms/student_form.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Clean student form with only personal and contact information.
Enrollment and parent fields are removed - handled by separate views.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.urls import reverse_lazy
from django.utils import timezone
import re
from django.db.models import Q
from core.models import AcademicYear, ClassLevel, Staff, Student, StudentEnrollment, StudentTransferOut
from .widgets import Select2Widget, DateInput

# Relationship choices for display only (used in separate parent form)
RELATIONSHIP_CHOICES = [
    ('father', 'Father'),
    ('mother', 'Mother'),
    ('guardian', 'Guardian'),
    ('brother', 'Brother'),
    ('sister', 'Sister'),
    ('uncle', 'Uncle'),
    ('aunt', 'Aunt'),
    ('grandfather', 'Grandfather'),
    ('grandmother', 'Grandmother'),
    ('cousin', 'Cousin'),
    ('stepfather', 'Stepfather'),
    ('stepmother', 'Stepmother'),
    ('other', 'Other'),
]


class StudentForm(forms.ModelForm):
    """
    Clean student form containing only personal and contact information.
    No enrollment or parent fields - these are handled by separate views.
    Perfectly matches the premium template design.
    """
    
    class Meta:
        model = Student
        fields = [
            'first_name', 'middle_name', 'last_name',
            'gender', 'date_of_birth', 'address',
            'physical_disability', 'national_id',
            'admission_date', 'profile_picture',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name',
                'data-live-preview': 'true',
                'autocomplete': 'given-name',
            }),
            'middle_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter middle name (optional)',
                'data-live-preview': 'true',
                'autocomplete': 'additional-name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name',
                'data-live-preview': 'true',
                'autocomplete': 'family-name',
            }),
            'gender': Select2Widget(attrs={
                'data-live-preview': 'true',
                'data-placeholder': 'Select gender',
            }),
            'date_of_birth': DateInput(attrs={
                'data-live-preview': 'true',
                'max': timezone.now().date().isoformat(),
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Enter physical address',
                'autocomplete': 'address-line1',
            }),
            'physical_disability': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Specify if any',
            }),
            'national_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'YYYY-XXXXXX-XXXXX',
                'autocomplete': 'off',
            }),
            'admission_date': DateInput(attrs={
                'max': timezone.now().date().isoformat(),
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'data-max-size': '2097152',  # 2MB in bytes
            }),
        }

    def __init__(self, *args, **kwargs):
        """Initialize form with dynamic querysets and initial values."""
        super().__init__(*args, **kwargs)
        
        # Set initial admission date to today for new students
        if not self.instance.pk:
            self.fields['admission_date'].initial = timezone.now().date()
        
        # Add custom CSS classes and attributes
        self._add_custom_attributes()
        
        # Make fields optional/required as needed
        self.fields['gender'].required = False
        self.fields['date_of_birth'].required = False
        self.fields['address'].required = False
        self.fields['physical_disability'].required = False
        self.fields['national_id'].required = False
        self.fields['profile_picture'].required = False

    def _add_custom_attributes(self):
        """Add custom CSS classes and attributes to form fields."""
        # Add help text icons and tooltips
        help_texts = {
            'gender': ('bi bi-gender-ambiguous', 'Select student\'s gender'),
            'date_of_birth': ('bi bi-calendar', 'Student\'s date of birth'),
            'address': ('bi bi-house', 'Current residential address'),
            'national_id': ('bi bi-card-text', 'Format: YYYY-XXXXXX-XXXXX'),
            'physical_disability': ('bi bi-heart', 'Specify any physical disabilities or leave blank'),
            'profile_picture': ('bi bi-image', 'Upload a clear photo (max 2MB)'),
        }
        
        for field_name, (icon, hint) in help_texts.items():
            if field_name in self.fields:
                self.fields[field_name].widget.attrs['data-icon'] = icon
                self.fields[field_name].widget.attrs['data-hint'] = hint

    def clean_national_id(self):
        """Validate national ID format if provided."""
        national_id = self.cleaned_data.get('national_id')
        if national_id:
            # Remove any whitespace
            national_id = national_id.strip()
            
            # Validate format: YYYY-XXXXXX-XXXXX
            pattern = r'^\d{4}-\d{6}-\d{5}$'
            if not re.match(pattern, national_id):
                raise ValidationError(
                    'National ID must be in format: YYYY-XXXXXX-XXXXX '
                    '(e.g., 2000-123456-78901)'
                )
        return national_id

    def clean_date_of_birth(self):
        """Validate date of birth is not in the future."""
        dob = self.cleaned_data.get('date_of_birth')
        if dob and dob > timezone.now().date():
            raise ValidationError('Date of birth cannot be in the future.')
        return dob

    def clean_admission_date(self):
        """Validate admission date is not in the future."""
        admission_date = self.cleaned_data.get('admission_date')
        if admission_date and admission_date > timezone.now().date():
            raise ValidationError('Admission date cannot be in the future.')
        return admission_date

    def clean(self):
        """
        Cross-field validation.
        Ensure admission date is after date of birth if both are provided.
        """
        cleaned_data = super().clean()
        
        dob = cleaned_data.get('date_of_birth')
        admission_date = cleaned_data.get('admission_date')
        
        if dob and admission_date and admission_date < dob:
            self.add_error(
                'admission_date',
                'Admission date cannot be before date of birth.'
            )
        
        return cleaned_data

    def save(self, commit=True):
        """
        Save the student instance.
        No enrollment or parent creation - handled by separate views.
        """
        student = super().save(commit=False)
        
        if commit:
            try:
                student.save()
                
                # Log the action (optional)
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"Student {'created' if not self.instance.pk else 'updated'}: "
                    f"{student.full_name} (ID: {student.pk})"
                )
                
            except Exception as e:
                raise ValidationError(f"Error saving student: {str(e)}")
        
        return student


class StudentDraftForm(StudentForm):
    """
    Extended form for draft saving - makes all fields optional.
    Used for saving incomplete student records.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make all fields optional for drafts
        for field in self.fields:
            self.fields[field].required = False
            if hasattr(self.fields[field], 'widget'):
                self.fields[field].widget.attrs.pop('required', None)


class StudentSearchForm(forms.Form):
    """
    Form for searching/filtering students in list views.
    """
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, registration number, or national ID...',
            'autocomplete': 'off',
        })
    )
    
    status = forms.ChoiceField(
        required=False,
        choices=[('', 'All Statuses')] + Student.STATUS_CHOICES,
        widget=Select2Widget(attrs={
            'data-placeholder': 'Filter by status',
        })
    )
    
    class_level = forms.ModelChoiceField(
        required=False,
        queryset=None,  # Will be set in __init__
        widget=Select2Widget(attrs={
            'data-placeholder': 'Filter by class level',
        })
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import ClassLevel
        self.fields['class_level'].queryset = ClassLevel.objects.all().order_by('educational_level', 'order')



class StudentEnrollmentForm(forms.ModelForm):
    class Meta:
        model = StudentEnrollment
        fields = ['student', 'academic_year', 'class_level',
                  'enrollment_date', 'status', 'remarks']
        widgets = {
            'student': Select2Widget(
                attrs={
                    'class': 'form-control select2',
                    'data-placeholder': 'Search for a student...',
                    'data-allow-clear': 'true',
                    'data-minimum-input-length': '2',
                    'data-width': '100%'
                }
            ),
            'academic_year': Select2Widget(
                attrs={
                    'class': 'form-control select2',
                    'data-placeholder': 'Select academic year...',
                    'data-allow-clear': 'true',
                    'data-width': '100%'
                }
            ),
            'class_level': Select2Widget(
                attrs={
                    'class': 'form-control select2',
                    'data-placeholder': 'Select class level...',
                    'data-allow-clear': 'true',
                    'data-width': '100%'
                }
            ),            
            'enrollment_date': DateInput(
                attrs={
                    'class': 'form-control datepicker',
                    'data-provide': 'datepicker',
                    'data-date-format': 'yyyy-mm-dd',
                    'autocomplete': 'off'
                }
            ),
            'status': Select2Widget(
                attrs={
                    'class': 'form-control select2',
                    'data-placeholder': 'Select status...',
                    'data-allow-clear': 'true',
                    'data-width': '100%'
                }
            ),
            'remarks': forms.Textarea(
                attrs={
                    'class': 'form-control',
                    'rows': 2,
                    'placeholder': 'Enter any additional notes...'
                }
            ),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # ============================================
        # ACADEMIC YEAR FILTERING
        # ============================================
        if self.instance.pk:
            # Editing existing enrollment - include all years for history
            self.fields['academic_year'].queryset = AcademicYear.objects.all().order_by('-start_date')
        else:
            # New enrollment - only show active academic year
            active_years = AcademicYear.objects.filter(is_active=True).order_by('-start_date')
            self.fields['academic_year'].queryset = active_years
            
            # Set default to active year if available
            if active_years.exists() and not self.initial.get('academic_year'):
                self.initial['academic_year'] = active_years.first()
        
        # ============================================
        # CLASS LEVEL FILTERING - Independent of academic year
        # ============================================
        # Show all class levels, ordered by educational level and order
        self.fields['class_level'].queryset = ClassLevel.objects.all().select_related(
            'educational_level'
        ).order_by('educational_level__level_type', 'order')
        
        # If this is an update, keep the current selection
        if self.instance.pk and self.instance.class_level:
            self.fields['class_level'].initial = self.instance.class_level
        
        # ============================================
        # STUDENT FILTERING - only show active students
        # ============================================
        self.fields['student'].queryset = Student.objects.filter(status='active').order_by('first_name', 'last_name')
        
        # If editing, include the current student even if not active
        if self.instance.pk and self.instance.student:
            current_student = self.instance.student
            if current_student.status != 'active':
                self.fields['student'].queryset = Student.objects.filter(
                    Q(status='active') | Q(pk=current_student.pk)
                ).order_by('first_name', 'last_name')
        
        # ============================================
        # INITIAL VALUES
        # ============================================
        # Set default enrollment date to today if not set
        if not self.initial.get('enrollment_date') and not self.instance.pk:
            self.initial['enrollment_date'] = timezone.now().date()
        
        # Set default status for new enrollments
        if not self.instance.pk and not self.initial.get('status'):
            self.initial['status'] = 'active'
        
        # ============================================
        # HELPER TEXTS
        # ============================================
        self._add_help_texts()
        
        # ============================================
        # FIELD CONFIGURATION
        # ============================================
        # Make fields required
        self.fields['student'].required = True
        self.fields['academic_year'].required = True
        self.fields['class_level'].required = True
        self.fields['enrollment_date'].required = True
        self.fields['status'].required = False  # Status not required for new enrollments (defaults to active)
        
        # Configure status field choices
        if self.instance.pk:
            # For existing enrollments, show all status choices
            self.fields['status'].choices = StudentEnrollment.STATUS_CHOICES
        else:
            # For new enrollments, only show appropriate initial statuses
            self.fields['status'].choices = [
                ('active', 'Active'),
                ('suspended', 'Suspended'),
            ]
        
        # Add Select2 specific attributes for AJAX loading (for student search only)
        self.fields['student'].widget.attrs.update({
            'data-ajax-url': reverse_lazy('management:search_students_for_enrollment'),
            'data-ajax--delay': 300,
            'data-minimum-input-length': 2,
            'data-language': 'en',
        })
        
        # Class level no longer depends on academic year
        # Remove any dependent attributes if they were previously set
        
        # Group class levels by educational level for better organization in Select2
        self.fields['class_level'].label_from_instance = self._get_class_level_label
    
    def _get_class_level_label(self, obj):
        """Return a formatted label for class level including educational level"""
        return f"{obj.name} ({obj.educational_level.name})"
    
    def _add_help_texts(self):
        """Add help text to fields"""
        help_texts = {
            'student': "Search and select the student to enroll. Only active students are shown.",
            'academic_year': "Select the academic year for this enrollment. Only active years are shown for new enrollments.",
            'class_level': "Select the class level for this enrollment.",
            'enrollment_date': "Date when the student enrolled. Defaults to today.",
            'status': "Current enrollment status. New enrollments default to 'Active'.",
            'remarks': "Optional notes about this enrollment.",
        }
        
        for field_name, help_text in help_texts.items():
            self.fields[field_name].help_text = help_text
    
    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        academic_year = cleaned_data.get('academic_year')
        class_level = cleaned_data.get('class_level')
        enrollment_date = cleaned_data.get('enrollment_date')
        status = cleaned_data.get('status')
        
        errors = []
        
        # ============================================
        # VALIDATION 1: Duplicate enrollment check
        # ============================================
        if student and academic_year:
            self._validate_duplicate_enrollment(student, academic_year, errors)
        
        # ============================================
        # VALIDATION 2: Student status check
        # ============================================
        if student:
            self._validate_student_status(student, errors)
        
        # ============================================
        # VALIDATION 3: Enrollment date within academic year
        # ============================================
        if academic_year and enrollment_date:
            self._validate_enrollment_date(academic_year, enrollment_date, errors)
        
        # ============================================
        # VALIDATION 4: Class level belongs to the student's educational level
        # ============================================
        if student and class_level:
            self._validate_class_level_for_student(student, class_level, errors)
        
        # ============================================
        # VALIDATION 5: Promotion rules
        # ============================================
        if status == 'promoted' and class_level:
            self._validate_promotion(class_level, student, errors)
        
        # ============================================
        # VALIDATION 6: A-Level combination requirement (soft warning)
        # ============================================
        if class_level and class_level.educational_level.level_type == 'A_LEVEL' and not self.instance.pk:
            # For new A-Level enrollments, we'll add a message that combination must be assigned
            # This is stored in the form as a warning, not an error
            self.add_warning(
                "A-Level students must be assigned a combination after enrollment."
            )
        
        if errors:
            raise ValidationError(errors)
        
        return cleaned_data
    
    def add_warning(self, message):
        """Add a warning message to the form (non-blocking)"""
        if not hasattr(self, 'warnings'):
            self.warnings = []
        self.warnings.append(message)
    
    def _validate_duplicate_enrollment(self, student, academic_year, errors):
        """Check if student is already enrolled in this academic year"""
        existing = StudentEnrollment.objects.filter(
            student=student,
            academic_year=academic_year
        ).exclude(pk=self.instance.pk)
        
        if existing.exists():
            existing_enrollment = existing.first()
            errors.append(
                ValidationError(
                    f"{student.full_name} is already enrolled in {academic_year.name} "
                    f"(Class: {existing_enrollment.class_level.name}, Status: {existing_enrollment.get_status_display()})."
                )
            )
    
    def _validate_student_status(self, student, errors):
        """Ensure student status allows enrollment"""
        if student.status != 'active' and not self.instance.pk:
            # For new enrollments, student must be active
            errors.append(
                ValidationError(
                    f"Cannot enroll a student with status '{student.get_status_display()}'. "
                    f"Only active students can be enrolled."
                )
            )
        elif student.status != 'active' and self.instance.pk:
            # For updates, allow but add a warning
            self.add_warning(
                f"This student has status '{student.get_status_display()}'. "
                f"Consider updating the student status if needed."
            )
    
    def _validate_enrollment_date(self, academic_year, enrollment_date, errors):
        """Ensure enrollment date is within academic year"""
        if enrollment_date < academic_year.start_date or enrollment_date > academic_year.end_date:
            errors.append(
                ValidationError(
                    f"Enrollment date must be within the academic year "
                    f"({academic_year.start_date.strftime('%Y-%m-%d')} to "
                    f"{academic_year.end_date.strftime('%Y-%m-%d')})."
                )
            )
    
    def _validate_class_level_for_student(self, student, class_level, errors):
        """Ensure class level is appropriate for the student based on previous enrollments"""
        # Check if student has completed previous levels
        previous_enrollments = StudentEnrollment.objects.filter(
            student=student
        ).exclude(pk=self.instance.pk).order_by('-academic_year__start_date')
        
        if previous_enrollments.exists():
            last_enrollment = previous_enrollments.first()
            last_level = last_enrollment.class_level
            
            # Check for logical progression
            if last_level.educational_level == class_level.educational_level:
                # Same educational level - ensure order is increasing
                if class_level.order < last_level.order:
                    errors.append(
                        ValidationError(
                            f"Cannot enroll in {class_level.name} (order {class_level.order}). "
                            f"Student was previously in {last_level.name} (order {last_level.order})."
                        )
                    )
                elif class_level.order == last_level.order and last_enrollment.status == 'promoted':
                    # Same level but promoted - this is repeating
                    self.add_warning(
                        f"Student is being enrolled in the same class level ({class_level.name}) "
                        f"after being promoted. This may indicate a repetition."
                    )
            elif (last_level.educational_level.level_type == 'O_LEVEL' and 
                  class_level.educational_level.level_type == 'A_LEVEL'):
                # Moving from O-Level to A-Level - valid progression
                pass
    
    def _validate_promotion(self, class_level, student, errors):
        """Validate promotion rules"""
        # Rule 1: Cannot promote from final class level
        if class_level.is_final:
            errors.append(
                ValidationError(
                    f"'{class_level.name}' is the final class level of "
                    f"'{class_level.educational_level.name}'. "
                    f"Students at this level should be marked as 'completed', not 'promoted'."
                )
            )
        
        # Rule 2: Check if there's a next level available (warning only)
        if not self.instance.pk or self.instance.status != 'promoted':
            next_level = ClassLevel.objects.filter(
                educational_level=class_level.educational_level,
                order__gt=class_level.order
            ).first()
            
            if not next_level and student:
                # This is a warning for final levels
                if class_level.is_final:
                    # Already handled above
                    pass
                else:
                    self.add_warning(
                        f"No higher class level found for {class_level.name}. "
                        f"This student may need to complete their education."
                    )
    
    def save(self, commit=True):
        enrollment = super().save(commit=False)
        
        # Set default enrollment date if not provided
        if not enrollment.enrollment_date:
            enrollment.enrollment_date = timezone.now().date()
        
        # Set default status for new enrollments
        if not self.instance.pk and not enrollment.status:
            enrollment.status = 'active'
        
        if commit:
            enrollment.save()
            
            # If this is a new enrollment and it's A-Level, add a message about combination assignment
            if not self.instance.pk and enrollment.class_level and enrollment.class_level.educational_level.level_type == 'A_LEVEL':
                # This will be handled in the view
                pass
            
        return enrollment
    

# portal_management/forms/student_form.py (add this class)

class StudentTransferOutForm(forms.ModelForm):
    """Form for creating/editing student transfer out records."""
    
    # Read-only display fields for enrollment information
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
            'student', 'transfer_date', 'destination_school', 
            'destination_school_name', 'reason', 'last_class_level',
            'last_academic_year', 'transfer_letter_issued', 
            'transcript_issued', 'authorised_by', 'remarks'
        ]
        widgets = {
            'transfer_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'destination_school_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter school name'}),
            'remarks': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Additional notes...'}),
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'last_class_level': forms.Select(attrs={'class': 'form-select'}),
            'last_academic_year': forms.Select(attrs={'class': 'form-select'}),
            'authorised_by': forms.Select(attrs={'class': 'form-select'}),
            'student': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set required fields
        self.fields['student'].required = True
        self.fields['transfer_date'].required = True
        self.fields['reason'].required = True
        
        # Hide the last_class_level and last_academic_year fields initially
        # They will be populated automatically from the student's active enrollment
        self.fields['last_class_level'].widget = forms.HiddenInput()
        self.fields['last_academic_year'].widget = forms.HiddenInput()
        self.fields['last_class_level'].required = False
        self.fields['last_academic_year'].required = False
        
        # Make destination_school optional if destination_school_name is provided
        self.fields['destination_school'].required = False
        
        # Staff choices (only those with user accounts)
        self.fields['authorised_by'].queryset = Staff.objects.filter(
            user__is_active=True
        ).select_related('user').order_by('first_name', 'last_name')
        self.fields['authorised_by'].label = "Authorised By"
        self.fields['authorised_by'].required = False
        
        # Help texts
        self.fields['destination_school_name'].help_text = "Leave blank if selecting from registered schools"
        self.fields['destination_school'].help_text = "Select a registered school or use the text field above"
        
        # If this is an existing transfer, disable student field and populate enrollment info
        if self.instance and self.instance.pk:
            self.fields['student'].disabled = True
            self.fields['student'].widget.attrs['disabled'] = True
            
            # Set initial values for display fields
            student = self.instance.student
            active_enrollment = student.enrollments.filter(status='active').first()
            
            if active_enrollment:
                self.initial['current_class'] = active_enrollment.class_level.name
                self.initial['current_stream'] = active_enrollment.stream_assignment.stream_class.name if hasattr(active_enrollment, 'stream_assignment') else 'Not assigned'
                self.initial['current_academic_year'] = active_enrollment.academic_year.name
    
    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        
        # Validate that student is provided
        if not student and not self.instance.pk:
            raise ValidationError("Student is required.")
        
        # For new transfers, validate student has active enrollment
        if student and not self.instance.pk:
            active_enrollment = student.enrollments.filter(status='active').first()
            
            if not active_enrollment:
                raise ValidationError(
                    f"{student.full_name} does not have an active enrollment. "
                    f"Only students with active enrollment can be transferred."
                )
            
            # Automatically set last_class_level and last_academic_year from active enrollment
            cleaned_data['last_class_level'] = active_enrollment.class_level
            cleaned_data['last_academic_year'] = active_enrollment.academic_year
        
        # Ensure at least one destination is provided
        destination_school = cleaned_data.get('destination_school')
        destination_school_name = cleaned_data.get('destination_school_name')
        
        if not destination_school and not destination_school_name:
            raise ValidationError(
                "Please provide either a registered school or enter the school name."
            )
        
        # Check if student already has a transfer record (for new records)
        if student and not self.instance.pk:
            if hasattr(student, 'transfer_out'):
                raise ValidationError(
                    f"{student.full_name} already has a transfer record. "
                    "Please edit the existing record instead."
                )
        
        return cleaned_data