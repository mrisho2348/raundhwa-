"""
core/management/commands/setup_school.py
════════════════════════════════════════
Initial school setup command. Run once after first migration:

    python manage.py setup_school

Creates:
  - Django permission groups for each portal
  - Default staff roles linked to groups
  - A superuser admin account (if none exists)

Usage:
    python manage.py setup_school
    python manage.py setup_school --admin-username admin --admin-password secret
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


ROLES = [
    # (role_name, group_name, portal_category)
    ('Headmaster',       'headmaster_group',        'management'),
    ('Deputy Headmaster','deputy_headmaster_group',  'management'),
    ('HOD',              'hod_group',               'management'),
    ('Academic',         'academic_group',           'academic'),
    ('Class Teacher',    'class_teacher_group',      'academic'),
    ('Secretary',        'secretary_group',          'administration'),
    ('Administrator',    'administrator_group',      'administration'),
    ('Accountant',       'accountant_group',         'finance'),
    ('Driver',           'driver_group',             'transport'),
    ('Librarian',        'librarian_group',          'library'),
    ('Nurse',            'nurse_group',              'health'),
    ('Matron',           'matron_group',             'health'),
    ('Cook',             None,                       'none'),
    ('Cleaner',          None,                       'none'),
    ('Watchman',         None,                       'none'),
]


class Command(BaseCommand):
    help = 'Initial school system setup — creates groups, roles, and admin user'

    def add_arguments(self, parser):
        parser.add_argument('--admin-username', default='admin')
        parser.add_argument('--admin-email', default='admin@school.ac.tz')
        parser.add_argument('--admin-password', default='Admin@1234')

    def handle(self, *args, **options):
        from core.models import CustomUser, StaffRole, UserType

        self.stdout.write(self.style.MIGRATE_HEADING('Setting up school system...'))

        # ── Create groups ─────────────────────────────────────────────────
        group_map = {}
        for role_name, group_name, portal in ROLES:
            if group_name:
                group, created = Group.objects.get_or_create(name=group_name)
                group_map[group_name] = group
                status = 'created' if created else 'exists'
                self.stdout.write(f'  Group [{status}]: {group_name}')

        # ── Create staff roles ────────────────────────────────────────────
        for role_name, group_name, portal in ROLES:
            group = group_map.get(group_name)
            role, created = StaffRole.objects.get_or_create(
                name=role_name,
                defaults={
                    'portal_category': portal,
                    'group': group,
                    'description': f'{role_name} role — auto-created by setup_school',
                }
            )
            if not created:
                # Update portal category and group if role already existed
                role.portal_category = portal
                if group:
                    role.group = group
                role.save()
            status = 'created' if created else 'updated'
            self.stdout.write(f'  Role [{status}]: {role_name} → {portal}')

        # ── Create superuser ──────────────────────────────────────────────
        username = options['admin_username']
        email = options['admin_email']
        password = options['admin_password']

        if not CustomUser.objects.filter(username=username).exists():
            user = CustomUser.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                user_type=UserType.HOD,
            )
            self.stdout.write(
                self.style.SUCCESS(f'\n  Superuser created: {username} / {password}')
            )
        else:
            self.stdout.write(f'\n  Superuser already exists: {username}')

        self.stdout.write(self.style.SUCCESS('\nSetup complete! You can now run the server.'))
        self.stdout.write(
            self.style.WARNING(
                '\nNext steps:\n'
                '  1. python manage.py runserver\n'
                f'  2. Login at http://127.0.0.1:8000/ with {username}/{password}\n'
                '  3. Add educational levels, academic year, class levels, subjects\n'
                '  4. Add staff and assign roles\n'
            )
        )
