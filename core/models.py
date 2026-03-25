from decimal import Decimal

from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, BaseUserManager, Group
from django.contrib.contenttypes.models import ContentType
from datetime import date


# ============================================================================
# USER MANAGEMENT & AUTHENTICATION
# ============================================================================

class UserType(models.IntegerChoices):
    HOD = 1, "HOD"
    STAFF = 2, "Staff"
    STUDENT = 3, "Student"


class CustomUserManager(BaseUserManager):
    """Custom user manager for handling user creation"""

    def create_user(self, username, email=None, password=None, user_type=UserType.HOD, **extra_fields):
        # Make email optional - only validate if provided
        if email is not None:
            email = self.normalize_email(email)
        else:
            email = ''  # Set empty string for users without email
        
        user = self.model(
            username=username,
            email=email,
            user_type=user_type,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('user_type', UserType.HOD)
        
        # For superusers, ensure email is provided or use a default
        if not email:
            email = f"{username}@admin.local"
        
        return self.create_user(username, email, password, **extra_fields)

class CustomUser(AbstractUser):
    """Extended user model with user type differentiation"""

    user_type = models.IntegerField(
        choices=UserType.choices,
        default=UserType.HOD
    )
    is_active = models.BooleanField(default=True)

    objects = CustomUserManager()

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['username']

    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"


class AdminHOD(models.Model):
    """Head of Department admin profile"""

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='hod_profile'
    )
    phone_number = models.CharField(max_length=15, blank=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Head of Department'
        verbose_name_plural = 'Heads of Department'

    def __str__(self):
        return f"HOD: {self.user.get_full_name()}"


# ============================================================================
# CORE CONFIGURATION MODELS
# ============================================================================

class EducationalLevel(models.Model):
    """Educational levels (Nursery, Primary, O-Level, A-Level)"""

    LEVEL_TYPE_CHOICES = [
        ('NURSERY', 'Nursery'),
        ('PRIMARY', 'Primary'),
        ('O_LEVEL', 'O-Level'),
        ('A_LEVEL', 'A-Level'),
    ]

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    level_type = models.CharField(
        max_length=10,
        choices=LEVEL_TYPE_CHOICES,
        default='PRIMARY'
    )
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = "Educational Level"
        verbose_name_plural = "Educational Levels"

    def __str__(self):
        return self.name


class AcademicYear(models.Model):
    """Academic years (e.g., 2024/2025)"""

    name = models.CharField(
        max_length=9,
        unique=True,
        help_text="Format: YYYY/YYYY (e.g., 2024/2025)"
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(
        default=False,
        help_text="Only one academic year can be active"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            if self.is_active:
                AcademicYear.objects.exclude(pk=self.pk).update(is_active=False)
            super().save(*args, **kwargs)


class Term(models.Model):
    """Academic terms within an academic year"""

    TERM_CHOICES = [
        (1, 'Term 1'),
        (2, 'Term 2'),
        (3, 'Term 3'),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='terms'
    )
    term_number = models.IntegerField(choices=TERM_CHOICES)
    name = models.CharField(max_length=20, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['academic_year', 'term_number']
        ordering = ['academic_year', 'term_number']
        verbose_name = "Term"
        verbose_name_plural = "Terms"

    def __str__(self):
        return f"{self.get_term_number_display()} - {self.academic_year}"

    def clean(self):
        if self.start_date and self.end_date:
            if self.start_date >= self.end_date:
                raise ValidationError("Start date must be before end date")

            if self.academic_year_id:
                try:
                    ay = self.academic_year
                except AcademicYear.DoesNotExist:
                    return
                if self.start_date < ay.start_date:
                    raise ValidationError("Term cannot start before academic year")
                if self.end_date > ay.end_date:
                    raise ValidationError("Term cannot end after academic year")

            # Check for overlapping terms in the same academic year
            overlapping = Term.objects.filter(
                academic_year=self.academic_year,
                start_date__lt=self.end_date,
                end_date__gt=self.start_date,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError("Term dates overlap with an existing term in this academic year.")

        # Enforce name uniqueness within the same academic year
        if self.name and self.academic_year_id:
            duplicate_name = Term.objects.filter(
                academic_year=self.academic_year,
                name=self.name,
            ).exclude(pk=self.pk)
            if duplicate_name.exists():
                raise ValidationError(
                    f"A term named '{self.name}' already exists in {self.academic_year}."
                )

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"Term {self.term_number}"
        self.full_clean()
        with transaction.atomic():
            if self.is_active:
                Term.objects.filter(
                    academic_year=self.academic_year
                ).exclude(pk=self.pk).update(is_active=False)
            super().save(*args, **kwargs)


class Department(models.Model):
    """Academic departments"""

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Department"
        verbose_name_plural = "Departments"

    def __str__(self):
        return self.name


# ============================================================================
# ACADEMIC STRUCTURE MODELS
# ============================================================================

class ClassLevel(models.Model):
    """Class levels within educational levels"""

    educational_level = models.ForeignKey(
        EducationalLevel,
        on_delete=models.CASCADE,
        related_name='class_levels'
    )
    name = models.CharField(max_length=50)    # e.g., "Form 1", "Std 3"
    code = models.CharField(max_length=20)    # e.g., "F1", "STD3"
    order = models.PositiveIntegerField(help_text="For proper ordering")
    is_final = models.BooleanField(
        default=False,
        help_text=(
            "Mark this as the final class level in this educational level. "
            "Only one class level per educational level can be final. "
            "Used to determine completion vs promotion and to identify "
            "terminal examination classes (PSLE, NECTA O-Level, NECTA A-Level)."
        )
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['educational_level', 'order']
        unique_together = ['educational_level', 'code']
        verbose_name = 'Class Level'
        verbose_name_plural = 'Class Levels'

    def clean(self):
        # Enforce only one final class level per educational level
        if self.is_final and self.educational_level_id:
            conflict = ClassLevel.objects.filter(
                educational_level=self.educational_level,
                is_final=True
            ).exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError(
                    f"'{self.educational_level}' already has a final class level "
                    f"({conflict.first()}). Only one class level per educational "
                    f"level can be marked as final."
                )

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self.name.upper().replace(' ', '')[:20]
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.educational_level.code})"


class StreamClass(models.Model):
    """Class streams (e.g., Form 1A, Form 2B)"""

    class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.CASCADE,
        related_name='streams'
    )
    stream_letter = models.CharField(
        max_length=1,
        help_text="A, B, C, etc."
    )
    name = models.CharField(max_length=10, blank=True)
    capacity = models.PositiveIntegerField(default=50)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['class_level', 'stream_letter']
        ordering = ['class_level', 'stream_letter']
        verbose_name = "Stream Class"
        verbose_name_plural = "Stream Classes"

    def __str__(self):
        return f"{self.class_level.name}{self.stream_letter}"

    def save(self, *args, **kwargs):
        if not self.name:
            self.name = f"{self.class_level.name}{self.stream_letter}"
        super().save(*args, **kwargs)

    @property
    def student_count(self):
        """Count active students in this stream."""
        return self.stream_assignments.filter(
            enrollment__status='active',
            enrollment__academic_year__is_active=True
        ).count()
    

class Subject(models.Model):
    """Academic subjects"""

    educational_level = models.ForeignKey(
        EducationalLevel,
        on_delete=models.CASCADE,
        related_name='subjects'
    )
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=20, blank=True)
    code = models.CharField(max_length=20)
    is_compulsory = models.BooleanField(default=False)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['educational_level', 'code']
        ordering = ['educational_level', 'name']
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Combination(models.Model):
    """Subject combinations for A-Level"""

    educational_level = models.ForeignKey(
        EducationalLevel,
        on_delete=models.CASCADE,
        limit_choices_to={'level_type': 'A_LEVEL'},
        related_name='combinations'
    )
    code = models.CharField(max_length=10, unique=True)   # e.g., "PCM" 

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = "Subject Combination"
        verbose_name_plural = "Subject Combinations"

    def __str__(self):
        return self.code


class CombinationSubject(models.Model):
    """Subjects within a combination with their roles"""

    SUBJECT_ROLE_CHOICES = [
        ('CORE', 'Core Subject'),
        ('SUBSIDIARY', 'Subsidiary Subject'),
    ]

    combination = models.ForeignKey(
        Combination,
        on_delete=models.CASCADE,
        related_name='combination_subjects'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='combination_subjects'
    )
    role = models.CharField(max_length=10, choices=SUBJECT_ROLE_CHOICES)

    class Meta:
        unique_together = ['combination', 'subject']
        verbose_name = "Combination Subject"
        verbose_name_plural = "Combination Subjects"

    def clean(self):
        if self.subject_id and self.combination_id:
            # Subject must belong to the same educational level as the combination.
            # Both Combination and Subject carry educational_level independently —
            # this validation ensures they always agree, preventing e.g. an
            # O-Level subject being added to an A-Level combination.
            if self.subject.educational_level != self.combination.educational_level:
                raise ValidationError(
                    f"Subject '{self.subject}' belongs to "
                    f"'{self.subject.educational_level}' but combination "
                    f"'{self.combination}' belongs to "
                    f"'{self.combination.educational_level}'. "
                    f"All subjects in a combination must belong to the "
                    f"same educational level as the combination."
                )

            # A subject already marked as compulsory at its level should not
            # be added as a subsidiary — compulsory subjects are taken by all
            # students regardless of combination, so assigning them to a
            # specific combination role is misleading.
            if self.role == 'SUBSIDIARY' and self.subject.is_compulsory:
                raise ValidationError(
                    f"'{self.subject}' is a compulsory subject and cannot be "
                    f"assigned as a Subsidiary in a combination. "
                    f"Compulsory subjects are taken by all students at this level."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.combination.code} - {self.subject.code} ({self.role})"


class StudentCombinationAssignment(models.Model):
    """
    Tracks combination assignments for A-Level students over their enrollment.

    This is the SINGLE source of truth for a student's combination.
    StudentEnrollment deliberately does NOT store a combination FK — it exposes
    a `current_combination` property that queries this table on demand, so
    there is no synchronisation required and no risk of the two getting out of step.

    Setting `is_active=True` on a new assignment automatically deactivates the
    previous active assignment for the same enrollment inside a single atomic
    transaction, so the UniqueConstraint on (enrollment, is_active=True) is
    always satisfied and the history of prior combinations is preserved.
    """
    
    student = models.ForeignKey(
        'Student',
        on_delete=models.CASCADE,
        related_name='combination_assignments',
        help_text="The A-Level student assigned to this combination"
    )
    enrollment = models.ForeignKey(
        'StudentEnrollment',
        on_delete=models.CASCADE,
        related_name='combination_assignments',
        help_text="The enrollment this combination assignment belongs to",
        limit_choices_to={'class_level__educational_level__level_type': 'A_LEVEL'}
    )
    combination = models.ForeignKey(
        Combination,
        on_delete=models.PROTECT,  # PROTECT prevents deletion if assignments exist
        related_name='student_assignments',
        help_text="The combination assigned to the student"
    )
    assigned_date = models.DateField(
        default=timezone.now,
        help_text="Date when this combination was assigned"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this is the current active combination assignment"
    )
    remarks = models.TextField(
        blank=True,
        help_text="Any notes about this assignment (reason for change, etc.)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Combination Assignment"
        verbose_name_plural = "Student Combination Assignments"
        ordering = ['-assigned_date', 'student']
        indexes = [
            models.Index(fields=['student', '-assigned_date']),
            models.Index(fields=['combination', 'is_active']),
            models.Index(fields=['enrollment', 'is_active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['enrollment', 'is_active'],
                condition=models.Q(is_active=True),
                name='unique_active_combination_per_enrollment'
            )
        ]

    def clean(self):
        """Validate the combination assignment."""
        if not self.student_id or not self.enrollment_id:
            return

        # Ensure student matches the enrollment
        if self.enrollment.student_id != self.student_id:
            raise ValidationError(
                "The student does not match the student on the enrollment record."
            )

        # Only applicable to A-Level students
        if self.enrollment.class_level.educational_level.level_type != 'A_LEVEL':
            raise ValidationError(
                "Combination assignments are only applicable to A-Level students."
            )

        # Ensure combination belongs to the same educational level as the enrollment
        if self.combination.educational_level != self.enrollment.class_level.educational_level:
            raise ValidationError(
                f"Combination '{self.combination.code}' is for "
                f"'{self.combination.educational_level.name}' but the student is enrolled in "
                f"'{self.enrollment.class_level.educational_level.name}'. "
                f"The combination must match the student's educational level."
            )

        # NOTE: we do NOT raise an error here if another active assignment already
        # exists for this enrollment.  The save() method deactivates the previous
        # active record atomically before inserting this one, so the constraint
        # is maintained at the database level.  A hard ValidationError here would
        # prevent legitimate combination changes (e.g., correcting a wrong assignment).

    def save(self, *args, **kwargs):
        """
        Save the combination assignment.

        When a new record is saved as active, any previously active assignment
        for the same enrollment is deactivated atomically inside the same
        transaction — ensuring the UniqueConstraint on (enrollment, is_active=True)
        is never violated and there is no window where two records are both active.

        There is intentionally NO write back to StudentEnrollment here.
        StudentEnrollment.current_combination is a @property that reads the
        assignment table on demand, so it is always correct without any sync.
        """
        self.full_clean()

        with transaction.atomic():
            if self.is_active:
                # Deactivate any other active assignment for this enrollment
                # BEFORE inserting/updating so the DB UniqueConstraint is not
                # violated even briefly.
                StudentCombinationAssignment.objects.filter(
                    enrollment=self.enrollment,
                    is_active=True,
                ).exclude(pk=self.pk).update(is_active=False)

            super().save(*args, **kwargs)

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"{self.student.full_name} - {self.combination.code} ({self.assigned_date}) [{status}]"


# ============================================================================
# STAFF MANAGEMENT MODELS
# ============================================================================

class Staff(models.Model):
    """Staff personal information"""

    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]

    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'),
        ('married', 'Married'),
        ('divorced', 'Divorced'),
        ('widowed', 'Widowed'),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ('permanent', 'Permanent'),
        ('contract', 'Contract'),
        ('part_time', 'Part Time'),
        ('temporary', 'Temporary'),
    ]

    # User account link — optional for non-system staff (cook, driver
    # with no system role, cleaner etc.) who are recorded for HR/payroll
    # purposes but do not need a system login. System-facing staff
    # (teachers, secretary, headmaster etc.) must have a user account.
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_profile'
    )

    # Personal Information
    # first_name and last_name are stored directly on Staff so that
    # non-system staff (no user account) still have a proper name.
    # For system staff these mirror user.first_name / user.last_name —
    # kept in sync via clean() below.
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    middle_name = models.CharField(max_length=100, blank=True)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Staff member's date of birth"
    )
    phone_number = models.CharField(max_length=15, blank=True)
    marital_status = models.CharField(
        max_length=20,
        choices=MARITAL_STATUS_CHOICES,
        blank=True
    )

    # Employment Information
    employee_id = models.CharField(max_length=50, unique=True, blank=True)
    employment_type = models.CharField(
        max_length=20,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default='permanent'
    )
    work_place = models.CharField(max_length=100, blank=True)
    joining_date = models.DateField(blank=True, null=True)

    # Media
    profile_picture = models.ImageField(
        upload_to='staff/profile_pictures/',
        blank=True,
        null=True
    )
    signature = models.ImageField(
        upload_to='staff/signatures/',
        blank=True,
        null=True,
        help_text="Upload digital signature"
    )

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Staff'
        verbose_name_plural = 'Staff'
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return self.get_full_name()

    def get_full_name(self):
        # For system staff, pull first/last name from the linked user account.
        # For non-system staff (no user account), fall back to stored name fields.
        if self.user_id:
            parts = [
                self.user.first_name,
                self.middle_name,
                self.user.last_name,
            ]
        else:
            parts = [
                self.first_name,
                self.middle_name,
                self.last_name,
            ]
        return ' '.join(filter(None, parts)).strip()

    def clean(self):
        if self.joining_date and self.joining_date > timezone.now().date():
            raise ValidationError("Joining date cannot be in the future.")
        if self.date_of_birth and self.date_of_birth > timezone.now().date():
            raise ValidationError("Date of birth cannot be in the future.")

        # For system staff, keep first/last name in sync with the user account
        # so both sources always agree and get_full_name() is consistent.
        if self.user_id:
            if self.user.first_name:
                self.first_name = self.user.first_name
            if self.user.last_name:
                self.last_name = self.user.last_name

        # Require at least a first name for non-system staff so the record
        # is not completely anonymous.
        if not self.user_id and not self.first_name and not self.last_name:
            raise ValidationError(
                "Non-system staff (without a user account) must have at "
                "least a first name or last name recorded."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.employee_id:
            year = timezone.now().year
            with transaction.atomic():
                last_staff = (
                    Staff.objects
                    .select_for_update()
                    .filter(employee_id__startswith=f"STAFF/{year}")
                    .order_by('-employee_id')
                    .first()
                )
                if last_staff:
                    last_number = int(last_staff.employee_id.split('/')[-1])
                    new_number = last_number + 1
                else:
                    new_number = 1
                self.employee_id = f"STAFF/{year}/{new_number:04d}"
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)


