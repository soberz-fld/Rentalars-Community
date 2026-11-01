# SPDX-License-Identifier: GPL-3.0-or-later
"""Django settings, derived from the configuration file (see ``config.py``).

Nothing in this file has to be edited for an installation. Operators change
``/etc/rentalars/rentalars.conf``; everything else follows from it or has a
sensible default (NFA-032).
"""

from __future__ import annotations

import sys
from pathlib import Path

from rentalars import __version__
from rentalars.config import SOURCE_DIR, load_config
from rentalars.core.hosts import AllowedHosts

CONFIG = load_config()

BASE_DIR: Path = SOURCE_DIR
RENTALARS_VERSION = __version__
RENTALARS_ENVIRONMENT = CONFIG.environment
RENTALARS_URL = CONFIG.url
RENTALARS_IS_PRODUCTION = CONFIG.is_production
#: The configuration file that was read; ``None`` in development without one.
RENTALARS_CONFIG_PATH = CONFIG.source
#: UIX-034: where map pictures and positions come from (``[maps]`` of the configuration file).
RENTALARS_MAPS = CONFIG.maps
DATA_DIR: Path = CONFIG.data_dir

SECRET_KEY = CONFIG.secret_key
DEBUG = CONFIG.debug
#: Whether the first-run setup may be opened without the one-time token
#: (NFA-064). Only on a developer's machine; on a server – and in the test
#: environment – a missing token means "closed", never "open to everybody".
SETUP_OPEN_WITHOUT_TOKEN = CONFIG.environment == "development"


# The application answers only for its own address. "localhost" stays allowed
# so that health checks and the development server work. ``allowed_hosts`` of the configuration adds
# more, and ``rentalars.core.hosts.AllowedHosts`` the addresses of this server itself.
_FIXED_HOSTS = sorted({CONFIG.host_name, "localhost", "127.0.0.1", *CONFIG.allowed_hosts})
ALLOWED_HOSTS = AllowedHosts(_FIXED_HOSTS)
RENTALARS_FIXED_HOSTS = tuple(_FIXED_HOSTS)
#: Whether a host name that is an address of this very server is answered to without an entry.
RENTALARS_ALLOW_OWN_ADDRESSES = CONFIG.allow_own_addresses
CSRF_TRUSTED_ORIGINS = [CONFIG.url] if CONFIG.url.startswith("http") else []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "rentalars.core",
    "rentalars.accounts",
    "rentalars.masterdata",
    "rentalars.products",
    "rentalars.material",
    "rentalars.customers",
    "rentalars.personnel",
    "rentalars.projects",
    "rentalars.timetracking",
    "rentalars.availability",
    "rentalars.packing",
    "rentalars.documents",
    "rentalars.notifications",
    "rentalars.mail",
    "rentalars.schedule",
    "rentalars.api",
    "rentalars.chat",  # UIX-010
    "rentalars.automations",  # ADM-013
    "rentalars.ai",  # EML-040, EML-044, ADM-017
    "rentalars.customfields",  # MAT-071, MAT-072, MAT-073: custom fields of material items
    "rentalars.incoming",  # Incoming invoices in Buchhaltung
    "rentalars.gateway_link",  # The server's side of the Rentalars Gateway (protocol RGW1)
]

MIDDLEWARE = [
    # Before anything asks for the host – a request to an address of this server itself is allowed.
    "rentalars.core.hosts.OwnAddressHostMiddleware",
    "rentalars.core.middleware.RequestCacheMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "rentalars.core.middleware.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # UIX-029: the language of the user, on pages without login the browser's.
    "rentalars.core.i18n.LanguageMiddleware",
    # Before the session timeout, which leaves a message for the login page.
    "django.contrib.messages.middleware.MessageMiddleware",
    "rentalars.accounts.sessions.SessionActivityMiddleware",
    "rentalars.core.middleware.CurrentActorMiddleware",
    "rentalars.core.middleware.SetupRequiredMiddleware",
    "rentalars.core.middleware.LoginRequiredMiddleware",
    "rentalars.accounts.twofactor.PasswordChangeRequiredMiddleware",
    "rentalars.accounts.twofactor.TwoFactorRequiredMiddleware",
    # ADM-012, ADM-014: /projects/P-2026-0042/ (a former number) leads to /projects/2026-0042/.
    "rentalars.core.middleware.FormerNumberRedirectMiddleware",
    "rentalars.core.trail.TrailMiddleware",
    # DOK-055: the pages and the API of bookkeeping are refused while Rentalars is not the accounting program.
    "rentalars.documents.bookkeeping.BookkeepingMiddleware",
    # AUT-028: who read which record – after the view answered, from the address it had.
    "rentalars.core.access_log.AccessLogMiddleware",
    "rentalars.core.listing.PageSizeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # API-010: Idempotency-Key, ETag and If-Match for the API. Last, so that a
    # check of If-Match can ask the view directly for the current state.
    "rentalars.api.safeguards.ApiSafeguardMiddleware",
]

