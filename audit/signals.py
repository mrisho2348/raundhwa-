"""
audit/signals.py
════════════════
All audit-related signal handlers in one place.

Sections:
  1. Authentication signals  — login/logout → StaffSession + AuditLog
  2. CRUD model signals      — post_save / post_delete → AuditLog
  3. Helper utilities        — diff computation, field serialisation

━━ How the current user is resolved ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Every HTTP request stores the user in thread-local via AuditMiddleware.
Signal handlers call get_current_user() to retrieve it.
For programmatic changes (bulk upload, management commands) the thread-local
is empty so get_current_user() returns None — the audit log entry is still
written but user is recorded as NULL ("System").

━━ Which models are audited ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL_MODELS — every change logged with full field diff
IMPORTANT_MODELS — changes logged (field diff)
To add a new model: import it and add to the appropriate set below.

━━ Connecting signals ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
In your audit/apps.py:

    class AuditConfig(AppConfig):
        name = 'audit'
        def ready(self):
            import audit.signals  # noqa: F401

In settings.py INSTALLED_APPS:
    'audit.apps.AuditConfig',
"""

import logging
import threading
from decimal import Decimal
from datetime import date, datetime

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from audit.middleware import get_current_request, get_current_session, get_current_user

logger = logging.getLogger(__name__)

# Thread-local storage for pre-save snapshots
_pre_save_snapshots = threading.local()


def _get_snapshots() -> dict:
    """Get the thread-local snapshot dictionary."""
    if not hasattr(_pre_save_snapshots, 'data'):
        _pre_save_snapshots.data = {}
    return _pre_save_snapshots.data


# ─────────────────────────────────────────────────────────────────────────────
# Which models to audit
# ─────────────────────────────────────────────────────────────────────────────

def _get_audited_models():
    """
    Lazy import to avoid circular imports at module load time.
    Returns (CRITICAL_MODELS, IMPORTANT_MODELS) as sets of model classes.
    """
    from core.models import (
        # Critical — result integrity
        StudentPaperScore,
        StudentSubjectResult,
        StudentExamMetrics,
        ExamSession,
        GradingScale,
        DivisionScale,

        # Critical — student lifecycle
        Student,
        StudentEnrollment,
        StudentTransferOut,
        StudentSuspension,
        StudentWithdrawal,
        StudentStreamAssignment,

        # Critical — staff access control
        StaffRoleAssignment,
        Staff,

        # Important — configuration
        AcademicYear,
        Term,
        ClassLevel,
        Subject,
        Combination,
        StaffLeave,
        StaffTeachingAssignment,
        ClassTeacherAssignment,
    )

    CRITICAL = {
        StudentPaperScore,
        StudentSubjectResult,
        StudentExamMetrics,
        ExamSession,
        GradingScale,
        DivisionScale,
        Student,
        StudentEnrollment,
        StudentTransferOut,
        StudentSuspension,
        StudentWithdrawal,
        StudentStreamAssignment,
        StaffRoleAssignment,
        Staff,
    }

    IMPORTANT = {
        AcademicYear,
        Term,
        ClassLevel,
        Subject,
        Combination,
        StaffLeave,
        StaffTeachingAssignment,
        ClassTeacherAssignment,
    }

    return CRITICAL, IMPORTANT


# ─────────────────────────────────────────────────────────────────────────────
# Field serialisation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _serialise_value(value):
    """
    Convert a model field value to a JSON-safe type.
    Handles Decimal, date, datetime, file fields, and related model instances.
    """
    if value is None:
        return None
    
    # Handle primitive types
    if isinstance(value, (str, int, float, bool)):
        return value
    
    # Handle Decimal
    if isinstance(value, Decimal):
        return float(value)
    
    # Handle date and datetime
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    
    # Handle file fields (ImageField, FileField)
    if hasattr(value, 'name') and hasattr(value, 'path'):
        return {
            'name': str(value.name) if value.name else None,
            'url': value.url if hasattr(value, 'url') and value else None,
            'size': value.size if hasattr(value, 'size') else None,
        }
    
    # Handle related model instances
    if hasattr(value, 'pk'):
        return {
            'id': value.pk,
            'repr': str(value)[:100],
            'model': value.__class__.__name__
        }
    
    # Handle querysets and lists
    if hasattr(value, '__iter__') and not isinstance(value, str):
        try:
            return [_serialise_value(item) for item in list(value)[:10]]  # Limit to 10 items
        except:
            return str(value)[:200]
    
    # Fallback: convert to string
    try:
        return str(value)[:200]
    except:
        return None


