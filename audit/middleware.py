"""
audit/middleware.py
═══════════════════
Two responsibilities:

1. AuditMiddleware
   - Stores the current request user in a thread-local variable so that
     model signals can attribute changes to the correct user without
     needing access to the request object.
   - Updates StaffSession.last_activity on every authenticated request.
   - Detects expired sessions and marks them is_online=False.

2. get_current_user() / get_current_request()
   - Called from signal handlers to retrieve the user/request that
     triggered a model change.
   - Returns None for programmatic changes (management commands,
     bulk uploads) where no HTTP request is in flight.

Usage in settings.py:
    MIDDLEWARE = [
        ...
        'audit.middleware.AuditMiddleware',
        ...
    ]

SESSION_INACTIVITY_TIMEOUT should be set in settings.py (seconds).
Default is 30 minutes if not configured.
"""

import threading
import logging
from datetime import timedelta
from typing import Optional, Any

from django.conf import settings
from django.utils import timezone
from django.http import HttpRequest

# Configure logger
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Thread-local storage — one slot per OS thread / async task
# ─────────────────────────────────────────────────────────────────────────────

class ThreadLocalStorage:
    """Simple namespace for thread-local storage."""
    user = None
    request = None
    staff_session = None
    request_start_time = None


_thread_local = threading.local()


def _get_thread_data() -> ThreadLocalStorage:
    """
    Get or create thread-local storage data.
    Returns a ThreadLocalStorage instance for the current thread.
    """
    if not hasattr(_thread_local, 'data'):
        _thread_local.data = ThreadLocalStorage()
    return _thread_local.data


def get_current_user():
    """
    Returns the CustomUser making the current HTTP request, or None if
    called outside a request context (management commands, signals fired
    by bulk operations, tests without a request).
    """
    try:
        return getattr(_get_thread_data(), 'user', None)
    except Exception:
        return None


def get_current_request():
    """
    Returns the current HttpRequest, or None outside a request context.
    """
    try:
        return getattr(_get_thread_data(), 'request', None)
    except Exception:
        return None


def get_current_session():
    """
    Returns the current StaffSession record, or None.
    """
    try:
        return getattr(_get_thread_data(), 'staff_session', None)
    except Exception:
        return None


def get_request_start_time():
    """
    Returns the start time of the current request, or None.
    """
    try:
        return getattr(_get_thread_data(), 'request_start_time', None)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────────────────────