class StaffRole(models.Model):
    """
    Staff roles (positions) — stored as free-text for flexibility.

    Each role links to a Django auth Group which controls what the
    staff member can do in the system. When a StaffRoleAssignment is
    saved, the staff member's user account is automatically added to
    or removed from this group.

    portal_category determines which UI portal the role belongs to.
    Multiple roles can share the same portal — e.g. Headmaster and
    Deputy Headmaster both use the Management portal but have different
    permission groups with different levels of access within it.

    Use 'none' for support staff who are recorded in the system for
    HR/payroll purposes but do not need any system interface (cook,
    cleaner, watchman etc.).
    """

    PORTAL_CHOICES = [
        # Core school portals
        ('management',      'Management Portal'),       # Headmaster, Deputy
        ('academic',        'Academic Portal'),          # Teachers, Class Teachers
        ('administration',  'Administration Portal'),    # Secretary, Administrator
        ('finance',         'Finance Portal'),           # Accountant

        # Support portals — each has its own independent interface
        ('transport',       'Transport Portal'),         # Driver
        ('library',         'Library Portal'),           # Librarian
        ('health',          'Health Portal'),            # Nurse, Matron

        # No portal — HR/payroll only, no system login needed
        ('none',            'No Portal Access'),         # Cook, Cleaner, Watchman
    ]

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    group = models.OneToOneField(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_role',
        help_text=(
            "The Django permission group that grants this role's system "
            "access. When a staff member is assigned this role they are "
            "automatically added to this group, and removed when the "
            "assignment is deactivated."
        )
    )
    portal_category = models.CharField(
        max_length=20,
        choices=PORTAL_CHOICES,
        blank=True,
        help_text=(
            "Which UI portal this role belongs to. Controls where the "
            "staff member is redirected after login. Multiple roles can "
            "share the same portal."
        )
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Staff Role"
        verbose_name_plural = "Staff Roles"

    def __str__(self):
        return self.name


class StaffRoleAssignment(models.Model):
    """Assignment of roles to staff members"""

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='role_assignments'
    )
    role = models.ForeignKey(
        StaffRole,
        on_delete=models.CASCADE,
        related_name='staff_assignments'
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['staff', 'role', 'start_date']
        ordering = ['-start_date']
        verbose_name = "Staff Role Assignment"
        verbose_name_plural = "Staff Role Assignments"

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date.")
        # Enforce only one active assignment per role per staff member
        if self.is_active:
            conflict = StaffRoleAssignment.objects.filter(
                staff=self.staff,
                role=self.role,
                is_active=True
            ).exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError(
                    f"{self.staff} already has an active assignment for role '{self.role}'."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            super().save(*args, **kwargs)
            # Auto-sync the staff member's user account to the Django
            # permission group linked to this role.
            #
            # Skip entirely when:
            #   - The role has no linked group (group not yet configured)
            #   - The staff member has no user account (non-system staff)
            #   - The role's portal_category is 'none' (HR-only roles like
            #     cook, cleaner — they have no system access by design)
            if (
                self.role.group_id
                and self.staff.user_id
                and self.role.portal_category != 'none'
            ):
                user = self.staff.user
                if self.is_active:
                    user.groups.add(self.role.group)
                else:
                    # Only remove the group if no other active assignment
                    # for the same role still exists — protects against
                    # accidentally revoking a group that another active
                    # assignment still requires.
                    still_active = StaffRoleAssignment.objects.filter(
                        staff=self.staff,
                        role=self.role,
                        is_active=True,
                    ).exclude(pk=self.pk).exists()
                    if not still_active:
                        user.groups.remove(self.role.group)

    def __str__(self):
        return f"{self.staff} - {self.role}"


class StaffDepartmentAssignment(models.Model):
    """Assignment of staff to departments"""

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='department_assignments'
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='staff_assignments'
    )
    is_head = models.BooleanField(default=False)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['staff', 'department', 'start_date']
        ordering = ['-start_date']
        verbose_name = "Staff Department Assignment"
        verbose_name_plural = "Staff Department Assignments"

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date.")
        if self.is_active:
            conflict = StaffDepartmentAssignment.objects.filter(
                staff=self.staff,
                department=self.department,
                is_active=True
            ).exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError(
                    f"{self.staff} already has an active assignment in department '{self.department}'."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.staff} -> {self.department.name}"


class StaffTeachingAssignment(models.Model):
    """Teaching assignments for staff"""

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='teaching_assignments'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='teaching_assignments'
    )
    class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.CASCADE,
        related_name='teaching_assignments'
    )
    stream_class = models.ForeignKey(
        StreamClass,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='teaching_assignments'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='teaching_assignments'
    )
    periods_per_week = models.PositiveIntegerField(default=0)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # stream_class can be NULL so uniqueness is enforced via clean() below
        ordering = ['academic_year', 'class_level', 'subject']
        verbose_name = "Staff Teaching Assignment"
        verbose_name_plural = "Staff Teaching Assignments"

    def clean(self):
        # Validate stream belongs to the assigned class level
        if self.stream_class_id and self.class_level_id:
            if self.stream_class.class_level_id != self.class_level_id:
                raise ValidationError(
                    f"Stream '{self.stream_class}' belongs to "
                    f"'{self.stream_class.class_level}', not '{self.class_level}'. "
                    f"The stream must belong to the assigned class level."
                )

        # Validate subject belongs to the same educational level as the class level
        if self.subject_id and self.class_level_id:
            if self.subject.educational_level != self.class_level.educational_level:
                raise ValidationError(
                    f"Subject '{self.subject}' belongs to "
                    f"'{self.subject.educational_level}' but class level "
                    f"'{self.class_level}' belongs to "
                    f"'{self.class_level.educational_level}'. "
                    f"Subject and class level must share the same educational level."
                )

        # Enforce uniqueness manually — stream_class is nullable and
        # NULL != NULL in most DB unique constraints
        qs = StaffTeachingAssignment.objects.filter(
            staff=self.staff,
            subject=self.subject,
            class_level=self.class_level,
            stream_class=self.stream_class,
            academic_year=self.academic_year,
        ).exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                "A teaching assignment already exists for this staff/subject/class/stream/year combination."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.stream_class:
            return f"{self.staff} -> {self.subject} ({self.class_level} - {self.stream_class})"
        return f"{self.staff} -> {self.subject} ({self.class_level})"