def _get_model_fields(instance) -> dict:
    """
    Return a dict of {field_name: serialised_value} for all concrete
    fields on a model instance. Skips auto-generated audit fields to
    avoid infinite loops.
    """
    SKIP_FIELDS = {'created_at', 'updated_at'}
    result = {}
    
    try:
        for field in instance._meta.concrete_fields:
            if field.name in SKIP_FIELDS:
                continue
            try:
                value = field.value_from_object(instance)
                result[field.name] = _serialise_value(value)
            except Exception as e:
                logger.debug(f"Failed to serialize field {field.name}: {e}")
                result[field.name] = None
    except Exception as e:
        logger.error(f"Error getting model fields: {e}")
    
    return result


def _compute_diff(old_data: dict, new_data: dict) -> dict:
    """
    Return only the fields that changed between old and new snapshots.
    Format: {"field": {"before": old_value, "after": new_value}}
    """
    diff = {}
    all_keys = set(old_data.keys()) | set(new_data.keys())
    
    for key in all_keys:
        old_val = old_data.get(key)
        new_val = new_data.get(key)
        
        # Skip if both values are None
        if old_val is None and new_val is None:
            continue
        
        # Compare serialized values
        if old_val != new_val:
            diff[key] = {
                'before': old_val,
                'after': new_val
            }
    
    return diff


# ─────────────────────────────────────────────────────────────────────────────
# Pre-save: snapshot the old state before any change is applied
# ─────────────────────────────────────────────────────────────────────────────

def _connect_pre_save_for(model_class):
    """Connect pre-save signal for a model class."""
    
    @receiver(pre_save, sender=model_class, weak=False)
    def capture_pre_save(sender, instance, **kwargs):
        if kwargs.get('raw'):
            return  # Skip fixture loading
        
        if instance.pk:
            # Existing record — fetch current state from DB for accurate diff
            try:
                db_instance = sender.objects.get(pk=instance.pk)
                snapshot = _get_model_fields(db_instance)
                _get_snapshots()[(sender, instance.pk)] = snapshot
            except sender.DoesNotExist:
                pass
            except Exception as e:
                logger.error(f"Error capturing pre-save snapshot for {sender.__name__}: {e}")


def _connect_post_save_for(model_class):
    """Connect post-save signal for a model class."""
    
    @receiver(post_save, sender=model_class, weak=False)
    def capture_post_save(sender, instance, created, **kwargs):
        if kwargs.get('raw'):
            return  # Skip fixture loading
        
        _write_crud_log(sender, instance, created=created)


def _connect_post_delete_for(model_class):
    """Connect post-delete signal for a model class."""
    
    @receiver(post_delete, sender=model_class, weak=False)
    def capture_post_delete(sender, instance, **kwargs):
        _write_crud_log(sender, instance, deleted=True)


# ─────────────────────────────────────────────────────────────────────────────
# Core CRUD log writer
# ─────────────────────────────────────────────────────────────────────────────

