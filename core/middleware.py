from django.shortcuts import render
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)


class MaintenanceModeMiddleware(MiddlewareMixin):
    """
    If maintenance_mode is on in SystemSettings:
      - Staff still get through (if allow_admin_during_maintenance is True)
      - Everyone else sees a maintenance page
      - Static/media/admin-login paths are always allowed through
    """

    # Paths always allowed through — even during maintenance
    ALWAYS_ALLOWED_PREFIXES = (
        '/static/',
        '/media/',
        '/admin/',      # Django admin login (so staff can get in)
        '/manage/',     # Custom admin panel
        '/accounts/logout/',
    )

    # Names of URLs that are always allowed
    ALWAYS_ALLOWED_NAMES = {
        'accounts:login',
        'accounts:logout',
        'accounts:register',
    }

    def process_request(self, request):
        # Fast path — no maintenance, no work
        try:
            from core.models import SystemSettings
            settings_obj = SystemSettings.get_settings()
        except Exception:
            return None

        if not settings_obj.maintenance_mode:
            return None

        # Already authenticated staff? Let them through (if setting allows)
        if settings_obj.allow_admin_during_maintenance:
            if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
                return None

        # Always-allowed URL prefixes
        path = request.path_info
        for prefix in self.ALWAYS_ALLOWED_PREFIXES:
            if path.startswith(prefix):
                return None

        # Always-allowed named URLs (login/register/logout)
        try:
            match = request.resolver_match
            if match and match.view_name in self.ALWAYS_ALLOWED_NAMES:
                return None
        except Exception:
            pass

        # Maintenance response
        return render(request, 'core/maintenance.html', {
            'message': settings_obj.maintenance_message,
            'title': 'Under Maintenance',
        }, status=503)