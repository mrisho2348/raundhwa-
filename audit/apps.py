from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audit'
    verbose_name = 'Audit Trail'

    def ready(self):
        """
        Import and register audit signals when the app is ready.
        """
        import audit.signals
        audit.signals.register_audit_signals()