# portal_management/utils/school_utils.py

from core.models import SchoolProfile

def get_school_info(request=None, educational_level=None):
    """
    Get school information for a specific educational level.
    
    Args:
        request: Optional request object for user info
        educational_level: Optional EducationalLevel object to get level-specific school
    
    Returns:
        dict: School information dictionary
    """
    school_info = SchoolProfile.objects.get_school_info(educational_level)
    
    # Add generated_by if request is provided
    if request:
        school_info['generated_by'] = request.user.get_full_name() or request.user.username
    
    return school_info


def get_school_info_for_session(session, request=None):
    """
    Get school information for an exam session.
    Tries to get the school from class_level, then educational level.
    """
    # Try to get school from class_level's school_profile first
    if session.class_level and session.class_level.school_profile:
        school_info = get_school_info(request, session.class_level.educational_level)
        # Override with class_level's school if it exists
        profile = session.class_level.school_profile
        school_info.update({
            'name': profile.name,
            'code': profile.code,
            'registration_number': profile.registration_number,
            'address': profile.address or school_info.get('address', ''),
            'phone': profile.get_contact_phone() or school_info.get('phone', ''),
            'email': profile.email or school_info.get('email', ''),
            'motto': profile.motto or school_info.get('motto', ''),
        })
    else:
        school_info = get_school_info(request, session.class_level.educational_level)
    
    return school_info