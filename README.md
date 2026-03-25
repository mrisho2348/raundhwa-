# School Management System

A comprehensive school management system for Tanzania education system supporting Nursery, Primary, O-Level, and A-Level education.

## Features

### Student Management
- Student enrollment with registration number generation
- Student profile management with profile pictures
- Student status tracking (Active, Suspended, Withdrawn, Completed, Transferred)
- Education history tracking
- Parent/Guardian management
- Student transfers and withdrawals
- Promotion management
- A-Level combination assignments

### Staff Management
- Staff profile management
- Staff role assignments with permission groups
- Department assignments
- Teaching assignments
- Class teacher assignments
- Staff leave management

### Academic Structure
- Educational levels (Nursery, Primary, O-Level, A-Level)
- Academic years and terms
- Class levels and stream classes
- Subjects and A-Level combinations
- Department management

### Examinations & Results
- Exam type management
- Exam session creation and management
- Subject exam paper configuration
- Result entry (manual and bulk Excel upload)
- Automatic grade calculation based on grading scales
- Division scale for O-Level/A-Level
- Subject results summary with grade distribution
- Student performance analytics
- Paper-wise analytics with statistics
- Export results to Excel and PDF

### Reports & Analytics
- Student academic trend tracking
- Subject performance analysis
- Grade distribution reports
- Gender performance analysis
- Export reports to PDF/Excel

### System Features
- User authentication with role-based access
- Audit logging for all actions
- School profile management
- Online user tracking
- Responsive design with mobile support
- Premium UI with Bootstrap 5

## Technology Stack

- **Backend**: Django 4.2
- **Database**: PostgreSQL / SQLite
- **Frontend**: Bootstrap 5, jQuery
- **Libraries**: DataTables, Select2, Chart.js, SweetAlert2
- **Reporting**: WeasyPrint, OpenPyXL
- **Icons**: Bootstrap Icons

## Installation

### Prerequisites
- Python 3.10+
- pip
- virtualenv

### Setup Instructions

1. Clone the repository:
```bash
git clone https://github.com/yourusername/school-management-system.git
cd school-management-system