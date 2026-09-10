"""Test configuration: ensures MEDIA_ROOT is a writable temp directory during tests.

This file works with both pytest (via pytest-django) and Django's test runner
(when DJANGO_SETTINGS_MODULE is set). The env var DJANGO_MEDIA_ROOT is set
before Django settings are loaded, so QR generation and file uploads work
correctly in tests without polluting the repository or using the production
MEDIA_ROOT path.

To use:
- pytest: conftest.py is auto-discovered by pytest
- Django test runner: `set DJANGO_MEDIA_ROOT=<temp> && python manage.py test`
  or use the conftest approach via pytest-django
"""
import os
import tempfile
import sys


def _setup_test_media_root():
    """Set MEDIA_ROOT to a temp directory if not already set and we're testing."""
    if 'test' in sys.argv or os.environ.get('PYTEST_CURRENT_TEST'):
        if not os.environ.get('DJANGO_MEDIA_ROOT'):
            temp_media = tempfile.mkdtemp(prefix='selvi_test_media_')
            os.environ['DJANGO_MEDIA_ROOT'] = temp_media


_setup_test_media_root()
