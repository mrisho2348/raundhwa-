"""portal_management/forms.py"""
from django import forms
from django.contrib.auth.models import Group
from core.models import (
    AcademicYear, ClassLevel, Combination, CombinationSubject,
    Department, DivisionScale, EducationalLevel, ExamSession,
    ExamType, GradingScale, Parent, Staff, StaffDepartmentAssignment,
    StaffLeave, StaffRole, StaffRoleAssignment,
    StaffTeachingAssignment, StreamClass, Student, StudentEnrollment, StudentParent, StudentStreamAssignment,
    Subject, Term,
)
from django.db import transaction
from django.core.exceptions import ValidationError

# ── Widget helpers ────────────────────────────────────────────────────────────

class Select2Widget(forms.Select):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs.setdefault('class', 'form-select select2')


class Select2MultipleWidget(forms.SelectMultiple):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs.setdefault('class', 'form-select select2')


class DateInput(forms.DateInput):
    input_type = 'date'
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs.setdefault('class', 'form-control')


# ── Educational Level ─────────────────────────────────────────────────────────

class EducationalLevelForm(forms.ModelForm):
    class Meta:
        model = EducationalLevel
        fields = ['name', 'code', 'level_type', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'level_type': Select2Widget(),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


# ── Academic Year ─────────────────────────────────────────────────────────────

class AcademicYearForm(forms.ModelForm):
    class Meta:
        model = AcademicYear
        fields = ['name', 'start_date', 'end_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '2024/2025'}),
            'start_date': DateInput(),
            'end_date': DateInput(),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ── Term ──────────────────────────────────────────────────────────────────────

class TermForm(forms.ModelForm):
    class Meta:
        model = Term
        fields = ['academic_year', 'term_number', 'name', 'start_date', 'end_date', 'is_active']
        widgets = {
            'academic_year': Select2Widget(),
            'term_number': Select2Widget(),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'start_date': DateInput(),
            'end_date': DateInput(),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ── Department ────────────────────────────────────────────────────────────────

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'code', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


# ── Class Level ───────────────────────────────────────────────────────────────

class ClassLevelForm(forms.ModelForm):
    class Meta:
        model = ClassLevel
        fields = ['educational_level', 'name', 'code', 'order', 'is_final']
        widgets = {
            'educational_level': Select2Widget(),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_final': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


# ── Stream Class ──────────────────────────────────────────────────────────────

class StreamClassForm(forms.ModelForm):
    class Meta:
        model = StreamClass
        fields = ['class_level', 'stream_letter', 'capacity']
        widgets = {
            'class_level': Select2Widget(),
            'stream_letter': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 1}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control'}),
        }


# ── Subject ───────────────────────────────────────────────────────────────────

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['educational_level', 'name', 'short_name', 'code', 'is_compulsory', 'description']
        widgets = {
            'educational_level': Select2Widget(),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'short_name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'is_compulsory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


# ── Combination ───────────────────────────────────────────────────────────────

class CombinationForm(forms.ModelForm):
    class Meta:
        model = Combination
        fields = ['educational_level','code']
        widgets = {
            'educational_level': Select2Widget(),           
            'code': forms.TextInput(attrs={'class': 'form-control'}),
     
        }


# ── Grading Scale ─────────────────────────────────────────────────────────────

class GradingScaleForm(forms.ModelForm):
    class Meta:
        model = GradingScale
        fields = ['education_level', 'grade', 'min_mark', 'max_mark', 'points', 'description']
        widgets = {
            'education_level': Select2Widget(),
            'grade': Select2Widget(),
            'min_mark': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_mark': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'points': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }


# ── Division Scale ────────────────────────────────────────────────────────────

class DivisionScaleForm(forms.ModelForm):
    class Meta:
        model = DivisionScale
        fields = ['education_level', 'division', 'min_points', 'max_points', 'description']
        widgets = {
            'education_level': Select2Widget(),
            'division': Select2Widget(),
            'min_points': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_points': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }


# ── Exam Type ─────────────────────────────────────────────────────────────────

class ExamTypeForm(forms.ModelForm):
    class Meta:
        model = ExamType
        fields = ['name', 'code', 'weight', 'max_score', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'weight': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'max_score': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


# ── Exam Session ──────────────────────────────────────────────────────────────

class ExamSessionForm(forms.ModelForm):
    class Meta:
        model = ExamSession
        fields = ['name', 'exam_type', 'academic_year', 'term', 'class_level',
                  'stream_class', 'exam_date', 'status']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'exam_type': Select2Widget(),
            'academic_year': Select2Widget(),
            'term': Select2Widget(),
            'class_level': Select2Widget(),
            'stream_class': Select2Widget(),
            'exam_date': DateInput(),
            'status': Select2Widget(),
        }


# ── Staff ─────────────────────────────────────────────────────────────────────

class StaffForm(forms.ModelForm):
    # User account fields — only for system staff
    create_user = forms.BooleanField(
        required=False, initial=True,
        label='Create system login account',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'createUserCheck'})
    )
    username = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    user_first_name = forms.CharField(
        required=False, label='First Name',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    user_last_name = forms.CharField(
        required=False, label='Last Name',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Staff
        fields = [
            'first_name', 'last_name', 'middle_name',
            'gender', 'date_of_birth', 'phone_number', 'marital_status',
            'employment_type', 'work_place', 'joining_date',
            'profile_picture',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'middle_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': Select2Widget(),
            'date_of_birth': DateInput(),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'marital_status': Select2Widget(),
            'employment_type': Select2Widget(),
            'work_place': forms.TextInput(attrs={'class': 'form-control'}),
            'joining_date': DateInput(),
            'profile_picture': forms.FileInput(attrs={'class': 'form-control'}),
        }


class StaffRoleAssignmentForm(forms.ModelForm):
    class Meta:
        model = StaffRoleAssignment
        fields = ['staff', 'role', 'start_date', 'end_date', 'is_active', 'remarks']
        widgets = {
            'staff': Select2Widget(),
            'role': Select2Widget(),
            'start_date': DateInput(),
            'end_date': DateInput(),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class StaffRoleForm(forms.ModelForm):
    class Meta:
        model = StaffRole
        fields = ['name', 'description', 'group', 'portal_category']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'group': Select2Widget(),
            'portal_category': Select2Widget(),
        }


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

# ── Student ───────────────────────────────────────────────────────────────────



