# School Management System

A complete, production-ready Django school management system built for
Tanzanian schools. Supports multiple educational levels (Nursery, Primary,
O-Level, A-Level), multi-portal role-based access, NECTA-aligned result
computation, and full audit logging.

---

## Quick Start

```bash
# 1. Clone / extract the project
cd school_project

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set SECRET_KEY, SCHOOL_NAME, SCHOOL_CODE

# 5. Run migrations
python manage.py migrate

# 6. Initial setup (creates groups, roles, admin user)
python manage.py setup_school

# 7. Create media and logs directories
mkdir -p media logs

# 8. Run the development server
python manage.py runserver
```

Open http://127.0.0.1:8000/ and login with:
- Username: `admin`
- Password: `Admin@1234`

---

## Project Structure

```
school_project/
├── school_project/         # Main Django config
│   ├── settings.py         # All settings + portal group config
│   ├── urls.py             # Root URL routing
│   └── wsgi.py
│
├── core/                   # All 39 models live here
│   ├── models.py           # Complete model file (3,051 lines)
│   ├── mixins.py           # Portal access control mixins
│   ├── context_processors.py
│   └── management/
│       └── commands/
│           └── setup_school.py   # Run once after migrate
│
├── audit/                  # Audit logging system
│   ├── middleware.py       # Thread-local user + session tracking
│   ├── signals.py          # CRUD + login/logout audit signals
│   └── apps.py             # Signal registration on startup
│
├── accounts/               # Login, logout, password change
│   ├── views.py            # Role-based login routing
│   └── urls.py
│
├── portal_management/      # Headmaster / HOD portal (FULLY BUILT)
│   ├── views.py            # All management views
│   ├── forms.py            # All management forms
│   └── urls.py             # All management URLs
│
├── portal_academic/        # Teacher portal (scaffolded)
├── portal_administration/  # Secretary portal (scaffolded)
├── portal_finance/         # Accountant portal (scaffolded)
├── portal_transport/       # Driver portal (scaffolded)
├── portal_library/         # Librarian portal (scaffolded)
├── portal_health/          # Nurse/Matron portal (scaffolded)
│
├── results/                # Result computation engine
│   ├── services.py         # Full pipeline: scores→results→metrics→positions
│   ├── utils.py            # Excel export (student + session reports)
│   └── views.py            # Calculate + export endpoints
│
├── templates/
│   ├── shared/
│   │   └── base.html       # Bootstrap 5 + Select2 + DataTables base
│   ├── accounts/           # Login, change password, student portal
│   └── portal_management/  # All management portal templates
│       ├── dashboard.html
│       ├── students/       # list, detail, form, enroll
│       ├── staff/          # list, detail, form, roles
│       ├── academic/       # levels, years, classes, subjects, departments
│       ├── exams/          # sessions, grading scales, session detail
│       └── reports/        # audit log, online users
│
├── static/                 # Your custom CSS/JS goes here
├── media/                  # Uploaded files (profile pictures etc.)
├── logs/                   # Application logs
└── requirements.txt
```

---

## The 39 Models

### Authentication & Users
| Model | Purpose |
|---|---|
| `CustomUser` | Extends Django auth. Types: HOD(1), Staff(2), Student(3) |
| `AdminHOD` | HOD profile |

### Core Configuration
| Model | Purpose |
|---|---|
| `EducationalLevel` | Nursery, Primary, O-Level, A-Level |
| `AcademicYear` | One active at a time |
| `Term` | 3 terms per year, overlap-protected |
| `Department` | Academic departments |

### Academic Structure
| Model | Purpose |
|---|---|
| `ClassLevel` | Form 1–6, Std 1–7. Has `is_final` flag |
| `StreamClass` | Form 1A, 2B. Has capacity enforcement |
| `Subject` | NECTA-coded per educational level |
| `Combination` | A-Level combinations (PCM, HGL etc.) |
| `CombinationSubject` | Subjects within combinations (CORE/SUBSIDIARY) |