ROOT_URLCONF = "rentalars.urls"
WSGI_APPLICATION = "rentalars.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "rentalars.core.context_processors.application",
            ],
            # UIX-029: the filters "date" and "time" write German patterns the British way while English is active.
            "builtins": ["rentalars.core.templatetags.local_dates"],
        },
    },
]


# --- Database (NFA-001, NFA-002) -------------------------------------------

if CONFIG.database.engine == "mariadb":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": CONFIG.database.name,
            "USER": CONFIG.database.user,
            "PASSWORD": CONFIG.database.password,
            "HOST": CONFIG.database.host,
            "PORT": CONFIG.database.port,
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                # utf8mb4 stores every Unicode character, including emoji in notes.
                "charset": "utf8mb4",
                # Strict mode turns silent truncation into errors. A row lock
                # that is not released in time gives an error instead of an
                # endless wait – set here, so that a database on another
                # server behaves like the one the installation sets up.
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES', innodb_lock_wait_timeout=20",
                # VFG-007 relies on this level: after waiting for a row lock,
                # a transaction must see what the other transaction committed.
                "isolation_level": "read committed",
            },
            "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
        }
    }
    # A database on another server: the connection can be encrypted, and the
    # server's certificate checked against a CA – its name included (NFA-066).
    if CONFIG.database.tls:
        _options = DATABASES["default"]["OPTIONS"]
        if CONFIG.database.tls_ca:
            _options["ssl"] = {"ca": CONFIG.database.tls_ca}
            _options["ssl_mode"] = "VERIFY_IDENTITY"
        else:
            _options["ssl_mode"] = "REQUIRED"
else:
    Path(CONFIG.database.name).parent.mkdir(parents=True, exist_ok=True)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": CONFIG.database.name,
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Users and passwords (AUT-002, AUT-003) ---------------------------------

