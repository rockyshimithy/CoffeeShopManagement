from django.core.management.base import BaseCommand, CommandError

from apps.identity.models import User


class Command(BaseCommand):
    help = "Create the first active admin, and refuse once one exists."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        if User.objects.filter(role=User.Role.ADMIN, is_active=True).exists():
            raise CommandError("An active admin already exists.")
        user = User.objects.create_superuser(
            email=options["email"], password=options["password"]
        )
        self.stdout.write(self.style.SUCCESS(f"Created admin {user.email}"))
