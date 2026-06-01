import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# AI 엔진(fastapi_app/ai_engine)은 top-level 패키지(common·gas·power)로 import되므로
# 해당 디렉토리를 sys.path에 등록한다. (STEP F — Isolation Forest 통합)
_AI_ENGINE_DIR = BASE_DIR / 'fastapi_app' / 'ai_engine'
if _AI_ENGINE_DIR.is_dir() and str(_AI_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_ENGINE_DIR))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']


# Application definition

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
     # third-party
    'django_prometheus',
    'django_filters',
    'rest_framework',
    # local apps
    'core',
    'accounts',
    'facilities',
    'monitoring',
    'alerts',
    'dashboard',
    'safety',
    'manager',
    #websocket
    'channels',
]

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 20,
}

MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')
CELERY_TIMEZONE = 'Asia/Seoul'
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# STEP G(예측)는 상태기(PredictionSubsystem)라 전용 큐 + 단일 동시성 worker로
# 처리한다. forecast_gas_task + forecast_power_task가 forecast 큐로 라우팅
# (아키텍처 D2). Phase D 결정 (i): 기존 celery-forecast 컨테이너 공유.
CELERY_TASK_ROUTES = {
    'alerts.tasks.forecast_gas_task':   {'queue': 'forecast'},
    'alerts.tasks.forecast_power_task': {'queue': 'forecast'},   # Phase D M1-8
    # facilities 이벤트 subscriber는 전용 큐 + 단일 worker로 격리해
    # 다중 subscriber 중복 dispatch를 인프라 레벨에서 차단한다.
    'facilities.tasks.consume_facilities_events': {'queue': 'events'},
}

from celery.schedules import crontab  # noqa: E402

# 7. MISSING 장비 감지 — 매 60초 주기 실행
# 8. facilities 이벤트 구독 — 매 25초 주기
# 9. 데이터 보관 주기 — 매일 새벽 3시 (dev 머지)
CELERY_BEAT_SCHEDULE = {
    'check-missing-devices': {
        'task': 'alerts.tasks.check_missing_devices',
        'schedule': 60.0,
    },
    'consume-facilities-events': {
        'task': 'facilities.tasks.consume_facilities_events',
        'schedule': 30.0,
    },
    'data-retention-daily': {
        'task': 'alerts.tasks.run_data_retention',
        'schedule': crontab(hour=3, minute=0),
    },
}

# Phase 2 — AI 예측(STEP G) 튜닝 파라미터. 검증·운영 중 무재학습 조정용.
FORECAST_K_CONFIRM = int(os.environ.get('FORECAST_K_CONFIRM', '18'))


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': f"redis://{os.environ.get('REDIS_HOST', '127.0.0.1')}:6379/2",
    }
}

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [(os.environ.get('REDIS_HOST', 'redis'), 6379)],
        },
    },
}

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
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

LANGUAGE_CODE = 'ko-kr'

TIME_ZONE = 'Asia/Seoul'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 절대경로 방식을 사용하기 위해 상대 경로는 주석 처리 해두었음 
# STATIC_URL = 'static/'
# STATICFILES_DIRS = [BASE_DIR / 'static']


AUTH_USER_MODEL = 'accounts.User'

# LOGOUT_REDIRECT_URL = '/accounts/login/'

STATIC_ROOT = BASE_DIR / 'staticfiles'