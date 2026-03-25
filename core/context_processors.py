# core/context_processors.py

from django.conf import settings
from django.core.exceptions import FieldError
import logging

logger = logging.getLogger(__name__)

def school_info(request):
    """Add school information to all templates."""
    school_info_dict = {}
    
    try:
        from core.models import SchoolProfile
        
        # Try to get the main school profile
        try:
            profile = SchoolProfile.objects.filter(
                educational_level__isnull=True, 
                is_active=True
            ).first()
        except FieldError:
            # If the field doesn't exist yet (migrations not run), fallback to settings
            logger.warning("SchoolProfile model fields not ready, using settings fallback")
            profile = None
        
        if profile:
            school_info_dict = {
                'SCHOOL_CODE': profile.code,
                'SCHOOL_NAME': profile.name,
                'SCHOOL_ADDRESS': profile.address,
                'SCHOOL_PHONE': profile.get_contact_phone(),
                'SCHOOL_EMAIL': profile.email,
                'SCHOOL_MOTTO': profile.motto,
                'SCHOOL_REGISTRATION_NUMBER': profile.registration_number,
                'SCHOOL_LOGO': profile.logo,
                'CONTACT_PERSON': profile.get_contact_name(),
            }
        else:
            # Fallback to settings
            school_info_dict = {
                'SCHOOL_CODE': getattr(settings, 'SCHOOL_CODE', ''),
                'SCHOOL_NAME': getattr(settings, 'SCHOOL_NAME', 'School Management System'),
                'SCHOOL_ADDRESS': getattr(settings, 'SCHOOL_ADDRESS', ''),
                'SCHOOL_PHONE': getattr(settings, 'SCHOOL_PHONE', ''),
                'SCHOOL_EMAIL': getattr(settings, 'SCHOOL_EMAIL', ''),
                'SCHOOL_MOTTO': getattr(settings, 'SCHOOL_MOTTO', ''),
                'SCHOOL_REGISTRATION_NUMBER': getattr(settings, 'SCHOOL_REGISTRATION_NUMBER', ''),
            }
            
    except ImportError:
        # If SchoolProfile model doesn't exist yet, use settings
        logger.warning("SchoolProfile model not available, using settings fallback")
        school_info_dict = {
            'SCHOOL_CODE': getattr(settings, 'SCHOOL_CODE', ''),
            'SCHOOL_NAME': getattr(settings, 'SCHOOL_NAME', 'School Management System'),
            'SCHOOL_ADDRESS': getattr(settings, 'SCHOOL_ADDRESS', ''),
            'SCHOOL_PHONE': getattr(settings, 'SCHOOL_PHONE', ''),
            'SCHOOL_EMAIL': getattr(settings, 'SCHOOL_EMAIL', ''),
            'SCHOOL_MOTTO': getattr(settings, 'SCHOOL_MOTTO', ''),
            'SCHOOL_REGISTRATION_NUMBER': getattr(settings, 'SCHOOL_REGISTRATION_NUMBER', ''),
        }
    except Exception as e:
        # Catch any other errors and fallback to settings
        logger.error(f"Error in school_info context processor: {e}")
        school_info_dict = {
            'SCHOOL_CODE': getattr(settings, 'SCHOOL_CODE', ''),
            'SCHOOL_NAME': getattr(settings, 'SCHOOL_NAME', 'School Management System'),
            'SCHOOL_ADDRESS': getattr(settings, 'SCHOOL_ADDRESS', ''),
            'SCHOOL_PHONE': getattr(settings, 'SCHOOL_PHONE', ''),
            'SCHOOL_EMAIL': getattr(settings, 'SCHOOL_EMAIL', ''),
            'SCHOOL_MOTTO': getattr(settings, 'SCHOOL_MOTTO', ''),
            'SCHOOL_REGISTRATION_NUMBER': getattr(settings, 'SCHOOL_REGISTRATION_NUMBER', ''),
        }
    
    return school_info_dict