from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from apps.accounts.models import UserProfile

class Command(BaseCommand):
    help = 'Create missing user profiles for existing users'

    def handle(self, *args, **options):
        users_without_profile = []
        for user in User.objects.all():
            try:
                # Try to access the profile
                profile = user.profile
            except UserProfile.DoesNotExist:
                users_without_profile.append(user)
                # Create profile
                UserProfile.objects.create(user=user)
                self.stdout.write(self.style.SUCCESS(f'Created profile for user: {user.username}'))
        
        if not users_without_profile:
            self.stdout.write(self.style.SUCCESS('All users already have profiles'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Created {len(users_without_profile)} profiles'))