class ClassTeacherAssignment(models.Model):
    """Class teacher assignments"""

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments'
    )
    class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments'
    )
    stream_class = models.ForeignKey(
        StreamClass,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='class_teacher_assignments'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='class_teacher_assignments'
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-academic_year', 'class_level']
        verbose_name = "Class Teacher Assignment"
        verbose_name_plural = "Class Teacher Assignments"

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date.")

        # Enforce uniqueness accounting for nullable stream_class
        qs = ClassTeacherAssignment.objects.filter(
            class_level=self.class_level,
            stream_class=self.stream_class,
            academic_year=self.academic_year,
        ).exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                "A class teacher is already assigned to this class/stream/year combination."
            )

        # Prevent one staff from being class teacher of two classes in the same year
        if self.is_active:
            conflict = ClassTeacherAssignment.objects.filter(
                staff=self.staff,
                academic_year=self.academic_year,
                is_active=True,
            ).exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError(
                    f"{self.staff} is already an active class teacher for another class in {self.academic_year}."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.stream_class:
            return f"{self.staff} -> Class Teacher ({self.class_level} - {self.stream_class})"
        return f"{self.staff} -> Class Teacher ({self.class_level})"


# ============================================================================
# STUDENT MANAGEMENT MODELS
# ============================================================================

# School code is configurable here rather than hardcoded deep in Student.save()
SCHOOL_CODE = "S2348"


class Student(models.Model):
    """Student personal information"""

    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]

    STATUS_CHOICES = [
        # Current standing at the school
        ('active',      'Active'),       # currently enrolled and attending
        ('suspended',   'Suspended'),    # temporarily barred — set by StudentSuspension
        ('withdrawn',   'Withdrawn'),    # dropped out — set by StudentWithdrawal
        ('completed',   'Completed'),    # finished final class level of their educational level
        ('transferred', 'Transferred'),  # left to another school — set by StudentTransferOut
    ]

    # Personal Information
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    # Contact & Identification
    address = models.CharField(max_length=200, blank=True)
    physical_disability = models.CharField(max_length=200, blank=True)
    national_id = models.CharField(max_length=30, blank=True, null=True)

    # School Identification
    registration_number = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True
    )
    examination_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="NECTA examination number"
    )

    # Admission Information
    admission_date = models.DateField(default=timezone.now)
    serial_number = models.PositiveIntegerField(blank=True, null=True, editable=False)

    # Media
    profile_picture = models.ImageField(
        upload_to='students/profile_pictures/',
        null=True,
        blank=True
    )

    # Portal access — auto-created when registration_number is generated.
    # Username = registration_number, default password = registration_number.
    # Student must change password on first login.
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_profile',
        help_text=(
            "Auto-created on first save. Username and default password "
            "are both set to the student's registration number."
        )
    )
    must_change_password = models.BooleanField(
        default=True,
        help_text=(
            "True until the student changes their default password. "
            "Portal views check this flag and redirect to the "
            "change-password page if it is still True."
        )
    )

    # Status — single source of truth; is_active derived from status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['registration_number']
        verbose_name = "Student"
        verbose_name_plural = "Students"

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return ' '.join(filter(None, parts)).strip()

    @property
    def is_active(self):
        """Derived from status to avoid dual-field inconsistency."""
        return self.status == 'active'

    @property
    def age(self):
        if self.date_of_birth:
            today = timezone.now().date()
            age = today.year - self.date_of_birth.year
            if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
                age -= 1
            return age
        return None

    def clean(self):
        if self.date_of_birth:
            today = timezone.now().date()
            if self.date_of_birth > today:
                raise ValidationError("Date of birth cannot be in the future.")
            # Reasonable minimum age guard (e.g., 3 years for nursery)
            if (today.year - self.date_of_birth.year) > 100:
                raise ValidationError("Date of birth appears invalid (over 100 years ago).")

    def save(self, *args, **kwargs):
        self.full_clean()
        admission_year = self.admission_date.year if self.admission_date else timezone.now().year

        with transaction.atomic():
            if not self.serial_number:
                last_student = (
                    Student.objects
                    .select_for_update()
                    .filter(admission_date__year=admission_year)
                    .order_by('-serial_number')
                    .first()
                )
                self.serial_number = (last_student.serial_number + 1) if last_student else 1

            if not self.registration_number:
                serial = str(self.serial_number).zfill(4)
                self.registration_number = f"{SCHOOL_CODE}/{serial}/{admission_year}"

            # Save the student first
            super().save(*args, **kwargs)

            # Auto-create a CustomUser account for portal access
            if not self.user_id and self.registration_number:
                try:
                    # Create a placeholder email using registration number
                    # This ensures uniqueness and satisfies any email requirements
                    placeholder_email = f"{self.registration_number.replace('/', '_')}@student.local"
                    
                    user = CustomUser.objects.create_user(
                        username=self.registration_number,
                        email=placeholder_email,  # Now using a proper email format
                        password=self.registration_number,
                        user_type=UserType.STUDENT,
                        first_name=self.first_name,
                        last_name=self.last_name,
                    )
                    
                    # Update the student with the user reference
                    # Use a separate update to avoid recursion
                    Student.objects.filter(pk=self.pk).update(user=user)
                    self.user = user
                    
                except Exception as e:
                    # Log the error but don't rollback the student creation
                    # The student record exists but without a user account
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to create user account for student {self.registration_number}: {str(e)}")
                    
                    # You might want to create a system notification here
                    # For now, we'll just log it and continue
                    pass


