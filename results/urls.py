from django.urls import path
from . import views

app_name = 'results'

urlpatterns = [
    path('calculate/<int:session_id>/', views.calculate_results, name='calculate'),
    path('export/student/<int:student_id>/', views.export_student_report, name='export_student'),
    path('export/session/<int:session_id>/', views.export_session_report, name='export_session'),
]
