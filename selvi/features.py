"""
Feature flag system for V2 UI.

Flags can be toggled via:
- Environment variables (V2_FEATURE_<NAME>)
- Django settings (V2_FEATURES dict)
"""

import os
from django.conf import settings


def _get_feature(name, default=False):
    env_key = f'V2_FEATURE_{name.upper()}'
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val.lower() in ('1', 'true', 'yes', 'on')

    features = getattr(settings, 'V2_FEATURES', {})
    return features.get(name, default)


FEATURES = {
    'v2_ui': _get_feature('v2_ui', default=True),
    'v2_api': _get_feature('v2_api', default=True),
    'v2_orders': _get_feature('v2_orders', default=True),
    'v2_production': _get_feature('v2_production', default=True),
    'v2_inventory': _get_feature('v2_inventory', default=True),
    'v2_quality': _get_feature('v2_quality', default=True),
    'v2_painting': _get_feature('v2_painting', default=True),
    'v2_packaging': _get_feature('v2_packaging', default=True),
    'v2_shipping': _get_feature('v2_shipping', default=True),
    'v2_reporting': _get_feature('v2_reporting', default=True),
}


def is_enabled(name):
    return FEATURES.get(name, False)


def require_feature(name):
    """Decorator for views that check a feature flag."""
    from django.http import HttpResponseForbidden
    from functools import wraps

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not is_enabled(name):
                return HttpResponseForbidden('V2 feature is disabled')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


class V2FeatureMixin:
    """Mixin for API views to check feature flags."""

    feature_name = None

    def initial(self, request, *args, **kwargs):
        if self.feature_name and not is_enabled(self.feature_name):
            from rest_framework.response import Response
            from rest_framework import status
            return Response(
                {'detail': f'Feature {self.feature_name} is disabled'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().initial(request, *args, **kwargs)