class StudentEnrollment(models.Model):
    """Student enrollment in classes per academic year"""

    STATUS_CHOICES = [
        # Outcome of this specific academic year enrollment
        ('active',      'Active'),       # year still in progress
        ('promoted',    'Promoted'),     # moved to next class level
        ('repeated',    'Repeated'),     # repeated the same class level
        ('completed',   'Completed'),    # finished final class level of the educational level
        ('transferred', 'Transferred'),  # left to another school mid-year
        ('withdrawn',   'Withdrawn'),    # dropped out mid-year
        ('suspended',   'Suspended'),    # suspended, enrollment on hold
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='student_enrollments'
    )
    class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.CASCADE,
        related_name='student_enrollments'
    )
    # NOTE: combination is intentionally NOT stored as a database FK here.
    # The student's current combination is the single active record in
    # StudentCombinationAssignment for this enrollment.  Access it via the
    # `current_combination` property below.  Storing it here as well was the
    # original design but created a dual-source-of-truth problem that required
    # three separate sync paths (save(), signal, update()) which could diverge.
    enrollment_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'academic_year']
        ordering = ['-academic_year', 'class_level']
        verbose_name = "Student Enrollment"
        verbose_name_plural = "Student Enrollments"

    def clean(self):
        # ----------------------------------------------------------------
        # NOTE: combination validation is now handled entirely in
        # StudentCombinationAssignment.clean().  There is no combination FK
        # on this model — see `current_combination` property.
        # ----------------------------------------------------------------

        # Ensure class_level belongs to the academic year being enrolled into —
        # prevent enrolling a student in Form 2 against a 2019/2020 academic year
        # while the current year is 2024/2025
        if self.academic_year_id and not self.academic_year.is_active:
            raise ValidationError(
                f"Cannot enroll a student into '{self.academic_year}' because "
                f"it is not the active academic year. "
                f"Enrollments can only be created for the currently active academic year."
            )

        # ----------------------------------------------------------------
        # Promotion rules:
        #
        # 1. A student at a final class level should be marked 'completed',
        #    not 'promoted' — there is nowhere left to be promoted to within
        #    that educational level.
        #
        # 2. A student can only be promoted within the same educational level.
        #    Moving to the next educational level (Primary → O-Level,
        #    O-Level → A-Level) requires a fresh enrollment as a new student
        #    at that level — not a promotion of the existing enrollment.
        #
        # 3. Promotion must always move forward — never sideways or backward.
        # ----------------------------------------------------------------
        if self.student_id and self.class_level_id and self.status == 'promoted':

            # Rule 1 — block promotion out of a final class level
            if self.class_level.is_final:
                raise ValidationError(
                    f"'{self.class_level}' is the final class level of "
                    f"'{self.class_level.educational_level}'. "
                    f"Students at this level should be marked 'completed', not 'promoted'."
                )

            # Find the student's most recent previous enrollment
            previous_enrollment = (
                StudentEnrollment.objects
                .filter(student_id=self.student_id)
                .exclude(pk=self.pk)
                .select_related('class_level__educational_level')
                .order_by('-academic_year__start_date')
                .first()
            )

            if previous_enrollment:
                previous_level = previous_enrollment.class_level.educational_level
                current_level = self.class_level.educational_level

                # Rule 2 — block cross-educational-level promotion
                if previous_level != current_level:
                    raise ValidationError(
                        f"A student cannot be promoted across educational levels. "
                        f"'{self.student}' is being moved from '{previous_level}' "
                        f"to '{current_level}'. "
                        f"To enroll this student at {current_level}, register them "
                        f"as a new student at that level."
                    )

                # Rule 3 — block backward or sideways promotion using order
                if self.class_level.order <= previous_enrollment.class_level.order:
                    raise ValidationError(
                        f"Promotion must move the student forward. "
                        f"'{previous_enrollment.class_level}' → '{self.class_level}' "
                        f"is not a valid promotion within '{current_level}'."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.full_name} -> {self.class_level} ({self.academic_year})"

    # ----------------------------------------------------------------
    # Single source of truth for the student's combination.
    # Always reads from the assignment table — no sync needed.
    # ----------------------------------------------------------------
    @property
    def current_combination(self):
        """
        Returns the currently active Combination for this enrollment,
        or None if not yet assigned (non-A-Level or not yet set).

        This is the ONLY place the combination is read from. There is no
        combination FK on this model — StudentCombinationAssignment is the
        sole source of truth.
        """
        assignment = self.combination_assignments.filter(is_active=True).first()
        return assignment.combination if assignment else None


class StudentStreamAssignment(models.Model):
    """
    Assigns an enrolled student to a specific stream within their class level.

    Stream assignment is a separate administrative step that happens after
    enrollment. A student must be enrolled before they can be streamed.
    Only one active stream assignment per student per academic year is allowed.
    Capacity of the target stream is strictly enforced.
    """

    enrollment = models.OneToOneField(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name='stream_assignment',
        help_text="The enrollment this stream assignment belongs to"
    )
    stream_class = models.ForeignKey(
        StreamClass,
        on_delete=models.PROTECT,
        related_name='stream_assignments',
        help_text="The stream the student is assigned to"
    )
    assigned_date = models.DateField(
        default=timezone.now,
        help_text="Date the student was assigned to this stream"
    )
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Stream Assignment"
        verbose_name_plural = "Student Stream Assignments"

    def clean(self):
        if not self.enrollment_id or not self.stream_class_id:
            return

        enrollment = self.enrollment
        stream = self.stream_class

        # Stream must belong to the same class level as the enrollment
        if stream.class_level != enrollment.class_level:
            raise ValidationError(
                f"Stream '{stream}' belongs to '{stream.class_level}' but the "
                f"student is enrolled in '{enrollment.class_level}'. "
                f"A student can only be assigned to a stream within their enrolled class level."
            )

        # Strictly enforce stream capacity
        current_count = StudentStreamAssignment.objects.filter(
            stream_class=stream,
            enrollment__academic_year=enrollment.academic_year,
        ).exclude(pk=self.pk).count()

        if current_count >= stream.capacity:
            raise ValidationError(
                f"Stream '{stream}' has reached its maximum capacity of "
                f"{stream.capacity} students for {enrollment.academic_year}. "
                f"Please assign the student to a different stream or increase "
                f"the capacity of this stream."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.enrollment.student.full_name} -> "
            f"{self.stream_class} ({self.enrollment.academic_year})"
        )


class Parent(models.Model):
    """Parent/Guardian information"""

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

    full_name = models.CharField(max_length=255)
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES)
    address = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, unique=True)
    alternate_phone = models.CharField(max_length=20, blank=True, null=True)
    students = models.ManyToManyField(
        Student,
        related_name='parents',
        through='StudentParent'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parent"
        verbose_name_plural = "Parents"
        ordering = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.get_relationship_display()})"


class StudentParent(models.Model):
    """Junction model for Student-Parent relationship"""

    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    parent = models.ForeignKey(Parent, on_delete=models.CASCADE)
    is_primary_contact = models.BooleanField(default=False)
    is_fee_responsible = models.BooleanField(
        default=False,
        help_text="Primary fee payer for this specific student"
    )
    fee_responsible_from = models.DateField(
        null=True,
        blank=True,
        help_text="Date from which this parent became the fee responsible party."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'parent']
        verbose_name = "Student Parent Relationship"
        verbose_name_plural = "Student Parent Relationships"


class StudentSubjectAssignment(models.Model):
    """
    Elective/optional subject assignments for O-Level students.

    In Tanzania's O-Level curriculum, students take a set of compulsory
    subjects plus a number of elective (non-compulsory) subjects chosen
    for them. This model records those elective subject assignments.
    """

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='subject_assignments'
    )
    enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name='subject_assignments',
        help_text="The O-Level enrollment this assignment belongs to"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='student_assignments'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['enrollment', 'subject']
        verbose_name = "Student Subject Assignment"
        verbose_name_plural = "Student Subject Assignments"

    def clean(self):
        # Ensure student matches the enrollment
        if self.enrollment_id and self.student_id:
            if self.enrollment.student_id != self.student_id:
                raise ValidationError(
                    "The student does not match the student on the enrollment record."
                )

        # Only applicable to O-Level students
        if self.enrollment_id:
            level_type = self.enrollment.class_level.educational_level.level_type
            if level_type != 'O_LEVEL':
                raise ValidationError(
                    "Elective subject assignments are only applicable to O-Level students."
                )

        # Only non-compulsory (elective) subjects may be assigned here
        if self.subject_id and self.subject.is_compulsory:
            raise ValidationError(
                f"'{self.subject}' is a compulsory subject and cannot be assigned as an elective. "
                "Compulsory subjects are implied by the student's enrollment."
            )

        # Subject must belong to the same educational level as the enrollment
        if self.subject_id and self.enrollment_id:
            enrollment_level = self.enrollment.class_level.educational_level
            if self.subject.educational_level != enrollment_level:
                raise ValidationError(
                    f"Subject '{self.subject}' does not belong to the student's "
                    f"educational level ({enrollment_level})."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.full_name} - {self.subject.name} ({self.enrollment.academic_year})"


# ============================================================================
# EXAMINATION & GRADING MODELS
# ============================================================================

class ExamType(models.Model):
    """Types of examinations"""

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Contribution (%) to final score"
    )
    max_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[MinValueValidator(1)]
    )
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Exam Type'
        verbose_name_plural = 'Exam Types'

    def __str__(self):
        return f"{self.name} ({self.code})"


class ExamSession(models.Model):
    """Examination sessions"""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('verified', 'Verified'),
        ('published', 'Published'),
    ]

    name = models.CharField(max_length=200)
    exam_type = models.ForeignKey(
        ExamType,
        on_delete=models.CASCADE,
        related_name='exam_sessions'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='exam_sessions'
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name='exam_sessions'
    )
    class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.CASCADE,
        related_name='exam_sessions'
    )
    stream_class = models.ForeignKey(
        StreamClass,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,   # was CASCADE — deleting a stream should not delete sessions
        related_name='exam_sessions'
    )
    exam_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-exam_date']
        verbose_name = 'Exam Session'
        verbose_name_plural = 'Exam Sessions'

    def clean(self):
        # Ensure the term belongs to the academic year
        if self.term_id and self.academic_year_id:
            if self.term.academic_year_id != self.academic_year_id:
                raise ValidationError(
                    "The selected term does not belong to the selected academic year."
                )

        # Ensure a grading scale exists for this class level's educational level
        # before allowing an exam session to be created — without it result
        # computation will fail at runtime with no clear error
        if self.class_level_id:
            ed_level = self.class_level.educational_level
            if not GradingScale.objects.filter(education_level=ed_level).exists():
                raise ValidationError(
                    f"No grading scale has been configured for '{ed_level}'. "
                    f"Please set up a grading scale for '{ed_level}' before "
                    f"creating exam sessions for this level."
                )

    def save(self, *args, **kwargs):
        # Auto-generate name from related fields if not explicitly provided.
        # e.g. "Midterm Exam — Form 2 — Term 1 — 2024/2025"
        if not self.name and self.exam_type_id and self.class_level_id \
                and self.term_id and self.academic_year_id:
            stream_part = f" {self.stream_class}" if self.stream_class_id else ""
            self.name = (
                f"{self.exam_type} — "
                f"{self.class_level}{stream_part} — "
                f"{self.term} — "
                f"{self.academic_year}"
            )
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} - {self.class_level} ({self.term})"


