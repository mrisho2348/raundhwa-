from django.apps import AppConfig

class CoreConfig(AppConfig):
    name = 'core'
    verbose_name = 'Core'

    def ready(self):
        pass  # signals handled by audit app