### Staff Management
| Model | Purpose |
|---|---|
| `Staff` | Personal + employment. Optional user account |
| `StaffRole` | Free-text roles linked to Django Groups + portal |
| `StaffRoleAssignment` | Role history, auto-syncs user ↔ group |
| `StaffDepartmentAssignment` | Department membership history |
| `StaffTeachingAssignment` | Subject × class × year |
| `ClassTeacherAssignment` | Class teacher per stream per year |
| `StaffLeave` | Leave applications with approval workflow |

### Student Management
| Model | Purpose |
|---|---|
| `Student` | Auto-generates reg number + CustomUser account |
| `StudentEnrollment` | Class enrollment per year. Full promotion rules |
| `StudentStreamAssignment` | Separate stream assignment with capacity |
| `Parent` | Guardian information |
| `StudentParent` | Student–parent junction. Fee responsibility per child |
| `StudentSubjectAssignment` | O-Level elective subject assignments |

### Examinations & Results
| Model | Purpose |
|---|---|
| `ExamType` | Midterm, Terminal, Mock, NECTA |
| `ExamSession` | Exam event. Auto-generated name |
| `SubjectExamPaper` | Papers within a session |
| `GradingScale` | A–F grades with mark ranges and points |
| `DivisionScale` | Division I–IV/0 with point ranges |
| `StudentPaperScore` | Raw marks per paper |
| `StudentSubjectResult` | Aggregated subject result with grade + points |
| `StudentExamMetrics` | Total marks, average, total points, division |
| `StudentExamPosition` | Class and stream rankings |

### Student Lifecycle
| Model | Purpose |
|---|---|
| `School` | Previous schools registry |
| `StudentEducationHistory` | Previous academic records |
| `StudentTransferOut` | Auto-sets status='transferred' |
| `StudentSuspension` | With lifting workflow |
| `StudentWithdrawal` | Permanent departure record |

### Audit & Sessions
| Model | Purpose |
|---|---|
| `StaffSession` | Login/logout/activity tracking |
| `AuditLog` | Permanent CRUD trail. Before/after diffs |

---

## Portal Access Control

Access is controlled by Django Groups. Configure in `settings.py`:

```python
MANAGEMENT_PORTAL_GROUPS    = ['headmaster_group', 'deputy_headmaster_group', 'hod_group']
ACADEMIC_PORTAL_GROUPS      = ['academic_group', 'class_teacher_group']
ADMINISTRATION_PORTAL_GROUPS = ['secretary_group', 'administrator_group']
FINANCE_PORTAL_GROUPS       = ['accountant_group']
TRANSPORT_PORTAL_GROUPS     = ['driver_group']
LIBRARY_PORTAL_GROUPS       = ['librarian_group']
HEALTH_PORTAL_GROUPS        = ['nurse_group', 'matron_group']
```

Adding a new role:
1. Create `StaffRole` in database (no code change)
2. Create Django `Group` (no code change)
3. Add group name to the right list in `settings.py` (one line)
4. Assign role to staff member — they automatically get group access

---

## Result Computation

Results are computed explicitly (not via signals) for performance with bulk uploads:

```python
from results.services import calculate_session_results

# After uploading all paper scores for a session:
summary = calculate_session_results(exam_session_id)
# summary = {
#     'subject_results': {'created': 150, 'updated': 0, 'skipped': 0},
#     'metrics': {'created': 30, 'updated': 0, 'skipped': 2},
#     'positions': {'class_positions': 30, 'stream_positions': 15},
# }
```

The pipeline:
1. **`calculate_subject_results()`** — sums paper scores per student×subject, assigns grade+points
2. **`calculate_metrics()`** — O-Level: best 7 subjects. A-Level: best 3 core + 1 subsidiary. Primary: average marks
3. **`calculate_positions()`** — ranks by total_points (O/A-Level) or average_marks (Primary)