def _write_crud_log(sender, instance, created=False, deleted=False):
    """
    Write one AuditLog entry for a CREATE, UPDATE, or DELETE.
    Called from post_save and post_delete receivers.
    """
    from core.models import AuditLog  # Lazy import to avoid circular imports

    try:
        user = get_current_user()
        request = get_current_request()
        session = get_current_session()

        if deleted:
            action = 'DELETE'
            changes = _get_model_fields(instance)
        elif created:
            action = 'CREATE'
            changes = _get_model_fields(instance)
        else:
            action = 'UPDATE'
            key = (sender, instance.pk)
            snapshots = _get_snapshots()
            old_data = snapshots.pop(key, {})
            new_data = _get_model_fields(instance)
            changes = _compute_diff(old_data, new_data)
            
            if not changes:
                # Nothing actually changed — skip writing a log entry
                return

        # Write the audit log
        AuditLog.log(
            action=action,
            user=user,
            instance=instance,
            changes=changes,
            request=request,
            session=session,
        )

    except Exception as exc:
        # Never let audit logging break the main operation
        logger.error(
            "Audit log write failed for %s pk=%s: %s",
            sender.__name__,
            getattr(instance, 'pk', '?'),
            exc,
            exc_info=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Connect signals for all audited models
# ─────────────────────────────────────────────────────────────────────────────

def register_audit_signals():
    """
    Connect pre_save, post_save, and post_delete signals for every
    model in CRITICAL_MODELS and IMPORTANT_MODELS.
    Called once from AuditConfig.ready().
    """
    critical, important = _get_audited_models()
    all_models = critical | important
    
    for model_class in all_models:
        try:
            _connect_pre_save_for(model_class)
            _connect_post_save_for(model_class)
            _connect_post_delete_for(model_class)
        except Exception as e:
            logger.error(f"Failed to connect signals for {model_class.__name__}: {e}")

    logger.debug(
        "Audit signals registered for %d models.",
        len(all_models),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Authentication signals — LOGIN and LOGOUT
# ─────────────────────────────────────────────────────────────────────────────

@receiver(user_logged_in)
def on_user_logged_in(sender, request, user, **kwargs):
    """
    On login:
      1. Create a StaffSession record.
      2. Write a LOGIN AuditLog entry.
    """
    from core.models import AuditLog, StaffSession  # Lazy import

    try:
        ip = AuditLog._get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        now = timezone.now()
        session_key = request.session.session_key if request.session else ''

        # Close any stale open sessions for this user
        # (e.g. browser crashed without logging out)
        StaffSession.objects.filter(
            user=user,
            is_online=True,
        ).update(
            is_online=False,
            logged_out_at=now,
            last_activity=now,
        )

        # Create fresh session record
        staff_session = StaffSession.objects.create(
            user=user,
            session_key=session_key,
            logged_in_at=now,
            last_activity=now,
            is_online=True,
            ip_address=ip,
            user_agent=user_agent,
        )

        # Store in thread-local so subsequent requests in this session
        # can reference it immediately without a DB lookup
        import audit.middleware as mw
        mw._thread_local.staff_session = staff_session

        # Write LOGIN audit entry
        AuditLog.log(
            action='LOGIN',
            user=user,
            request=request,
            session=staff_session,
            changes={
                'ip_address': ip,
                'user_agent': user_agent[:100],
                'session_key': session_key[:20] + '...' if len(session_key) > 20 else session_key
            },
        )

    except Exception as exc:
        logger.error("Failed to record login for user %s: %s", user, exc, exc_info=True)


@receiver(user_logged_out)
def on_user_logged_out(sender, request, user, **kwargs):
    """
    On logout:
      1. Close the StaffSession — set is_online=False and logged_out_at.
      2. Write a LOGOUT AuditLog entry.
    """
    from core.models import AuditLog, StaffSession  # Lazy import

    if user is None:
        return  # Anonymous session logout — nothing to record

    try:
        now = timezone.now()
        session_key = request.session.session_key if request.session else None
        staff_session = None

        if session_key:
            # Update the session
            updated = StaffSession.objects.filter(
                user=user,
                session_key=session_key,
                is_online=True,
            ).update(
                is_online=False,
                logged_out_at=now,
                last_activity=now,
            )
            
            if updated:
                staff_session = StaffSession.objects.filter(
                    user=user,
                    session_key=session_key,
                ).first()

        # Write LOGOUT audit entry
        AuditLog.log(
            action='LOGOUT',
            user=user,
            request=request,
            session=staff_session,
            changes={'session_duration': 'calculated_at_logout'},
        )

        # Clear thread-local session
        import audit.middleware as mw
        if hasattr(mw._thread_local, 'staff_session'):
            delattr(mw._thread_local, 'staff_session')

    except Exception as exc:
        logger.error("Failed to record logout for user %s: %s", user, exc, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Session tracking middleware helper
# ─────────────────────────────────────────────────────────────────────────────

def update_session_activity(user, session_key):
    """
    Update the last_activity timestamp for a user's session.
    Called from middleware on each request.
    """
    from core.models import StaffSession  # Lazy import

    try:
        StaffSession.objects.filter(
            user=user,
            session_key=session_key,
            is_online=True,
        ).update(
            last_activity=timezone.now()
        )
    except Exception as exc:
        logger.error(f"Failed to update session activity: {exc}")