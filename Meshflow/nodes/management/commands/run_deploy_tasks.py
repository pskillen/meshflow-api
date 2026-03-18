"""
Run all deploy/upgrade tasks in order.

Add new tasks to DEPLOY_TASKS; no deployment config changes needed.
Used by the migrations container on deploy.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand

# (command_name, args_list, kwargs)
DEPLOY_TASKS = [
    ("sync_nodelateststatus", [], {}),
]


class Command(BaseCommand):
    help = "Run deploy tasks (migrate, sync_nodelateststatus, etc.)"

    def handle(self, *args, **options):
        for name, args_list, kwargs in DEPLOY_TASKS:
            self.stdout.write(f"Running: {name}")
            call_command(name, *args_list, **kwargs)
        self.stdout.write(self.style.SUCCESS("All deploy tasks completed"))