All three steps run in O(1) DB queries regardless of student count.

---

## Audit Logging

Every CREATE, UPDATE, DELETE on important models is logged automatically.
Login/logout events are also logged.

```python
# Query from views:
from core.models import AuditLog

# Everything a user did today
logs = AuditLog.objects.filter(user=user, timestamp__date=today)

# All changes to a specific student
from django.contrib.contenttypes.models import ContentType
ct = ContentType.objects.get_for_model(Student)
logs = AuditLog.objects.filter(content_type=ct, object_id=student.pk)

# Who is online right now
from core.models import StaffSession
online = StaffSession.objects.filter(is_online=True).select_related('user')
```

---

## Building the Remaining Portals

Each scaffolded portal (`portal_academic`, `portal_administration` etc.)
has `views.py`, `urls.py`, and a dashboard template ready.

To add features to a portal:

**1. Add a view in `portal_academic/views.py`:**
```python
from core.mixins import AcademicRequiredMixin
from core.models import StaffTeachingAssignment

class MyClassesView(AcademicRequiredMixin, TemplateView):
    template_name = 'portal_academic/my_classes.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        staff = self.request.user.staff_profile
        ctx['assignments'] = StaffTeachingAssignment.objects.filter(
            staff=staff,
            academic_year__is_active=True,
        ).select_related('subject', 'class_level')
        return ctx
```

**2. Add the URL in `portal_academic/urls.py`:**
```python
path('my-classes/', views.MyClassesView.as_view(), name='my_classes'),
```

**3. Create the template in `templates/portal_academic/my_classes.html`:**
```html
{% extends 'shared/base.html' %}
{% block portal_primary %}#198754{% endblock %}
{% block page_title %}My Classes{% endblock %}
{% block sidebar_menu %}
<a href="{% url 'academic:dashboard' %}" class="nav-link">
    <i class="bi bi-speedometer2"></i>
    <span class="link-text">Dashboard</span>
</a>
<a href="{% url 'academic:my_classes' %}" class="nav-link active">
    <i class="bi bi-book"></i>
    <span class="link-text">My Classes</span>
</a>
{% endblock %}
{% block content %}
<!-- your content here -->
{% endblock %}
```

---

## Student Login

Students log in at the same URL (`/`) using:
- **Username:** Their registration number (e.g. `S2348/0001/2025`)
- **Password:** Same as username on first login

On first login, they are redirected to change their password.
The student portal is at `/student/`.

---

## Technology Stack

| Component | Technology |
|---|---|
| Backend | Django 5.0 |
| Database | SQLite (dev) / PostgreSQL (production) |
| UI Framework | Bootstrap 5.3 |
| Data Tables | DataTables 1.13 with Bootstrap 5 theme |
| Select Inputs | Select2 4.1 with Bootstrap 5 theme |
| Confirmations | SweetAlert2 11 |
| Icons | Bootstrap Icons 1.11 |
| Excel Export | openpyxl 3.1 |
| Forms | django-crispy-forms + crispy-bootstrap5 |
| Static Files | WhiteNoise |

---

## Planned Future Modules

The structure is ready for these without breaking changes:

| Module | Portal | Key Models to Add |
|---|---|---|
| Fee Management | Finance | `FeeStructure`, `StudentInvoice`, `Payment` |
| Attendance | Academic | `ClassAttendance`, `StudentAttendanceRecord` |
| Hostel | Administration | `Hostel`, `Room`, `BedAllocation`, `HostelAttendance` |
| Transport | Transport | `Vehicle`, `Route`, `StudentTransportAssignment` |
| Library | Library | `Book`, `BookCopy`, `BorrowRecord` |
| Health | Health | `StudentHealthRecord`, `SickVisit` |
| Timetable | Academic/Management | `Period`, `TimetableSlot` |
| Notifications | All | `Notification`, `NotificationRecipient` |
