"""
One-off script: set up the Ojukaye NewsAi bot's profile.
Run:  python fix_newsai.py     (NOT manage.py shell)
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ojukaye_project.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import UserProfile
from django.core.files import File


def main():
    bot, created = User.objects.get_or_create(
        username='newsai',
        defaults={
            'first_name': 'Ojukaye',
            'last_name': 'NewsAi',
            'email': 'newsai@ojukaye.local',
            'is_active': False,
        }
    )
    if created:
        bot.set_unusable_password()
        bot.save()
        print("Created newsai user")
    else:
        print("newsai user exists")

    profile, _ = UserProfile.objects.get_or_create(user=bot)
    profile.bio = 'Ojukaye NewsAi — automated news curation powered by AI.'
    profile.save()
    print("Profile ok")

    # ---- Avatar ----
    with open('static/images/logo.jpeg', 'rb') as f:
        profile.profile_pic.save('newsai_logo.jpeg', File(f), save=True)
    print("Avatar:", profile.profile_pic.url)

    # ---- Cover ----
    with open('static/images/newsbot_banner.png', 'rb') as f:
        profile.cover_photo.save('newsai_banner.png', File(f), save=True)
    print("Cover:", profile.cover_photo.url)

    print("Done.")


if __name__ == '__main__':
    main()