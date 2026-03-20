"""
school_project/settings.py
"""
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-change-me')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

SCHOOL_CODE = config('SCHOOL_CODE', default='S2348')
SCHOOL_NAME = config('SCHOOL_NAME', default='School Management System')

# ─── Applications ────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'crispy_forms',
    'crispy_bootstrap5',

    # Project apps
    'core.apps.CoreConfig',
    'audit.apps.AuditConfig',
    'accounts.apps.AccountsConfig',
    'portal_management.apps.PortalManagementConfig',
    'portal_academic.apps.PortalAcademicConfig',
    'portal_administration.apps.PortalAdministrationConfig',
    'portal_finance.apps.PortalFinanceConfig',
    'portal_transport.apps.PortalTransportConfig',
    'portal_library.apps.PortalLibraryConfig',
    'portal_health.apps.PortalHealthConfig',
    'results.apps.ResultsConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'audit.middleware.AuditMiddleware',
]

ROOT_URLCONF = 'school_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.school_info',
            ],
        },
    },
]

WSGI_APPLICATION = 'school_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME':     config('DB_NAME',     default='raudhwa_islamic_db'),
        'USER':     config('DB_USER',     default='root'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST':     config('DB_HOST',     default='127.0.0.1'),
        'PORT':     config('DB_PORT',     default='3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

AUTH_USER_MODEL = 'core.CustomUser'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'accounts:redirect'
LOGOUT_REDIRECT_URL = 'accounts:login'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

SESSION_INACTIVITY_TIMEOUT = config('SESSION_INACTIVITY_TIMEOUT', default=1800, cast=int)

# Portal group names — add new groups here when new roles are created
MANAGEMENT_PORTAL_GROUPS = ['headmaster_group', 'deputy_headmaster_group', 'hod_group']
ACADEMIC_PORTAL_GROUPS = ['academic_group', 'class_teacher_group']
ADMINISTRATION_PORTAL_GROUPS = ['secretary_group', 'administrator_group']
FINANCE_PORTAL_GROUPS = ['accountant_group']
TRANSPORT_PORTAL_GROUPS = ['driver_group']
LIBRARY_PORTAL_GROUPS = ['librarian_group']
HEALTH_PORTAL_GROUPS = ['nurse_group', 'matron_group']

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'verbose'},
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'school.log',
            'formatter': 'verbose',
        },
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'audit': {'handlers': ['console', 'file'], 'level': 'INFO', 'propagate': False},
        'results': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
    },
}