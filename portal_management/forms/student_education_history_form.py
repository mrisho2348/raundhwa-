# portal_management/forms/student_education_history_form.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from core.models import (
    AcademicYear, StudentEducationHistory, Student, School, Combination, 
    EducationalLevel, DivisionScale, StudentEnrollment, ClassLevel
)
from .widgets import Select2Widget, DateInput


class StudentEducationHistoryForm(forms.ModelForm):
    """Form for creating/editing student education history."""
    
    # Display fields for level type (read-only)
    educational_level_type = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True,
            'disabled': True,
        })
    )
    
    # Display field for school level info
    school_level_info = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True,
            'disabled': True,
        })
    )
    
    # Custom field for class completed with select2
    class_completed = forms.ChoiceField(
        required=True,
        choices=[],
        widget=Select2Widget(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select class completed...',
            'data-allow-clear': 'true',
        })
    )
    
    # Custom field for grade with select2
    grade = forms.ChoiceField(
        required=False,
        choices=[],
        widget=Select2Widget(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select grade...',
            'data-allow-clear': 'true',
        })
    )
    
    # Custom field for division with select2
    division = forms.ChoiceField(
        required=False,
        choices=[],
        widget=Select2Widget(attrs={
            'class': 'form-select',
            'data-placeholder': 'Select division...',
            'data-allow-clear': 'true',
        })
    )
    
    class Meta:
        model = StudentEducationHistory
        fields = [
            'student', 'school', 'class_completed', 'completion_year',
            'examination_number', 'combination', 'grade', 'division',
            'total_points', 'is_transfer', 'remarks'
        ]
        widgets = {
            'completion_year': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1950,
                'max': 2100,
                'placeholder': 'e.g., 2020',
            }),
            'examination_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'NECTA index number (e.g., PS123456789)',
            }),
            'total_points': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., 7, 12, 21',
            }),
            'is_transfer': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Any additional notes about this education history...',
            }),
            'student': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Search for a student...',
                'data-allow-clear': 'true',
                'data-minimum-input-length': '2',
            }),
            'school': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Search for a school...',
                'data-allow-clear': 'true',
                'data-minimum-input-length': '2',
            }),
            'combination': Select2Widget(attrs={
                'class': 'form-select',
                'data-placeholder': 'Select combination (A-Level only)...',
                'data-allow-clear': 'true',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set field requirements
        self.fields['student'].required = True
        self.fields['school'].required = False
        self.fields['completion_year'].required = False
        self.fields['examination_number'].required = False
        self.fields['combination'].required = False
        self.fields['total_points'].required = False
        self.fields['is_transfer'].required = False
        
        # Set student queryset
        self.fields['student'].queryset = Student.objects.all().order_by('first_name', 'last_name')
        
        # School queryset with educational level prefetched
        self.fields['school'].queryset = School.objects.select_related('educational_level').all().order_by('name')
        
        # Combination queryset (initially empty)
        self.fields['combination'].queryset = Combination.objects.none()
        
        # Set up choices for class levels
        self._setup_class_level_choices()
        
        # Set up choices for grades
        self._setup_grade_choices()
        
        # Set up choices for divisions
        self._setup_division_choices()
        
        # If editing an existing record, populate educational level info
        if self.instance and self.instance.pk:
            self._populate_level_info(self.instance.school)
            self._filter_combinations(self.instance.school)
            self._set_field_visibility(self.instance.school)
            self._set_selected_values(self.instance)
        
        # Add dynamic filtering for combinations based on school selection
        if 'school' in self.data:
            try:
                school_id = int(self.data.get('school'))
                school = School.objects.get(pk=school_id)
                self._filter_combinations(school)
                self._populate_level_info(school)
                self._set_field_visibility(school)
            except (ValueError, TypeError, School.DoesNotExist):
                pass
        elif self.instance.pk and self.instance.school:
            self._filter_combinations(self.instance.school)
        
        # Add CSS classes
        self._add_css_classes()
        
        # Add help texts
        self._add_help_texts()
    
    def _setup_class_level_choices(self):
        """Set up choices for class completed field."""
        choices = [('', 'Select class completed...')]
        
        # Get all class levels ordered by educational level and order
        class_levels = ClassLevel.objects.select_related('educational_level').all().order_by(
            'educational_level__level_type', 'order'
        )
        
        current_educational_level = None
        for class_level in class_levels:
            if current_educational_level != class_level.educational_level:
                current_educational_level = class_level.educational_level
                choices.append(('__header__', f'--- {current_educational_level.name} ---'))
            
            choices.append((
                class_level.id,
                f"{class_level.name} ({class_level.educational_level.code})"
            ))
        
        self.fields['class_completed'].choices = choices
    
    def _setup_grade_choices(self):
        """Set up choices for grade field."""
        choices = [('', 'Select grade...')]
        
        # Standard PSLE grades
        grade_choices = [
            ('A', 'A - Excellent'),
            ('B', 'B - Very Good'),
            ('C', 'C - Good'),
            ('D', 'D - Satisfactory'),
            ('E', 'E - Fair'),
            ('F', 'F - Fail'),
        ]
        
        for value, label in grade_choices:
            choices.append((value, label))
        
        self.fields['grade'].choices = choices
    
    def _setup_division_choices(self):
        """Set up choices for division field."""
        choices = [('', 'Select division...')]
        
        # Standard NECTA divisions
        division_choices = [
            ('I', 'Division I'),
            ('II', 'Division II'),
            ('III', 'Division III'),
            ('IV', 'Division IV'),
            ('0', 'Division 0'),
        ]
        
        for value, label in division_choices:
            choices.append((value, label))
        
        self.fields['division'].choices = choices
    
    def _set_selected_values(self, instance):
        """Set selected values for choice fields."""
        if instance.class_completed:
            # Try to find the class level by name
            try:
                class_level = ClassLevel.objects.get(name=instance.class_completed)
                self.initial['class_completed'] = class_level.id
            except ClassLevel.DoesNotExist:
                self.initial['class_completed'] = instance.class_completed
        
        if instance.grade:
            self.initial['grade'] = instance.grade
        
        if instance.division:
            self.initial['division'] = instance.division
    
    def _add_css_classes(self):
        """Add CSS classes to form fields."""
        for field_name, field in self.fields.items():
            if field.widget.__class__.__name__ not in ['CheckboxInput', 'Select2Widget']:
                if 'class' not in field.widget.attrs:
                    field.widget.attrs['class'] = 'form-control'
    
    def _add_help_texts(self):
        """Add helpful help texts for each field."""
        self.fields['school'].help_text = "School where the student previously studied"
        self.fields['class_completed'].help_text = "The class level completed at the previous school"
        self.fields['completion_year'].help_text = "Year of completion (e.g., 2020)"
        self.fields['examination_number'].help_text = "NECTA index number from previous level"
        self.fields['combination'].help_text = "For A-Level history only"
        self.fields['grade'].help_text = "Overall PSLE grade (Primary level only)"
        self.fields['division'].help_text = "NECTA division (O-Level/A-Level only)"
        self.fields['total_points'].help_text = "Best 7 subject points total (O-Level/A-Level only)"
        self.fields['is_transfer'].help_text = "Check if this student transferred from this school"
    
    def _populate_level_info(self, school):
        """Populate the educational level information based on the selected school."""
        if school and school.educational_level:
            level_type_display = school.educational_level.get_level_type_display()
            self.initial['educational_level_type'] = level_type_display
            self.initial['school_level_info'] = f"{school.educational_level.name} ({level_type_display})"
    
    def _filter_combinations(self, school):
        """Filter combinations based on the school's educational level."""
        if school and school.educational_level and school.educational_level.level_type == 'A_LEVEL':
            self.fields['combination'].queryset = Combination.objects.filter(
                educational_level=school.educational_level
            ).order_by('code')
        else:
            self.fields['combination'].queryset = Combination.objects.none()
    
    def _set_field_visibility(self, school):
        """Set field visibility and requirements based on educational level."""
        if not school or not school.educational_level:
            return
        
        level_type = school.educational_level.level_type
        
        # Default all result fields to not required
        self.fields['grade'].required = False
        self.fields['division'].required = False
        self.fields['total_points'].required = False
        self.fields['combination'].required = False
        
        # Set visibility based on level type
        if level_type == 'PRIMARY':
            # Primary: show grade, hide division, points, combination
            self.fields['grade'].required = True
            self.fields['grade'].help_text = "Overall PSLE grade (e.g., A, B, C) - Required"
            self.fields['division'].widget = forms.HiddenInput()
            self.fields['total_points'].widget = forms.HiddenInput()
            self.fields['combination'].widget = forms.HiddenInput()
            
        elif level_type == 'O_LEVEL':
            # O-Level: show division and points, hide grade and combination
            self.fields['division'].required = True
            self.fields['total_points'].required = True
            self.fields['division'].help_text = "NECTA division (I, II, III, IV, 0) - Required"
            self.fields['total_points'].help_text = "Best 7 subject points total - Required"
            self.fields['grade'].widget = forms.HiddenInput()
            self.fields['combination'].widget = forms.HiddenInput()
            
        elif level_type == 'A_LEVEL':
            # A-Level: show division, points, and combination
            self.fields['division'].required = True
            self.fields['total_points'].required = True
            self.fields['combination'].required = False
            self.fields['division'].help_text = "NECTA division (I, II, III, IV, 0) - Required"
            self.fields['total_points'].help_text = "Total points - Required"
            self.fields['combination'].help_text = "Subject combination (Optional)"
            self.fields['grade'].widget = forms.HiddenInput()
    
    def _get_student_current_enrollment(self, student):
        """Get the student's current active enrollment."""
        if not student:
            return None
        
        current_academic_year = AcademicYear.objects.filter(is_active=True).first()
        if not current_academic_year:
            return None
        
        return student.enrollments.filter(
            status='active',
            academic_year=current_academic_year
        ).select_related('class_level__educational_level').first()
    
    def clean_completion_year(self):
        """Validate completion year."""
        completion_year = self.cleaned_data.get('completion_year')
        
        if completion_year:
            current_year = timezone.now().year
            if completion_year > current_year:
                raise forms.ValidationError("Completion year cannot be in the future.")
            if completion_year < 1950:
                raise forms.ValidationError("Completion year must be after 1950.")
        
        return completion_year
    
    def clean_class_completed(self):
        """Validate class completed and convert to string."""
        class_completed_value = self.cleaned_data.get('class_completed')
        
        if class_completed_value:
            # If it's a number (ID from select), get the class level name
            try:
                class_level = ClassLevel.objects.get(pk=int(class_completed_value))
                return class_level.name
            except (ValueError, ClassLevel.DoesNotExist):
                # If it's not a number, return as is (for backward compatibility)
                return class_completed_value
        
        return class_completed_value
    
    def clean_grade(self):
        """Validate grade format."""
        grade = self.cleaned_data.get('grade')
        
        if grade:
            grade = grade.upper().strip()
            valid_grades = ['A', 'B', 'C', 'D', 'E', 'F', 'S']
            if grade not in valid_grades:
                raise forms.ValidationError(f"Grade must be one of: {', '.join(valid_grades)}")
        
        return grade
    
    def clean_division(self):
        """Validate division format."""
        division = self.cleaned_data.get('division')
        
        if division:
            division = division.upper().strip()
            valid_divisions = ['I', 'II', 'III', 'IV', '0']
            if division not in valid_divisions:
                raise forms.ValidationError(f"Division must be one of: {', '.join(valid_divisions)}")
        
        return division
    
    def clean_total_points(self):
        """Validate total points."""
        total_points = self.cleaned_data.get('total_points')
        
        if total_points is not None and total_points < 0:
            raise forms.ValidationError("Total points cannot be negative.")
        
        if total_points is not None and total_points > 35:
            raise forms.ValidationError("Total points cannot exceed 35 (maximum for best 7 subjects).")
        
        return total_points
    
    def clean(self):
        """Comprehensive validation based on educational level and current enrollment."""
        cleaned_data = super().clean()
        
        student = cleaned_data.get('student')
        school = cleaned_data.get('school')
        grade = cleaned_data.get('grade')
        division = cleaned_data.get('division')
        total_points = cleaned_data.get('total_points')
        combination = cleaned_data.get('combination')
        completion_year = cleaned_data.get('completion_year')
        class_completed_raw = cleaned_data.get('class_completed')
        
        # Get the actual class completed name
        class_completed = None
        try:
            if class_completed_raw and str(class_completed_raw).isdigit():
                class_level = ClassLevel.objects.get(pk=int(class_completed_raw))
                class_completed = class_level.name
            else:
                class_completed = class_completed_raw
        except (ValueError, ClassLevel.DoesNotExist):
            class_completed = class_completed_raw
        
        # ============================================
        # VALIDATION 1: Student must exist
        # ============================================
        if not student:
            self.add_error('student', 'Please select a student.')
            return cleaned_data
        
        # ============================================
        # VALIDATION 2: Class completed is required
        # ============================================
        if not class_completed:
            self.add_error('class_completed', 'Please select the class completed.')
            return cleaned_data
        
        # ============================================
        # VALIDATION 3: Get educational level type from school
        # ============================================
        level_type = None
        if school and school.educational_level:
            level_type = school.educational_level.level_type
        elif not school:
            self.add_error(
                'school',
                'Please select a school to determine the educational level.'
            )
            return cleaned_data
        
        # ============================================
        # VALIDATION 4: Get student's current enrollment (if exists)
        # ============================================
        current_enrollment = self._get_student_current_enrollment(student)
        
        # ============================================
        # VALIDATION 5: Validate completion year against current enrollment
        # ============================================
        if current_enrollment and completion_year:
            enrollment_year = current_enrollment.academic_year.start_date.year
            
            # For students already enrolled, completion year must be <= enrollment year
            if completion_year > enrollment_year:
                self.add_error(
                    'completion_year',
                    f"Completion year ({completion_year}) cannot be after the student's "
                    f"enrollment year ({enrollment_year}) at this school. "
                    f"The student is already enrolled in {current_enrollment.academic_year.name}."
                )
        
        # ============================================
        # VALIDATION 6: Validate class completed against current enrollment class level
        # ============================================
        if current_enrollment and class_completed:
            current_class_level = current_enrollment.class_level
            current_class_order = current_class_level.order
            current_educational_level = current_class_level.educational_level
            
            # Try to find the completed class level in the database
            completed_class_level = None
            try:
                completed_class_level = ClassLevel.objects.filter(
                    name=class_completed,
                    educational_level=current_educational_level
                ).first()
                
                if not completed_class_level:
                    # Try to find by name pattern
                    completed_class_level = ClassLevel.objects.filter(
                        name__icontains=class_completed,
                        educational_level=current_educational_level
                    ).first()
            except:
                pass
            
            if completed_class_level:
                completed_class_order = completed_class_level.order
                
                # The completed class level should not be greater than the current class level
                if completed_class_order > current_class_order:
                    self.add_error(
                        'class_completed',
                        f"The completed class level ({class_completed}) cannot be higher than "
                        f"the student's current class level ({current_class_level.name}). "
                        f"The student is already enrolled in {current_class_level.name} "
                        f"for {current_enrollment.academic_year.name}."
                    )
        
        # ============================================
        # VALIDATION 7: PRIMARY level validation
        # ============================================
        if level_type == 'PRIMARY':
            # Only grade is allowed for primary
            if division:
                self.add_error(
                    'division',
                    'Division is not applicable for Primary level history. '
                    'Primary (PSLE) results use an overall grade only.'
                )
            if total_points is not None:
                self.add_error(
                    'total_points',
                    'Points are not applicable for Primary level history. '
                    'Primary (PSLE) results use an overall grade only.'
                )
            if combination:
                self.add_error(
                    'combination',
                    'Combination is not applicable for Primary level history.'
                )
            
            # Require grade for primary
            if not grade:
                self.add_error(
                    'grade',
                    'Overall PSLE grade is required for Primary level history.'
                )
        
        # ============================================
        # VALIDATION 8: O-LEVEL validation
        # ============================================
        elif level_type == 'O_LEVEL':
            # Only division and total_points are allowed for O-Level
            if grade:
                self.add_error(
                    'grade',
                    'Overall grade is not applicable for O-Level history. '
                    'O-Level results use division and points only.'
                )
            if combination:
                self.add_error(
                    'combination',
                    'Combination is not applicable for O-Level history.'
                )
            
            # Validate division against DivisionScale if available
            if division and school and school.educational_level:
                valid_divisions = DivisionScale.objects.filter(
                    education_level=school.educational_level
                ).values_list('division', flat=True)
                
                if valid_divisions and division not in valid_divisions:
                    valid_divisions_list = ', '.join(valid_divisions)
                    self.add_error(
                        'division',
                        f"Division '{division}' is not valid for {school.educational_level.name}. "
                        f"Valid divisions are: {valid_divisions_list}"
                    )
            
            # Require division and points for O-Level
            if not division:
                self.add_error('division', 'Division is required for O-Level history.')
            if total_points is None:
                self.add_error('total_points', 'Total points are required for O-Level history.')
        
        # ============================================
        # VALIDATION 9: A-LEVEL validation
        # ============================================
        elif level_type == 'A_LEVEL':
            # Only division and total_points are allowed for A-Level
            if grade:
                self.add_error(
                    'grade',
                    'Overall grade is not applicable for A-Level history.'
                )
            
            # Combination validation
            if combination and school and school.educational_level:
                if combination.educational_level != school.educational_level:
                    self.add_error(
                        'combination',
                        f"Combination '{combination.code}' belongs to "
                        f"'{combination.educational_level.name}', but the school is for "
                        f"'{school.educational_level.name}'. Please select a valid combination."
                    )
            
            # Validate division against DivisionScale
            if division and school and school.educational_level:
                valid_divisions = DivisionScale.objects.filter(
                    education_level=school.educational_level
                ).values_list('division', flat=True)
                
                if valid_divisions and division not in valid_divisions:
                    valid_divisions_list = ', '.join(valid_divisions)
                    self.add_error(
                        'division',
                        f"Division '{division}' is not valid for {school.educational_level.name}. "
                        f"Valid divisions are: {valid_divisions_list}"
                    )
            
            # Require division and points for A-Level
            if not division:
                self.add_error('division', 'Division is required for A-Level history.')
            if total_points is None:
                self.add_error('total_points', 'Total points are required for A-Level history.')
        
        # ============================================
        # VALIDATION 10: Prevent duplicate entries
        # ============================================
        if student and school and completion_year:
            existing = StudentEducationHistory.objects.filter(
                student=student,
                school=school,
                completion_year=completion_year,
                class_completed=class_completed
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                self.add_error(
                    None,
                    f"A record for {student.full_name} at {school.name} in {completion_year} already exists."
                )
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the education history record."""
        history = super().save(commit=False)
        
        # Set the student
        history.student = self.cleaned_data.get('student')
        
        # Clean and format data
        if history.grade:
            history.grade = history.grade.upper().strip()
        
        if history.division:
            history.division = history.division.upper().strip()
        
        if commit:
            history.save()
            
            # Update student's examination number if provided and not already set
            if history.examination_number and not history.student.examination_number:
                history.student.examination_number = history.examination_number
                history.student.save(update_fields=['examination_number'])
        
        return history