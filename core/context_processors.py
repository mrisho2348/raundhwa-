from django.conf import settings

def school_info(request):
    """Inject school name and code into every template context."""
    return {
        'SCHOOL_NAME': settings.SCHOOL_NAME,
        'SCHOOL_CODE': settings.SCHOOL_CODE,
    }