class SubjectExamPaper(models.Model):
    """Individual exam papers for subjects"""

    exam_session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name='exam_papers'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='exam_papers'
    )
    paper_number = models.PositiveIntegerField(help_text="Paper number (1, 2, 3...)")
    paper_name = models.CharField(max_length=100, blank=True)
    max_marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100,
        validators=[MinValueValidator(1)]
    )
    exam_date = models.DateField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['exam_session', 'subject', 'paper_number']
        ordering = ['exam_session', 'subject', 'paper_number']
        verbose_name = "Subject Exam Paper"
        verbose_name_plural = "Subject Exam Papers"

    def __str__(self):
        return f"{self.subject} Paper {self.paper_number} - {self.exam_session}"

    def clean(self):
        if self.subject_id and self.exam_session_id:
            session_level = self.exam_session.class_level.educational_level
            if self.subject.educational_level != session_level:
                raise ValidationError(
                    f"Subject '{self.subject}' belongs to '{self.subject.educational_level}' "
                    f"but this exam session is for '{session_level}'. "
                    f"A subject must belong to the same educational level as the exam session."
                )

    def save(self, *args, **kwargs):
        if not self.paper_name:
            self.paper_name = f"Paper {self.paper_number}"
        self.full_clean()
        super().save(*args, **kwargs)


class GradingScale(models.Model):
    """Grading scales based on educational level"""

    GRADE_CHOICES = [
        ('A', 'A - Excellent'),
        ('B', 'B - Very Good'),
        ('C', 'C - Good'),
        ('D', 'D - Satisfactory'),
        ('E', 'E - Fair'),
        ('F', 'F - Fail'),
        ('S', 'S - Subsidiary'),
    ]

    education_level = models.ForeignKey(
        EducationalLevel,
        on_delete=models.CASCADE,
        related_name='grading_scales'
    )
    grade = models.CharField(max_length=1, choices=GRADE_CHOICES)
    min_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    max_mark = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    points = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        default=0,
        help_text="Grade points (0 for primary)"
    )
    description = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['education_level', '-min_mark']
        unique_together = ['education_level', 'grade']
        verbose_name = 'Grading Scale'
        verbose_name_plural = 'Grading Scales'

    def clean(self):
        if self.min_mark is not None and self.max_mark is not None:
            if self.min_mark > self.max_mark:
                raise ValidationError("Minimum mark cannot exceed maximum mark")
            if self.min_mark < 0 or self.max_mark > 100:
                raise ValidationError("Marks must be between 0 and 100")

            # Check for overlapping ranges for the same education level
            overlapping = GradingScale.objects.filter(
                education_level=self.education_level,
                min_mark__lt=self.max_mark,
                max_mark__gt=self.min_mark,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    f"Mark range {self.min_mark}–{self.max_mark} overlaps with an existing grade band."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.education_level.name} | {self.grade} ({self.min_mark}-{self.max_mark}) Points: {self.points}"


class DivisionScale(models.Model):
    """Division/GPA scales based on total points"""

    DIVISION_CHOICES = [
        ('I', 'Division I'),
        ('II', 'Division II'),
        ('III', 'Division III'),
        ('IV', 'Division IV'),
        ('0', 'Division 0'),
    ]

    education_level = models.ForeignKey(
        EducationalLevel,
        on_delete=models.CASCADE,
        limit_choices_to={'level_type__in': ['O_LEVEL', 'A_LEVEL']},
        related_name='division_scales'
    )
    min_points = models.PositiveIntegerField()
    max_points = models.PositiveIntegerField()
    division = models.CharField(max_length=5, choices=DIVISION_CHOICES)
    description = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['min_points']
        unique_together = ['education_level', 'division']
        verbose_name = 'Division Scale'
        verbose_name_plural = 'Division Scales'

    def clean(self):
        # Enforce O-Level / A-Level only at the model level, not just the
        # FK widget filter — limit_choices_to only restricts the admin UI,
        # not programmatic saves.
        if self.education_level_id:
            level_type = self.education_level.level_type
            if level_type not in ('O_LEVEL', 'A_LEVEL'):
                raise ValidationError(
                    "Division scales are only applicable to O-Level and A-Level. "
                    f"'{self.education_level}' is '{self.education_level.get_level_type_display()}'."
                )

        if self.min_points is not None and self.max_points is not None:
            if self.min_points > self.max_points:
                raise ValidationError("Min points cannot exceed max points")

            # Check for overlapping point ranges per education level
            overlapping = DivisionScale.objects.filter(
                education_level=self.education_level,
                min_points__lt=self.max_points,
                max_points__gt=self.min_points,
            ).exclude(pk=self.pk)
            if overlapping.exists():
                raise ValidationError(
                    f"Point range {self.min_points}–{self.max_points} overlaps with an existing division band."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.education_level.name} | {self.division} ({self.min_points}-{self.max_points})"


# ============================================================================
# STUDENT RESULTS MODELS
# ============================================================================

class StudentPaperScore(models.Model):
    """Individual paper scores for students"""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='paper_scores',
        db_index=True
    )
    exam_paper = models.ForeignKey(
        SubjectExamPaper,
        on_delete=models.CASCADE,
        related_name='student_scores',
        db_index=True
    )
    marks = models.DecimalField(max_digits=5, decimal_places=2)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'exam_paper']
        verbose_name = "Student Paper Score"
        verbose_name_plural = "Student Paper Scores"

    def clean(self):
        if self.marks is not None and self.exam_paper_id:
            if self.marks < 0:
                raise ValidationError("Marks cannot be negative.")
            if self.marks > self.exam_paper.max_marks:
                raise ValidationError(
                    f"Marks ({self.marks}) cannot exceed the paper maximum "
                    f"({self.exam_paper.max_marks})."
                )

        # Validate the student is actually enrolled in the class level
        # and academic year this exam paper belongs to
        if self.student_id and self.exam_paper_id:
            session = self.exam_paper.exam_session
            is_enrolled = StudentEnrollment.objects.filter(
                student=self.student,
                academic_year=session.academic_year,
                class_level=session.class_level,
            ).exists()
            if not is_enrolled:
                raise ValidationError(
                    f"'{self.student}' is not enrolled in "
                    f"'{session.class_level}' for {session.academic_year}. "
                    f"Only enrolled students can have scores recorded."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.full_name} - {self.exam_paper} - {self.marks}"


class StudentSubjectResult(models.Model):
    """Aggregated subject results for students"""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='subject_results',
        db_index=True
    )
    exam_session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name='subject_results',
        db_index=True
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='student_results'
    )
    total_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    # Grade value is derived by looking up GradingScale at result-calculation time.
    # No hardcoded choices here — valid grades are defined in GradingScale.
    grade = models.CharField(max_length=2)
    points = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True
    )
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'exam_session', 'subject']
        ordering = ['exam_session', 'subject']
        verbose_name = "Student Subject Result"
        verbose_name_plural = "Student Subject Results"

    def __str__(self):
        return f"{self.student.full_name} - {self.subject} - {self.grade}"


class StudentExamMetrics(models.Model):
    """Overall exam metrics for students"""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='exam_metrics',
        db_index=True
    )
    exam_session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name='student_metrics',
        db_index=True
    )
    total_marks = models.DecimalField(max_digits=8, decimal_places=2)
    average_marks = models.DecimalField(max_digits=5, decimal_places=2)
    total_points = models.DecimalField(max_digits=5, decimal_places=2)
    # Division value is derived by looking up DivisionScale at result-calculation time.
    # No hardcoded choices here — valid divisions are defined in DivisionScale.
    division = models.CharField(max_length=10)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'exam_session']
        verbose_name = "Student Exam Metrics"
        verbose_name_plural = "Student Exam Metrics"

    def __str__(self):
        return f"{self.student.full_name} - {self.exam_session} - {self.division}"


class StudentExamPosition(models.Model):
    """Student positions in exams"""

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='exam_positions',
        db_index=True
    )
    exam_session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name='student_positions',
        db_index=True
    )
    class_position = models.PositiveIntegerField(null=True, blank=True)
    stream_position = models.PositiveIntegerField(null=True, blank=True)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'exam_session']
        verbose_name = "Student Exam Position"
        verbose_name_plural = "Student Exam Positions"

    def clean(self):
        """Prevent two students from sharing the same position in the same exam session."""
        if self.class_position is not None:
            conflict = StudentExamPosition.objects.filter(
                exam_session=self.exam_session,
                class_position=self.class_position,
            ).exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError(
                    f"Class position {self.class_position} is already assigned "
                    f"to another student in this exam session."
                )

        # Stream position is only meaningful if the student is assigned to a
        # stream. Stream context is now resolved via StudentStreamAssignment
        # (ExamSession no longer carries stream_class directly).
        if self.stream_position is not None and self.student_id and self.exam_session_id:
            student_has_stream = StudentStreamAssignment.objects.filter(
                enrollment__student=self.student,
                enrollment__academic_year=self.exam_session.academic_year,
            ).exists()
            if not student_has_stream:
                raise ValidationError(
                    f"Cannot assign a stream position to '{self.student}' "
                    f"because they have not been assigned to a stream for "
                    f"{self.exam_session.academic_year}."
                )
            conflict = StudentExamPosition.objects.filter(
                exam_session=self.exam_session,
                stream_position=self.stream_position,
                # Scope conflict check to students in the same stream
                student__enrollments__stream_assignment__stream_class=(
                    StudentStreamAssignment.objects.filter(
                        enrollment__student=self.student,
                        enrollment__academic_year=self.exam_session.academic_year,
                    ).values('stream_class')[:1]
                ),
            ).exclude(pk=self.pk)
            if conflict.exists():
                raise ValidationError(
                    f"Stream position {self.stream_position} is already assigned "
                    f"to another student in the same stream for this exam session."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.full_name} - Class: {self.class_position}, Stream: {self.stream_position}"


