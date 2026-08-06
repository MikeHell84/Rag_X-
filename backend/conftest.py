import os

# Ensure Django settings are loaded for pytest before any module imports that access settings.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_TESTING", "1")


def pytest_configure(config):
    from django.conf import settings

    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "ATOMIC_REQUESTS": False,
    }
    settings.DEBUG = True
