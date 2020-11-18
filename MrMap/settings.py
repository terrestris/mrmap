"""
Django settings for MrMap project.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

# Include other settings files (DO NOT TOUCH THESE!)
from MrMap.sub_settings.django_settings import *
from MrMap.sub_settings.dev_settings import *
from MrMap.sub_settings.db_settings import *
from MrMap.sub_settings.logging_settings import *
from api.settings import REST_FRAMEWORK
from django.utils.translation import gettext_lazy as _


ALLOWED_HOSTS = [
    HOST_NAME,
    "127.0.0.1",
]

# GIT repo links
GIT_REPO_URI = "https://git.osgeo.org/gitea/GDI-RP/MrMap/src/branch/pre_master"
GIT_GRAPH_URI = "https://git.osgeo.org/gitea/GDI-RP/MrMap/graph"

# Defines the semantic web information which will be injected on the resource html views
SEMANTIC_WEB_HTML_INFORMATION = {
    "legalName": "Zentrale Stelle GDI-RP",
    "email": "kontakt@geoportal.rlp.de",
    "addressCountry": "DE",
    "streetAddress": "Von-Kuhl-Straße 49",
    "addressRegion": "RLP",
    "postalCode": "56070",
    "addressLocality": "Koblenz",
}

# Defines the timespan for fetching the last activities on dashboard
LAST_ACTIVITY_DATE_RANGE = 7

# configure your proxy like "http://10.0.0.1:8080"
# or with username and password: "http://username:password@10.0.0.1:8080"
HTTP_PROXY = ""
PROXIES = {
    "http": HTTP_PROXY,
    "https": HTTP_PROXY,
}

ALLOWED_HOSTS = [
    HOST_NAME,
    "127.0.0.1",
]

# Application definition
INSTALLED_APPS = [
    'MrMap',  # added so we can use general commands in MrMap/management/commands
    'dal',
    'dal_select2',
    'django.forms',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'django.contrib.gis',
    'formtools',
    'service',
    'users',
    'structure',
    'django_extensions',
    'editor',
    'captcha',
    'rest_framework',
    'rest_framework.authtoken',
    'api',
    'csw',
    'atom',
    'django_celery_beat',
    'monitoring',
    'bootstrap4',
    'fontawesome_5',
    'django_tables2',
    'django_filters',
    'query_parameters',
    'django_nose',
    'mathfilters',
]
if DEBUG:
    INSTALLED_APPS.append(
        'debug_toolbar',
    )
    # Disable all panels by default
    DEBUG_TOOLBAR_CONFIG = {
        "DISABLE_PANELS": {
            'debug_toolbar.panels.versions.VersionsPanel',
            'debug_toolbar.panels.timer.TimerPanel',
            'debug_toolbar.panels.settings.SettingsPanel',
            'debug_toolbar.panels.headers.HeadersPanel',
            'debug_toolbar.panels.request.RequestPanel',
            'debug_toolbar.panels.sql.SQLPanel',
            'debug_toolbar.panels.staticfiles.StaticFilesPanel',
            'debug_toolbar.panels.templates.TemplatesPanel',
            'debug_toolbar.panels.cache.CachePanel',
            'debug_toolbar.panels.signals.SignalsPanel',
            'debug_toolbar.panels.logging.LoggingPanel',
            'debug_toolbar.panels.redirects.RedirectsPanel',
            'debug_toolbar.panels.profiling.ProfilingPanel',
        }
    }

# Holds all apps which needs migrations. Will be used in command 'dev_makemigrations'
# If you added a new app with models, which need to be migrated, you have to put the app's name in this list
MIGRATABLE_APPS = [
    'csw',
    'structure',
    'service',
    'users',
    'monitoring',
]

TEMPLATE_LOADERS = (
    'django.template.loaders.structure.mr_map_filters.py',
)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.RemoteUserMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dealer.contrib.django.Middleware',
]

# Password hashes
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]

ROOT_URLCONF = 'MrMap.urls'

FORM_RENDERER = 'django.forms.renderers.TemplatesSetting'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR + "/templates",
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dealer.contrib.django.context_processor',
            ],
        },
    },
]

WSGI_APPLICATION = 'MrMap.wsgi.application'

# Database
# https://docs.djangoproject.com/en/2.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': 'MrMap',
        'USER': 'postgres',
        'HOST': '127.0.0.1',
        'PORT': '5432',
    }
}

# Cache
# Use local redis installation as cache
# The "regular" redis cache will be set to work in redis table 1 (see LOCATION)
# The default table (0) is preserved for celery task management
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://localhost:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
        }
    }
}

# Session settings and password validation
# https://docs.djangoproject.com/en/2.1/ref/settings/#auth-password-validators

MIN_PASSWORD_LENGTH = 9
MIN_USERNAME_LENGTH = 5  # ToDo: For production use another, more appropriate length!

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            "min_length": MIN_PASSWORD_LENGTH,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]
AUTH_USER_MODEL = 'structure.MrMapUser'
SESSION_COOKIE_AGE = 30 * 60  # Defines how many seconds can pass until the session expires, default is 30 * 60
SESSION_SAVE_EVERY_REQUEST = True  # Whether the session age will be refreshed on every request or only if data has been modified
LOGIN_URL = "/"  # Defines where to redirect a user, that has to be logged in for a certain route

# Internationalization
# https://docs.djangoproject.com/en/2.1/topics/i18n/

LANGUAGE_CODE = 'en'
LANGUAGES = (
    ('en', _('English')),
    ('de', _('German')),
)

LOCALE_PATHS = (
    os.path.join(BASE_DIR, 'locale'),
)

DEFAULT_DATE_TIME_FORMAT = 'YYYY-MM-DD hh:mm:ss'

TIME_ZONE = 'Europe/Berlin'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# CELERY SETTINGS
BROKER_URL = 'redis://localhost:6379'
CELERY_RESULT_BACKEND = 'redis://localhost:6379'
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

# API
from api.settings import REST_FRAMEWORK

RESPONSE_CACHE_TIME = 60 * 30  # 30 minutes

# Tests
if 'test' in sys.argv:
    CAPTCHA_TEST_MODE = True

TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
NOSE_ARGS = [
    '--with-xunit',
    '--xunit-file=tests/nosetests.xml',
    '--with-coverage',
    '--cover-erase',
    '--cover-xml',
    '--cover-xml-file=nosecover.xml',
]

# Progress bar
PROGRESS_STATUS_AFTER_PARSING = 90  # indicates at how much % status we are after the parsing

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.1/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR + "/static/"
STATICFILES_DIRS = [
    BASE_DIR + '/MrMap/static',
]

# define the message tags for bootstrap4
MESSAGE_TAGS = {
    messages.DEBUG: 'alert-info',
    messages.INFO: 'alert-info',
    messages.SUCCESS: 'alert-success',
    messages.WARNING: 'alert-warning',
    messages.ERROR: 'alert-danger',
}

MONITORING_TIME = "23:59:00"
MONITORING_REQUEST_TIMEOUT = 30  # seconds

# DJANGO DEBUG TOOLBAR
# Add the IP for which the toolbar should be shown
INTERNAL_IPS = [
    "127.0.0.1"
]

# DEALER Settings
DEALER_PATH = BASE_DIR

# django logging settings
import logging

root_logger = logging.getLogger('MrMap.root')

LOG_DIR = BASE_DIR + '/logs'
LOG_SUB_DIRS = {
    'root': {'dir': '/root', 'log_file': 'root.log'},
    'api': {'dir': '/api', 'log_file': 'api.log'},
    'csw': {'dir': '/csw', 'log_file': 'csw.log'},
    'editor': {'dir': '/editor', 'log_file': 'rooeditorog'},
    'monitoring': {'dir': '/monitoring', 'log_file': 'monitoring.log'},
    'service': {'dir': '/service', 'log_file': 'service.log'},
    'structure': {'dir': '/structure', 'log_file': 'structure.log'},
    'users': {'dir': '/users', 'log_file': 'users.log'},
}
LOG_FILE_MAX_SIZE = 1024 * 1024 * 20  # 20 MB
LOG_FILE_BACKUP_COUNT = 5

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'MrMap.root.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['root']['dir'] + '/' + LOG_SUB_DIRS['root']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.api.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['api']['dir'] + '/' + LOG_SUB_DIRS['api']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.csw.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['csw']['dir'] + '/' + LOG_SUB_DIRS['csw']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.editor.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['editor']['dir'] + '/' + LOG_SUB_DIRS['editor']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.monitoring.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['monitoring']['dir'] + '/' + LOG_SUB_DIRS['monitoring']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.service.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['service']['dir'] + '/' + LOG_SUB_DIRS['service']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.structure.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['structure']['dir'] + '/' + LOG_SUB_DIRS['structure']['log_file'],
            'formatter': 'verbose',
        },
        'MrMap.users.file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'maxBytes': LOG_FILE_MAX_SIZE,
            'backupCount': LOG_FILE_BACKUP_COUNT,
            'filename': LOG_DIR + LOG_SUB_DIRS['users']['dir'] + '/' + LOG_SUB_DIRS['users']['log_file'],
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'MrMap.root': {
            'handlers': ['MrMap.root.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.api': {
            'handlers': ['MrMap.api.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.csw': {
            'handlers': ['MrMap.csw.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.editor': {
            'handlers': ['MrMap.editor.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.monitoring': {
            'handlers': ['MrMap.monitoring.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.service': {
            'handlers': ['MrMap.service.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.structure': {
            'handlers': ['MrMap.structure.file', ],
            'level': 'INFO',
            'propagate': True,
        },
        'MrMap.users': {
            'handlers': ['MrMap.users.file', ],
            'level': 'INFO',
            'propagate': True,
        },
    },
}