# ============================================================================
# EDUCATION HISTORY MODELS
# ============================================================================

class School(models.Model):
    """Schools where students previously studied"""

    name = models.CharField(max_length=200)
    educational_level = models.ForeignKey(
        EducationalLevel,
        on_delete=models.SET_NULL,
        null=True,
        related_name='schools'
    )
    location = models.CharField(max_length=200, blank=True)
    registration_number = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'location']
        # Remove unique_together constraint - we'll handle validation in form/model
        verbose_name = "School"
        verbose_name_plural = "Schools"

    def __str__(self):
        if self.location:
            return f"{self.name} ({self.location}) - {self.educational_level.name if self.educational_level else 'No Level'}"
        return f"{self.name} - {self.educational_level.name if self.educational_level else 'No Level'}"
    

class StudentEducationHistory(models.Model):
    """
    Previous education history of a student before joining this school.

    Result fields are level-dependent:

    PRIMARY (Std 7 / PSLE)
    ───────────────────────
        total_marks  — aggregate marks from PSLE
        grade        — overall grade (A, B, C, etc.)
        division     — must be blank  (primary has no division system)
        total_points — must be blank  (primary has no point system)

    O-LEVEL (Form 4 / NECTA)
    ────────────────────────
        division     — NECTA division (I, II, III, IV, 0)
        total_points — best 7 subject points total
        total_marks  — must be blank  (O-Level results are not expressed as total marks)
        grade        — must be blank  (O-Level results are not expressed as a single grade)

    Transfer students follow the same rules based on the level
    of the school they are transferring from.
    """

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='education_history'
    )
    school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_histories'
    )
    class_completed = models.CharField(
        max_length=50,
        help_text="Example: Std 7, Form 4"
    )
    completion_year = models.IntegerField(
        null=True,
        blank=True,
        validators=[
            MinValueValidator(1950),
            MaxValueValidator(2100),
        ],
        help_text="Year of completion (e.g., 2020)"
    )
    examination_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        help_text="NECTA index number from the previous level"
    )
    combination = models.ForeignKey(
        Combination,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="For A-Level history only"
    )

    # ---- Primary result fields (PRIMARY level only) ----------------------
    grade = models.CharField(
        max_length=5,
        blank=True,
        help_text=(
            "Overall PSLE grade — applicable for Primary history only. "
            "NECTA provides grades per subject and an overall grade on the "
            "result slip without raw marks or averages."
        )
    )

    # ---- O-Level / A-Level result fields --------------------------------
    division = models.CharField(
        max_length=5,
        blank=True,
        help_text="NECTA division (I, II, III, IV, 0) — applicable for O-Level and A-Level history only"
    )
    total_points = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Best 7 subject points total — applicable for O-Level and A-Level history only"
    )

    is_transfer = models.BooleanField(default=False)
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-completion_year']
        verbose_name = "Student Education History"
        verbose_name_plural = "Student Education Histories"

    def _get_level_type(self):
        """Resolve the level_type from the linked school's educational level."""
        if self.school_id and self.school and self.school.educational_level:
            return self.school.educational_level.level_type
        return None

    def clean(self):
        if self.completion_year is not None:
            if self.completion_year > timezone.now().year:
                raise ValidationError("Completion year cannot be in the future.")

        level_type = self._get_level_type()

        if level_type == 'PRIMARY':
            # Primary result — only the overall PSLE grade is recorded.
            # NECTA publishes grades per subject and an overall grade on the
            # result slip. Raw marks and averages are not provided to students
            # or receiving schools, so there is nothing else to store.
            if self.division:
                raise ValidationError(
                    "Division is not applicable for Primary level history. "
                    "Primary (PSLE) results use an overall grade only."
                )
            if self.total_points is not None:
                raise ValidationError(
                    "Points are not applicable for Primary level history. "
                    "Primary (PSLE) results use an overall grade only."
                )
            if self.combination:
                raise ValidationError(
                    "Combination is not applicable for Primary level history."
                )

        elif level_type == 'O_LEVEL':
            # O-Level result — division and total_points only
            if self.grade:
                raise ValidationError(
                    "Overall grade is not applicable for O-Level history. "
                    "O-Level results use division and points only."
                )
            if self.combination:
                raise ValidationError(
                    "Combination is not applicable for O-Level history. "
                    "Combination applies to A-Level history only."
                )
            # Validate division value against existing DivisionScale records
            if self.division and self.school_id:
                ed_level = self.school.educational_level
                valid_divisions = list(
                    DivisionScale.objects.filter(
                        education_level=ed_level
                    ).values_list('division', flat=True)
                )
                if valid_divisions and self.division not in valid_divisions:
                    raise ValidationError(
                        f"Division '{self.division}' is not a valid division for "
                        f"'{ed_level}'. Valid divisions are: {', '.join(valid_divisions)}."
                    )

        elif level_type == 'A_LEVEL':
            # A-Level history — division and points only, combination is allowed
            if self.grade:
                raise ValidationError(
                    "Overall grade is not applicable for A-Level history. "
                    "A-Level results use division and points only."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.full_name} - {self.school} ({self.completion_year})"


# ============================================================================
# STUDENT TRANSFER MODELS
# ============================================================================

class StudentTransferOut(models.Model):
    """
    Records when a student leaves this school to join another institution.

    Creating this record is the single action that marks a student as
    transferred — Student.status is automatically set to 'transferred'
    when this record is saved, so no separate manual status update is needed.

    This is the school's permanent evidence of the departure: when it
    happened, where the student went, why, and what documents were issued.
    It is required for TEMIS school register compliance and district
    education officer inspections.
    """

    REASON_CHOICES = [
        ('relocation', 'Family Relocation'),
        ('fees',       'Unable to Pay Fees'),
        ('discipline', 'Disciplinary Transfer'),
        ('voluntary',  'Voluntary Transfer'),
        ('medical',    'Medical Reasons'),
        ('other',      'Other'),
    ]

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name='transfer_out',
        help_text="A student can only have one outgoing transfer record."
    )
    transfer_date = models.DateField(
        help_text="The date the student officially left this school."
    )
    destination_school = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_transfers',
        help_text=(
            "The school the student transferred to if it exists in the "
            "School registry. Leave blank if unknown or not yet registered."
        )
    )
    destination_school_name = models.CharField(
        max_length=200,
        blank=True,
        help_text=(
            "Free-text name of the destination school if it does not exist "
            "in the School registry. Used when the receiving school is known "
            "by name but has not been registered in the system."
        )
    )
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        default='voluntary'
    )
    last_class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transfer_outs',
        help_text="The class level the student was in when they transferred out."
    )
    last_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        related_name='transfer_outs',
        help_text="The academic year during which the transfer occurred."
    )
    transfer_letter_issued = models.BooleanField(
        default=False,
        help_text="Whether an official transfer letter was issued to the student."
    )
    transcript_issued = models.BooleanField(
        default=False,
        help_text="Whether an academic transcript/results summary was issued."
    )
    authorised_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='authorised_transfers',
        help_text="The staff member (e.g. Headmaster) who authorised this transfer."
    )
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Transfer Out"
        verbose_name_plural = "Student Transfers Out"

    def clean(self):
        if self.transfer_date and self.transfer_date > timezone.now().date():
            raise ValidationError("Transfer date cannot be in the future.")

        # Warn if neither a school FK nor a free-text name is provided —
        # at least one should be present so the destination is not completely
        # unknown. This is a soft warning via remarks guidance, not a hard
        # block, since unknown destinations do occur and must still be recorded.
        if not self.destination_school_id and not self.destination_school_name:
            # We allow this but the __str__ will reflect "Unknown School"
            pass

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            # Automatically mark the student as transferred — this is the
            # single authoritative action that changes their status.
            # We update directly on the model instance and also persist it
            # so both the in-memory object and the database stay in sync.
            Student.objects.filter(pk=self.student_id).update(status='transferred')
            self.student.status = 'transferred'  # keep in-memory object consistent
            super().save(*args, **kwargs)

    def __str__(self):
        destination = (
            str(self.destination_school)
            if self.destination_school
            else self.destination_school_name or "Unknown School"
        )
        return f"{self.student.full_name} → {destination} ({self.transfer_date})"


