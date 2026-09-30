from django.conf import settings


def site_context(request):
    """Global context available to every template."""
    context = {
        'site_name': 'Ojukaye',
        'site_description': "Nigeria's Modern News & Discussion Platform",
        'DEBUG': settings.DEBUG,
    }

    # Unread notification count for logged-in users
    if request.user.is_authenticated:
        try:
            from social.models import Notification
            context['notification_count'] = Notification.objects.filter(
                user=request.user, is_read=False
            ).count()
        except Exception:
            context['notification_count'] = 0

    return context