"""Create or update the optional deployment bootstrap administrator."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create or update a superuser for first-run deployments."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--name", default="admin")
        parser.add_argument(
            "--preserve-password",
            action="store_true",
            help="Do not change the password when the user already exists.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip()
        password = options["password"]
        name = options["name"].strip() or "admin"
        if not email:
            raise CommandError("--email is required")
        if not password:
            raise CommandError("--password is required")

        user_model = get_user_model()
        normalized_email = user_model.objects.normalize_email(email).lower()
        user, created = user_model.objects.get_or_create(
            email=normalized_email,
            defaults={"name": name, "is_staff": True, "is_superuser": True, "is_active": True},
        )

        update_fields = []
        if created or not options["preserve_password"]:
            user.set_password(password)
            update_fields.append("password")
        if not user.name:
            user.name = name
            update_fields.append("name")
        for field in ("is_staff", "is_superuser", "is_active"):
            if getattr(user, field) is not True:
                setattr(user, field, True)
                update_fields.append(field)
        if update_fields:
            update_fields.append("updated_at")
            user.save(update_fields=update_fields)

        status = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"bootstrap admin {status}: {normalized_email}"))