class StudentSuspension(models.Model):
    """
    Records a student suspension — a temporary removal from school.

    Uses ForeignKey (not OneToOneField) because a student can be
    suspended, return, and be suspended again — each suspension is a
    separate record with its own dates, reason, and lifting details.

    Saving a new suspension automatically sets Student.status to
    'suspended'. Setting is_lifted=True automatically restores
    Student.status back to 'active'.
    """

    REASON_CHOICES = [
        ('discipline',  'Disciplinary Issues'),
        ('fees',        'Fee Defaulting'),
        ('examination', 'Examination Misconduct'),
        ('other',       'Other'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='suspensions',
        help_text="The suspended student."
    )
    suspension_date = models.DateField(
        help_text="The date the suspension takes effect."
    )
    expected_return_date = models.DateField(
        null=True,
        blank=True,
        help_text="Expected date the student may return. Can be left blank if indefinite."
    )
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        default='discipline'
    )
    authorised_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='authorised_suspensions',
        help_text="Staff member (e.g. Headmaster) who authorised this suspension."
    )

    # Lifting details — filled in when the suspension is ended
    is_lifted = models.BooleanField(
        default=False,
        help_text=(
            "Mark True when the suspension is lifted. "
            "This automatically restores the student's status to 'active'."
        )
    )
    lifted_date = models.DateField(
        null=True,
        blank=True,
        help_text="The date the suspension was officially lifted."
    )
    lifted_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lifted_suspensions',
        help_text="Staff member who lifted the suspension."
    )
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-suspension_date']
        verbose_name = "Student Suspension"
        verbose_name_plural = "Student Suspensions"

    def clean(self):
        if self.suspension_date and self.suspension_date > timezone.now().date():
            raise ValidationError("Suspension date cannot be in the future.")

        if self.expected_return_date and self.suspension_date:
            if self.expected_return_date <= self.suspension_date:
                raise ValidationError(
                    "Expected return date must be after the suspension date."
                )

        if self.is_lifted:
            if not self.lifted_date:
                raise ValidationError(
                    "Lifted date is required when marking a suspension as lifted."
                )
            if not self.lifted_by_id:
                raise ValidationError(
                    "Lifted by (staff member) is required when marking a suspension as lifted."
                )
            if self.lifted_date and self.suspension_date:
                if self.lifted_date < self.suspension_date:
                    raise ValidationError(
                        "Lifted date cannot be before the suspension date."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            if self.is_lifted:
                # Lifting a suspension — restore student to active only if
                # they have no other active (non-lifted) suspensions
                other_active = StudentSuspension.objects.filter(
                    student=self.student,
                    is_lifted=False,
                ).exclude(pk=self.pk)
                if not other_active.exists():
                    Student.objects.filter(pk=self.student_id).update(status='active')
                    self.student.status = 'active'
            else:
                # New or updated suspension — mark student as suspended
                Student.objects.filter(pk=self.student_id).update(status='suspended')
                self.student.status = 'suspended'
            super().save(*args, **kwargs)

    def __str__(self):
        status = "Lifted" if self.is_lifted else "Active"
        return (
            f"{self.student.full_name} — Suspended {self.suspension_date} "
            f"({self.get_reason_display()}) [{status}]"
        )


class StudentWithdrawal(models.Model):
    """
    Records a student withdrawal (dropout) — permanent departure from the
    school without transferring to another institution.

    Uses OneToOneField because withdrawal is a one-time permanent event.
    Unlike suspension, there is no return — if a withdrawn student comes
    back they must be re-admitted as a new student.

    Saving this record automatically sets Student.status to 'withdrawn'.
    """

    REASON_CHOICES = [
        ('fees',        'Unable to Pay Fees'),
        ('family',      'Family Circumstances'),
        ('illness',     'Illness / Medical'),
        ('pregnancy',   'Pregnancy'),
        ('employment',  'Went to Work / Employment'),
        ('disability',  'Disability / Health Condition'),
        ('other',       'Other'),
    ]

    student = models.OneToOneField(
        Student,
        on_delete=models.CASCADE,
        related_name='withdrawal',
        help_text="A student can only have one withdrawal record."
    )
    withdrawal_date = models.DateField(
        help_text="The last date the student attended school."
    )
    reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        default='other'
    )
    last_class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.SET_NULL,
        null=True,
        related_name='withdrawals',
        help_text="The class level the student was in when they withdrew."
    )
    last_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        related_name='withdrawals',
        help_text="The academic year during which the withdrawal occurred."
    )
    authorised_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='authorised_withdrawals',
        help_text="Staff member who recorded/authorised this withdrawal."
    )
    transcript_issued = models.BooleanField(
        default=False,
        help_text="Whether an academic transcript was issued to the student."
    )
    remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Withdrawal"
        verbose_name_plural = "Student Withdrawals"

    def clean(self):
        if self.withdrawal_date and self.withdrawal_date > timezone.now().date():
            raise ValidationError("Withdrawal date cannot be in the future.")

        # A transferred student cannot also be withdrawn —
        # these are mutually exclusive departure types
        if self.student_id:
            if hasattr(self.student, 'transfer_out'):
                raise ValidationError(
                    f"'{self.student}' already has a transfer out record. "
                    f"A student cannot be both transferred and withdrawn."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        with transaction.atomic():
            Student.objects.filter(pk=self.student_id).update(status='withdrawn')
            self.student.status = 'withdrawn'
            super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.student.full_name} — Withdrawn {self.withdrawal_date} "
            f"({self.get_reason_display()})"
        )


# ============================================================================
# STAFF LEAVE MODELS
# ============================================================================

class StaffLeave(models.Model):
    """
    Records a staff member's leave application and its outcome.

    Leave is an HR function managed by the Headmaster. The workflow is:
        1. Leave is created with status='pending'
        2. Headmaster approves (status='approved') or rejects (status='rejected')
        3. On approval, the leave dates are locked — no further edits allowed
           unless the Headmaster explicitly reverts to pending.

    A staff member can have multiple leave records across their career.
    Leave periods for the same staff member cannot overlap — enforced in clean().
    """

    LEAVE_TYPE_CHOICES = [
        ('annual',       'Annual Leave'),
        ('sick',         'Sick Leave'),
        ('maternity',    'Maternity Leave'),
        ('paternity',    'Paternity Leave'),
        ('study',        'Study Leave'),
        ('compassionate','Compassionate Leave'),   # bereavement, family emergency
        ('unpaid',       'Unpaid Leave'),
        ('other',        'Other'),
    ]

    STATUS_CHOICES = [
        ('pending',   'Pending'),    # submitted, awaiting approval
        ('approved',  'Approved'),   # approved by Headmaster
        ('rejected',  'Rejected'),   # rejected by Headmaster
        ('cancelled', 'Cancelled'),  # cancelled by staff member before approval
    ]

    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name='leaves',
        help_text="The staff member applying for leave."
    )
    leave_type = models.CharField(
        max_length=20,
        choices=LEAVE_TYPE_CHOICES,
        default='annual'
    )
    start_date = models.DateField(
        help_text="First day of leave."
    )
    end_date = models.DateField(
        help_text="Last day of leave (inclusive)."
    )
    duration_days = models.PositiveIntegerField(
        editable=False,
        help_text="Auto-calculated from start and end dates."
    )
    reason = models.TextField(
        help_text="Staff member's reason for the leave request."
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Approval details — filled when status changes to approved or rejected
    reviewed_by = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_leaves',
        help_text="Staff member (Headmaster) who approved or rejected this leave."
    )
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date and time the leave was approved or rejected."
    )
    review_remarks = models.TextField(
        blank=True,
        help_text="Headmaster's remarks on approval or rejection."
    )

    # Substitute arrangement
    substitute = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='substitute_leaves',
        help_text=(
            "Staff member covering the absent teacher's duties. "
            "Particularly important for teaching staff."
        )
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Staff Leave"
        verbose_name_plural = "Staff Leaves"

    def clean(self):
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError(
                    "End date cannot be before start date."
                )

            # Duration is inclusive of both start and end dates
            delta = (self.end_date - self.start_date).days + 1
            self.duration_days = delta

            # Prevent overlapping leave periods for the same staff member.
            # Two leaves overlap when one starts before the other ends.
            overlapping = StaffLeave.objects.filter(
                staff=self.staff,
                status__in=('pending', 'approved'),
                start_date__lte=self.end_date,
                end_date__gte=self.start_date,
            ).exclude(pk=self.pk)

            if overlapping.exists():
                other = overlapping.first()
                raise ValidationError(
                    f"This leave period ({self.start_date} – {self.end_date}) "
                    f"overlaps with an existing leave record "
                    f"({other.start_date} – {other.end_date}, {other.get_status_display()}). "
                    f"A staff member cannot have two overlapping leave periods."
                )

        # A leave cannot be approved without a reviewer
        if self.status == 'approved' and not self.reviewed_by_id:
            raise ValidationError(
                "An approved leave must have a reviewer (the staff member "
                "who approved it). Please set 'reviewed by'."
            )

        # A rejected leave must also have a reviewer and review remarks
        if self.status == 'rejected':
            if not self.reviewed_by_id:
                raise ValidationError(
                    "A rejected leave must have a reviewer."
                )
            if not self.review_remarks:
                raise ValidationError(
                    "Please provide review remarks explaining why this "
                    "leave was rejected."
                )

        # A staff member cannot review their own leave
        if self.reviewed_by_id and self.reviewed_by_id == self.staff_id:
            raise ValidationError(
                "A staff member cannot approve or reject their own leave."
            )

    def save(self, *args, **kwargs):
        # Ensure duration_days is always set before saving
        if self.start_date and self.end_date:
            self.duration_days = (self.end_date - self.start_date).days + 1
        elif not self.duration_days:
            self.duration_days = 0
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.staff} — {self.get_leave_type_display()} "
            f"({self.start_date} to {self.end_date}) [{self.get_status_display()}]"
        )


# ============================================================================
# AUDIT & SESSION TRACKING MODELS
# ============================================================================

class StaffSession(models.Model):
    """
    Tracks login/logout sessions for staff and students.

    Created on login via Django's user_logged_in signal.
    Updated on every request via AuditMiddleware (last_activity).
    Closed on logout via user_logged_out signal.

    is_online becomes False when:
      - The user explicitly logs out (logout signal fires)
      - The session expires due to inactivity (middleware detects this)

    Readable by: Headmaster (Management portal) and system administrator.
    """

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='sessions',
        db_index=True
    )
    session_key = models.CharField(
        max_length=40,
        db_index=True,
        help_text="Django session key — links this record to the active session."
    )
    logged_in_at = models.DateTimeField(
        help_text="When the user logged in."
    )
    last_activity = models.DateTimeField(
        help_text="Time of the most recent request in this session."
    )
    logged_out_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the user logged out. Null if still active or session expired."
    )
    is_online = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True while the session is active. False after logout or expiry."
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address at the time of login."
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Browser/device information at the time of login."
    )

    class Meta:
        ordering = ['-logged_in_at']
        verbose_name = "Staff Session"
        verbose_name_plural = "Staff Sessions"

    def __str__(self):
        status = "Online" if self.is_online else "Offline"
        return f"{self.user} — {self.logged_in_at:%Y-%m-%d %H:%M} [{status}]"

    @property
    def duration(self):
        """
        Returns session duration as a timedelta.
        Uses logged_out_at if available, otherwise last_activity.
        """
        end = self.logged_out_at or self.last_activity
        return end - self.logged_in_at


