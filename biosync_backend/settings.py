"""
Django settings for biosync_backend project.
"""

from pathlib import Path
import os
import dj_database_url

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-change-me-to-a-real-secret-key')

# SECURITY WARNING: don't run with debug turned on in production!
# This sets Debug to False if running on Render, True if on your laptop
DEBUG = True

# ALLOWED_HOSTS is required for the cloud. '*' allows your Render URL to work.
ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Add your apps here if you create them later
    'rest_framework',
    'corsheaders',
    'app', 
    'store',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # <--- CRITICAL: Serves static files on Render
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',      # <--- CRITICAL: Allows Flutter to connect
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'biosync_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'biosync_backend.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    'default': dj_database_url.config(
        # Use SQLite locally, but use Render's DATABASE_URL automatically in production
        default='sqlite:///db.sqlite3',
        conn_max_age=600
    )
}


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = 'static/'

# This is the specific line that caused your error. It tells Django where to put files.
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# This enables WhiteNoise to actually serve those files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ========================================================
#  CRITICAL SECURITY SETTINGS FOR MOBILE APPS (FLUTTER)
# ========================================================

# 1. CORS: Allow the mobile app to talk to the server
CORS_ALLOW_ALL_ORIGINS = True  
# If you want to be stricter later, you can use: CORS_ALLOWED_ORIGINS = ["https://..."]

# 2. CSRF: Trust requests coming from your HTTPS Render URL
# This fixes the "Origin checking failed" error on HTTPS
CSRF_TRUSTED_ORIGINS = [
    "https://nutrichoice-xvpf.onrender.com",
]

# 3. COOKIES: Ensure cookies work over HTTPS
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True