class AuditMiddleware:
    """
    Per-request middleware that:
      1. Injects the current user into thread-local storage so signals
         can read it without access to the request.
      2. Updates StaffSession.last_activity on every authenticated request.
      3. Marks sessions as offline when they exceed the inactivity timeout.
    """

    # How long without activity before a session is considered expired.
    # Override in settings.py: SESSION_INACTIVITY_TIMEOUT = 1800  (seconds)
    DEFAULT_TIMEOUT = 30 * 60  # 30 minutes

    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = timedelta(
            seconds=getattr(settings, 'SESSION_INACTIVITY_TIMEOUT', self.DEFAULT_TIMEOUT)
        )

    def __call__(self, request):
        # Initialize thread-local data
        thread_data = self._init_thread_data(request)
        
        try:
            # Process the request
            response = self.get_response(request)
            
            # Update session activity after successful response
            self._update_session_activity_after_response(request, thread_data)
            
            return response
            
        except Exception as e:
            # Log the error but don't let middleware break the response
            logger.error(f"Error in AuditMiddleware: {e}", exc_info=True)
            raise
            
        finally:
            # Always clean up thread-local data
            self._cleanup_thread_data()

    def _init_thread_data(self, request: HttpRequest) -> ThreadLocalStorage:
        """
        Initialize thread-local data for this request.
        Returns the thread data object.
        """
        thread_data = _get_thread_data()
        thread_data.request = request
        thread_data.user = request.user if request.user.is_authenticated else None
        thread_data.staff_session = None
        thread_data.request_start_time = timezone.now()
        
        return thread_data

    def _cleanup_thread_data(self):
        """Clean up thread-local data after request is processed."""
        try:
            thread_data = _get_thread_data()
            thread_data.request = None
            thread_data.user = None
            thread_data.staff_session = None
            thread_data.request_start_time = None
        except Exception as e:
            logger.error(f"Error cleaning up thread data: {e}")

    def _update_session_activity_after_response(self, request: HttpRequest, thread_data: ThreadLocalStorage):
        """
        Update session activity after the response is generated.
        This runs after the main request processing to avoid blocking.
        """
        if not request.user.is_authenticated:
            return
            
        if not request.session or not request.session.session_key:
            return
            
        try:
            self._update_session_activity(request, thread_data)
        except Exception as e:
            logger.error(f"Error updating session activity: {e}")

    def _update_session_activity(self, request: HttpRequest, thread_data: ThreadLocalStorage):
        """
        Find the StaffSession for the current Django session key and
        update its last_activity timestamp. Mark any sessions that have
        exceeded the inactivity timeout as offline.
        """
        from core.models import StaffSession  # avoid circular import

        session_key = request.session.session_key
        if not session_key:
            return

        now = timezone.now()
        staff_session = None

        try:
            # Try to get existing session
            staff_session = StaffSession.objects.filter(
                session_key=session_key,
                is_online=True,
            ).first()

            if staff_session:
                # Check for inactivity timeout
                time_since_last_activity = now - staff_session.last_activity
                
                if time_since_last_activity > self.timeout:
                    # Session has expired — mark offline without a logout time
                    # since the user did not explicitly log out
                    staff_session.is_online = False
                    staff_session.last_activity = now
                    staff_session.save(update_fields=['is_online', 'last_activity'])
                    
                    logger.info(f"Session expired for user {request.user.username} due to inactivity")
                    
                else:
                    # Active session — update last_activity
                    staff_session.last_activity = now
                    staff_session.save(update_fields=['last_activity'])
                    
                    # Store in thread-local for other parts of the app
                    thread_data.staff_session = staff_session
                    
            else:
                # No active session found — try to create one if this is a new session
                # This can happen for the first request after login before the signal has fired
                self._try_create_session(request, session_key, now, thread_data)
                
        except Exception as e:
            logger.error(f"Error updating session activity for key {session_key}: {e}")

    def _try_create_session(self, request: HttpRequest, session_key: str, now: timezone.datetime, thread_data: ThreadLocalStorage):
        """
        Attempt to create a StaffSession if one doesn't exist.
        This is a fallback for cases where the login signal hasn't fired yet.
        """
        from core.models import StaffSession, AuditLog  # avoid circular import

        try:
            # Check if there's already a session record (maybe offline)
            existing_session = StaffSession.objects.filter(
                session_key=session_key,
                user=request.user,
            ).first()

            if existing_session:
                # Reactivate offline session
                existing_session.is_online = True
                existing_session.last_activity = now
                existing_session.logged_out_at = None
                existing_session.save(update_fields=['is_online', 'last_activity', 'logged_out_at'])
                
                thread_data.staff_session = existing_session
                
                # Log this as an automatic reactivation
                AuditLog.log(
                    action='LOGIN',
                    user=request.user,
                    request=request,
                    session=existing_session,
                    changes={'note': 'Session auto-reactivated after inactivity'},
                )
                
            else:
                # Create new session (shouldn't normally happen - login signal should do this)
                ip = AuditLog._get_client_ip(request)
                user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
                
                staff_session = StaffSession.objects.create(
                    user=request.user,
                    session_key=session_key,
                    logged_in_at=now,
                    last_activity=now,
                    is_online=True,
                    ip_address=ip,
                    user_agent=user_agent,
                )
                
                thread_data.staff_session = staff_session
                
                # Log this fallback creation
                AuditLog.log(
                    action='LOGIN',
                    user=request.user,
                    request=request,
                    session=staff_session,
                    changes={'note': 'Session created by middleware fallback'},
                )
                
                logger.info(f"Created fallback session for user {request.user.username}")
                
        except Exception as e:
            logger.error(f"Error creating fallback session: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Utility functions for async support (if using Django 3.1+ async views)
# ─────────────────────────────────────────────────────────────────────────────

async def get_current_user_async():
    """
    Async version of get_current_user().
    Returns the CustomUser making the current HTTP request, or None.
    """
    # For async contexts, we need to ensure we're using the correct thread-local
    # This is a simplified version - for production, consider using contextvars
    return get_current_user()


async def get_current_request_async():
    """
    Async version of get_current_request().
    Returns the current HttpRequest, or None.
    """
    return get_current_request()


# ─────────────────────────────────────────────────────────────────────────────
# Context manager for testing
# ─────────────────────────────────────────────────────────────────────────────

class audit_context:
    """
    Context manager for testing: temporarily set the current user in thread-local.
    
    Usage:
        with audit_context(user=some_user):
            # Do something that triggers signals
            student.save()
    """
    
    def __init__(self, user=None, request=None):
        self.user = user
        self.request = request
        self.old_user = None
        self.old_request = None
    
    def __enter__(self):
        thread_data = _get_thread_data()
        self.old_user = thread_data.user
        self.old_request = thread_data.request
        
        thread_data.user = self.user
        thread_data.request = self.request
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        thread_data = _get_thread_data()
        thread_data.user = self.old_user
        thread_data.request = self.old_request


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup on app shutdown (for graceful shutdown)
# ─────────────────────────────────────────────────────────────────────────────

def cleanup_thread_local():
    """
    Clean up thread-local data. Called during app shutdown.
    """
    try:
        if hasattr(_thread_local, 'data'):
            delattr(_thread_local, 'data')
    except Exception:
        pass