class AuditLog(models.Model):
    """
    Permanent record of every CREATE, UPDATE, DELETE, LOGIN, and LOGOUT
    action performed in the system.

    For CREATE and DELETE: changes field contains the full record as JSON.
    For UPDATE: changes field contains only the fields that changed,
                each with 'before' and 'after' values:
                {"marks": {"before": 45, "after": 78}}

    This record is never deleted — it is the school's accountability trail.
    Readable by: Headmaster (Management portal) and system administrator.

    ── How it is written ──────────────────────────────────────────────────
    Model-level signals (post_save, post_delete) write CRUD entries.
    Authentication signals (user_logged_in, user_logged_out) write
    LOGIN/LOGOUT entries.

    The current user is passed to signals via a thread-local variable
    set by AuditMiddleware on every request. Programmatic changes
    (management commands, bulk uploads) are attributed to a system user
    if no request user is available.
    """

    ACTION_CHOICES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('DELETE', 'Deleted'),
        ('LOGIN',  'Logged In'),
        ('LOGOUT', 'Logged Out'),
    ]

    # Who performed the action
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        db_index=True,
        help_text=(
            "The user who performed this action. Null for system-initiated "
            "actions (bulk uploads, management commands)."
        )
    )

    # What action was performed
    action = models.CharField(
        max_length=10,
        choices=ACTION_CHOICES,
        db_index=True
    )

    # Which model and which record was affected
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
        help_text="The Django model that was affected (e.g. StudentSubjectResult)."
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Primary key of the affected record."
    )
    object_repr = models.CharField(
        max_length=300,
        blank=True,
        help_text=(
            "Human-readable representation of the affected record at the "
            "time of the action. e.g. 'John Doe - Biology - A'. "
            "Stored as a string so it remains readable even after the "
            "record is deleted."
        )
    )

    # What changed — only populated for UPDATE actions
    # Format: {"field_name": {"before": old_value, "after": new_value}, ...}
    # For CREATE: full record values as {"field_name": value, ...}
    # For DELETE: full record values as {"field_name": value, ...}
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "For UPDATE: changed fields only with before/after values. "
            "For CREATE/DELETE: full record snapshot."
        )
    )

    # Session context
    session = models.ForeignKey(
        'StaffSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text="The login session during which this action was performed."
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )
    user_agent = models.TextField(blank=True)

    # Timestamp — indexed for date-range queries
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True
    )

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        # Composite indexes for the most common query patterns:
        # "Show all actions by this user" and "Show all changes to this record"
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['content_type', 'object_id', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]

    def __str__(self):
        user_str = str(self.user) if self.user else "System"
        return (
            f"{user_str} — {self.get_action_display()} "
            f"{self.object_repr} at {self.timestamp:%Y-%m-%d %H:%M:%S}"
        )

    @classmethod
    def log(
        cls,
        action: str,
        user=None,
        instance=None,
        changes: dict = None,
        request=None,
        session=None,
    ):
        """
        Convenience class method for writing an audit log entry.
        
        Usage in signals:
            AuditLog.log(
                action='UPDATE',
                user=current_user,
                instance=student_result_instance,
                changes={'marks': {'before': 45, 'after': 78}},
                request=request,
            )

        Usage for LOGIN/LOGOUT (no instance):
            AuditLog.log(action='LOGIN', user=user, request=request)
        """
        # Sanitize changes to ensure JSON serializable
        sanitized_changes = cls._sanitize_for_json(changes or {})
        
        entry = cls(
            user=user,
            action=action,
            changes=sanitized_changes,
            session=session,
        )

        if instance is not None:
            entry.content_type = ContentType.objects.get_for_model(instance)
            entry.object_id = instance.pk
            entry.object_repr = str(instance)[:300]

        if request is not None:
            entry.ip_address = cls._get_client_ip(request)
            entry.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]

        try:
            entry.save()
        except Exception as e:
            # Log the error but don't crash the main operation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Audit log write failed: {str(e)}")
            
            # Try one more time with minimal data
            try:
                entry.changes = {'error': 'Could not serialize full changes'}
                entry.save()
            except:
                pass  # Give up if even that fails
            
        return entry

    @classmethod
    def _sanitize_for_json(cls, obj):
        """Recursively sanitize objects for JSON serialization"""
        if obj is None:
            return None
        
        # Handle primitive types
        if isinstance(obj, (str, int, float, bool)):
            return obj
        
        # Handle Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        
        # Handle datetime/date
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        
        # Handle dictionaries
        if isinstance(obj, dict):
            return {str(k): cls._sanitize_for_json(v) for k, v in obj.items()}
        
        # Handle lists/tuples
        if isinstance(obj, (list, tuple)):
            return [cls._sanitize_for_json(item) for item in obj]
        
        # Handle Django model instances
        if hasattr(obj, 'pk'):
            return {
                'id': obj.pk,
                'repr': str(obj)[:100],
                'model': obj.__class__.__name__
            }
        
        # Handle file fields
        if hasattr(obj, 'name') and hasattr(obj, 'path'):
            return str(obj.name) if obj.name else None
        
        # Handle querysets
        if hasattr(obj, 'values_list'):
            try:
                return [cls._sanitize_for_json(item) for item in obj[:10]]  # Limit to 10 items
            except:
                return str(obj)[:200]
        
        # Fallback: convert to string
        try:
            return str(obj)[:200]
        except:
            return None

    @staticmethod
    def _get_client_ip(request) -> str:
        """
        Extract the real client IP from the request, handling proxies.
        X-Forwarded-For is checked first for reverse-proxy setups.
        """
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            # X-Forwarded-For can be a comma-separated list;
            # the first IP is the original client
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')



# core/models.py

class SchoolProfileManager(models.Manager):
    """Custom manager for SchoolProfile model."""
    
    def get_queryset(self):
        """Return the base queryset."""
        return super().get_queryset()
    
    def get_active_profile(self, educational_level=None):
        """
        Get the active school profile.
        If educational_level is provided, returns the profile for that level,
        otherwise returns the main school profile.
        """
        if educational_level:
            return self.filter(
                educational_level=educational_level,
                is_active=True
            ).first()
        return self.filter(educational_level__isnull=True, is_active=True).first()
    
    def get_school_info(self, educational_level=None):
        """
        Get school information as a dictionary for use in views.
        """
        profile = self.get_active_profile(educational_level)
        if profile:
            return {
                'code': profile.code,
                'name': profile.name,
                'registration_number': profile.registration_number,
                'address': profile.address,
                'phone': profile.get_contact_phone(),
                'alternative_phone': profile.alternative_phone,
                'email': profile.email,
                'website': profile.website,
                'motto': profile.motto,
                'vision': profile.vision,
                'mission': profile.mission,
                'established_year': profile.established_year,
                'logo': profile.logo,
                'contact_person': profile.get_contact_name(),
            }
        return self._get_default_school_info()
    
    def _get_default_school_info(self):
        """Return default school information from settings."""
        from django.conf import settings
        return {
            'code': getattr(settings, 'SCHOOL_CODE', 'S2348'),
            'name': getattr(settings, 'SCHOOL_NAME', 'School Management System'),
            'registration_number': getattr(settings, 'SCHOOL_REGISTRATION_NUMBER', ''),
            'address': getattr(settings, 'SCHOOL_ADDRESS', ''),
            'phone': getattr(settings, 'SCHOOL_PHONE', ''),
            'email': getattr(settings, 'SCHOOL_EMAIL', ''),
            'motto': getattr(settings, 'SCHOOL_MOTTO', ''),
        }


class SchoolProfile(models.Model):
    """
    School/Institution profile information supporting multiple educational levels.
    Stores information about the current school/institution.
    Different from School model which stores previous schools students attended.
    """
    
    # School identification
    code = models.CharField(max_length=20, unique=True, help_text="School code (e.g., RISS-PRIMARY)")
    name = models.CharField(max_length=200, help_text="Full school name")
    registration_number = models.CharField(max_length=50, unique=True, help_text="Official registration number")
    
    # Educational level (can be null for main school record)
    educational_level = models.ForeignKey(
        'EducationalLevel',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='school_profiles',
        help_text="Educational level this school serves (leave blank for main record)"
    )
    
    # Contact information
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    alternative_phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    
    # School details
    motto = models.CharField(max_length=200, blank=True)
    vision = models.TextField(blank=True)
    mission = models.TextField(blank=True)
    established_year = models.PositiveIntegerField(null=True, blank=True)
    
    # Media
    logo = models.ImageField(upload_to='school/logos/', blank=True, null=True)
    
    # Contact person (Headmaster/Principal)
    contact_person = models.ForeignKey(
        'Staff',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='school_profiles_managed',
        help_text="Headmaster/Principal of this school"
    )
    
    # Active status
    is_active = models.BooleanField(default=True)
    
    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Custom manager
    objects = SchoolProfileManager()
    
    class Meta:
        verbose_name = "School Profile"
        verbose_name_plural = "School Profiles"
        ordering = ['code']
        unique_together = ['code', 'educational_level']
    
    def __str__(self):
        if self.educational_level:
            return f"{self.name} ({self.educational_level.code})"
        return self.name
    
    def get_contact_phone(self):
        """Get contact phone, prioritizing headmaster's phone if available."""
        if self.contact_person and self.contact_person.phone_number:
            return self.contact_person.phone_number
        return self.phone
    
    def get_contact_name(self):
        """Get contact person name."""
        if self.contact_person:
            return self.contact_person.get_full_name()
        return "Headmaster"