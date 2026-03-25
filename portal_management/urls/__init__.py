"""
portal_management/urls/__init__.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Combines all URL modules into one urlpatterns list.
The root portal_management/urls.py imports from here.
"""

from .dashboard import urlpatterns as dashboard_urls
from .students import urlpatterns as student_urls
from .staff import urlpatterns as staff_urls
from .academics import urlpatterns as academic_urls
from .exams import urlpatterns as exam_urls
from .reports import urlpatterns as report_urls
from .schools import urlpatterns as school_urls
from .suspensions import urlpatterns as suspension_urls
from .student_withdrawal  import urlpatterns as student_withdrawal_urls
from .student_education_history   import urlpatterns as student_education_history_urls
from .parent   import urlpatterns as parent_urls
from .school_profile   import urlpatterns as school_profile_urls

app_name = "management"

urlpatterns = (
    dashboard_urls +
    student_urls +
    staff_urls +
    academic_urls +
    exam_urls +
    report_urls +
    school_urls +
    student_withdrawal_urls +
    suspension_urls +
    school_profile_urls +
    parent_urls +
    student_education_history_urls

)