AUTH_USER_MODEL = "accounts.User"
# AUT-029: the second backend asks the directory (LDAP / Active Directory) when it is switched on.
AUTHENTICATION_BACKENDS = [
    "rentalars.accounts.backends.EmailOrUsernameBackend",
    "rentalars.accounts.ldap_backend.LdapBackend",
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# The test suite creates hundreds of users. Hashing every password with the
# slow production algorithm would only make the tests slow, not better.
RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == "test"
if RUNNING_TESTS:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

#: NFA-041: tasks in the background run in a process of their own on a server.
#: In tests they run at once, so that a test sees the result.
JOBS_RUN_INLINE = RUNNING_TESTS

# Adds the check that every API operation is called by a test (API-014).
TEST_RUNNER = "rentalars.testing.RentalarsTestRunner"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "rentalars.accounts.password_policy.ConfiguredMinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# How long links for "reset password" and invitations stay valid (AUT-004).
PASSWORD_RESET_TIMEOUT = CONFIG.password_reset_hours * 60 * 60

SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"


# --- Language, time, money (NFA-003, NFA-026) -------------------------------

LANGUAGE_CODE = CONFIG.language
LANGUAGES = [("de", "Deutsch"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
# UIX-029: English is British (16/10/2026, 24-hour clock); German keeps Django's formats.
FORMAT_MODULE_PATH = ["rentalars.core.formats"]
USE_TZ = True  # timestamps are stored in UTC and shown in local time
TIME_ZONE = CONFIG.time_zone
# Numbers in templates are written without a thousands separator unless a
# filter asks for one ("money", "thousands"). With the automatic separator a
# record ID such as 1234 would be written as "1.234" wherever a template
# puts it into a hidden field, an option or an attribute – and every form
# that sends it back would fail from the thousandth record on.
USE_THOUSAND_SEPARATOR = False


# --- Files -------------------------------------------------------------------

STATIC_URL = "/static/"
# Addresses of static files carry a fingerprint of their content, so that
# browsers do not go on using an old style sheet after an update (NFA-065).
STORAGES = {
    "default": {"BACKEND": "rentalars.core.files.KeepDeletedStorage"},  # A deleted file stays a week in media/.deleted
    "staticfiles": {"BACKEND": "rentalars.core.staticfiles.VersionedStaticFilesStorage"},
}
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = DATA_DIR / "static"

# Uploaded files are never served directly. A view checks the rights first and
# then either streams the file or lets NGINX deliver it (NFA-007).
MEDIA_ROOT = DATA_DIR / "media"
MEDIA_URL = "/media/"
SERVE_MEDIA_VIA_NGINX = CONFIG.serve_media_via_nginx

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
# A packlist or a planning page of a large project posts thousands of fields.
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000

#: Upper limits for uploads, checked by ``rentalars.core.uploads``.
MAX_IMAGE_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_IMPORT_UPLOAD_BYTES = 25 * 1024 * 1024
#: Rows of a material list the browser and the API import in one request.
#: The application server ends a request after two minutes (deploy/systemd);
#: 20,000 rows took 2:18 minutes on two cores, 5,000 take about half a
#: minute. Longer lists go through the command on the server (IMP-007).
MAX_IMPORT_ROWS_PER_REQUEST = 5000


# --- E-mail --------------------------------------------------------------------

if CONFIG.email.host:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = CONFIG.email.host
    EMAIL_PORT = CONFIG.email.port
    EMAIL_HOST_USER = CONFIG.email.user
    EMAIL_HOST_PASSWORD = CONFIG.email.password
    EMAIL_USE_TLS = CONFIG.email.use_tls and not CONFIG.email.use_ssl
    EMAIL_USE_SSL = CONFIG.email.use_ssl
    EMAIL_TIMEOUT = 20
else:
    # Without a mail server the messages appear in the log, so that an
    # administrator can still copy an invitation link from there.
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# EML-039: every system mail (invitation, password link, notification) is noted in the mail log.
# The backend chosen above still does the sending; the logging backend only wraps it.
EMAIL_INNER_BACKEND = EMAIL_BACKEND
EMAIL_BACKEND = "rentalars.mail.backends.LoggingEmailBackend"
DEFAULT_FROM_EMAIL = CONFIG.email.from_address
SERVER_EMAIL = CONFIG.email.from_address


# --- Security for operation on the internet (NFA-005, NFA-006, NFA-048) ----

# mysql.W003 warns that a unique CharField longer than 255 characters may not fit an index. It does here:
# LdapGroupMapping.group_key is 500 characters of utf8mb4 = 2000 bytes, within the 3072 bytes that InnoDB
# (ROW_FORMAT=DYNAMIC, the default of MariaDB 10.2+) allows, and the group itself is limited to 480 (review R4).
SILENCED_SYSTEM_CHECKS = ["mysql.W003"]

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

if CONFIG.is_production and CONFIG.uses_https:
    # NGINX terminates HTTPS and tells the application through this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

#: NFA-073: a production server with an http:// address starts only with ``allow_http = yes``
#: (``config.load_config`` refuses it otherwise); the self-check names the state.
RENTALARS_ALLOW_HTTP = CONFIG.allow_http

#: NFA-071: internal networks, addresses and host names that calendars, webhooks and mail servers
#: entered in the interface may reach (``[network] allow_internal``; ``core.network``). The test
#: suite starts its calendar and webhook receivers on this machine; tests of the guard override this.
RENTALARS_NETWORK_ALLOW_INTERNAL = CONFIG.network.allow_internal or (("127.0.0.0/8", "::1") if RUNNING_TESTS else ())


# --- API (API-003 to API-008) ------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rentalars.accounts.authentication.ApiTokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rentalars.api.permissions.ModulePermission"],
    "DEFAULT_PAGINATION_CLASS": "rentalars.api.pagination.StandardPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rentalars.api.renderers.RentalarsJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "rentalars.api.errors.exception_handler",
    # API-011: calls per token and minute, as set in the administration.
    "DEFAULT_THROTTLE_CLASSES": ["rentalars.api.safeguards.TokenRateThrottle"],
    "DEFAULT_SCHEMA_CLASS": "rentalars.api.schema.RentalarsAutoSchema",
    "COERCE_DECIMAL_TO_STRING": True,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Rentalars API",
    "DESCRIPTION": (
        "Every business function of Rentalars is available through this API "
        "(API-001). Authenticate with a personal token: "
        "`Authorization: Bearer rl_…`."
    ),
    "VERSION": "1",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    # The documentation page loads its scripts from this server, never from a
    # content delivery network (NFA-050). For the same reason the "validator"
    # badge is switched off – it would send the address of this server to
    # swagger.io – and the second viewer the library offers (ReDoc) is not
    # used: it fetches fonts and a logo from other servers.
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "validatorUrl": None,
        "filter": True,  # a field to narrow the list down by tag (API-004: searchable)
        "docExpansion": "list",
    },
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAuthenticated"],
    # Several fields are called "status" or "kind"; give each set of values
    # its own name in the generated description.
    "ENUM_NAME_OVERRIDES": {
        "LanguageEnum": "rentalars.core.i18n.LANGUAGE_CHOICES",  # UIX-029
        "ItemStatusEnum": "rentalars.material.models.ItemStatus",
        "IncomingInvoiceStatusEnum": "rentalars.incoming.models.InvoiceStatus",
        "ProjectStatusEnum": "rentalars.projects.models.ProjectStatus",
        "CaseStatusEnum": "rentalars.projects.models.CaseStatus",  # bulk actions
        "WaitingForEnum": "rentalars.projects.models.CaseWaitingFor",
        "PacklistStatusEnum": "rentalars.packing.models.PacklistStatus",
        "SubrentalStatusEnum": "rentalars.projects.models.SubrentalStatus",
        "ProductKindEnum": "rentalars.products.models.ProductKind",
        "GroupKindEnum": "rentalars.projects.models.GroupKind",
        "MailSecurityEnum": "rentalars.mail.models.Security",
        "MaterialFileKindEnum": "rentalars.material.models.MaterialFileKind",
        "DocumentKindEnum": "rentalars.documents.models.DocumentKind",
        "MakeableDocumentKindEnum": "rentalars.documents.api.MAKEABLE_KINDS",
        "AvailabilitySourceEnum": "rentalars.personnel.models.AvailabilitySource",
        # ADM-013
        "AutomationActionEnum": "rentalars.automations.models.Action",
        "AutomationRunStatusEnum": "rentalars.automations.models.RunStatus",
        # PER-009: the federal state whose holidays count for the surcharges.
        "FederalStateEnum": "rentalars.core.holidays.STATE_CHOICES_OF_THE_API",
        # PER-040: the kinds of surcharge rules and of own holidays.
        "SurchargeRuleKindEnum": "rentalars.core.models.TimeSurchargeRuleKind",
        "OwnHolidayKindEnum": "rentalars.core.models.OwnHolidayKind",
        # The availability of people keeps the name it had before another field "state" came (PER-021).
        "StateEnum": "rentalars.personnel.models.AvailabilityState",
        # MAT-069: the result of an inspection keeps its name next to the result of an audit.
        "ResultEnum": "rentalars.material.models.InspectionResult",
        "AuditResultEnum": "rentalars.material.audit_models.AuditResult",
        # MAT-077: one name for the protection class of models, items and inspections.
        "ProtectionClassEnum": "rentalars.material.models.ProtectionClass",
    },
}


# --- Logging -----------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        # ADM-016: Django logs an unknown host name as an ERROR with a traceback; it is a hint.
        "host_hint": {"()": "rentalars.core.hosts.DisallowedHostHint"},
    },
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        # systemd collects standard error of the service in the journal.
        "console": {"class": "logging.StreamHandler", "formatter": "plain"},
        # NFA-018: errors are also counted in the database and reported to the operators.
        "operators": {"class": "rentalars.core.errors.OperatorHandler", "level": "ERROR"},
    },
    "root": {"handlers": ["console", "operators"], "level": "INFO"},
    "loggers": {
        "django.request": {"handlers": ["console", "operators"], "level": "ERROR", "propagate": False},
        # A request to a host name the application does not answer to is a hint for the operator (the page says
        # what to do), not an error to report: a scanner that tries addresses would otherwise raise the alarm.
        "django.security.DisallowedHost": {
            "handlers": ["console"],
            "filters": ["host_hint"],
            "level": "WARNING",
            "propagate": False,
        },
        "rentalars": {"handlers": ["console", "operators"], "level": "INFO", "propagate": False},
        # The PDF library reports every embedded font; only problems matter.
        "fontTools": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "weasyprint": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
