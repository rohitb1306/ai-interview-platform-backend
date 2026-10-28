"""
Django settings for config project.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-e+m1%09_6t$-9oabtaqu+ggg_y=-*1kr%v8qso(#30*fahvxoy")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',

    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'drf_spectacular',
    'django_celery_beat',

    # Local apps
    'candidates',
    'jobs',
    'applications',
    'interviews',
    'recruiter',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}')
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static & media files

STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# DRF

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'AI Interview Platform API',
    'DESCRIPTION': 'Resume screening and dynamic AI interview platform.',
    'VERSION': '1.0.0',
}

# CORS

CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS', default=['http://localhost:3000']
)

# Frontend / Celery / Redis

FRONTEND_URL = env('FRONTEND_URL', default='http://localhost:3000')

CELERY_BROKER_URL = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# LLM provider (resume screening + interview generation/evaluation)

LLM_PROVIDER = env('LLM_PROVIDER', default='gemini')
GEMINI_API_KEY = env('GEMINI_API_KEY', default='')
# Google retires model versions; override these in .env when that happens.
GEMINI_GENERATION_MODEL = env('GEMINI_GENERATION_MODEL', default='gemini-flash-latest')
GEMINI_EMBEDDING_MODEL = env('GEMINI_EMBEDDING_MODEL', default='gemini-embedding-001')
OPENAI_API_KEY = env('OPENAI_API_KEY', default='')

MATCH_SCORE_THRESHOLD = 70.0

# Email (magic-link / rejection notices)

# Local (DEBUG) prints emails to the terminal; deployed (not DEBUG) sends via SMTP.
# Set EMAIL_BACKEND explicitly to override either way.
EMAIL_BACKEND = env(
    'EMAIL_BACKEND',
    default=(
        'django.core.mail.backends.console.EmailBackend'
        if DEBUG
        else 'django.core.mail.backends.smtp.EmailBackend'
    ),
)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@example.com')

# SMTP (only used with the smtp backend). For Gmail, the password is an App Password.
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_TIMEOUT = 10

if EMAIL_BACKEND.endswith('smtp.EmailBackend') and not (EMAIL_HOST_USER and EMAIL_HOST_PASSWORD):
    raise ImproperlyConfigured(
        'SMTP email is enabled but EMAIL_HOST_USER / EMAIL_HOST_PASSWORD are not set.'
    )
