#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Shared helpers of the Rentalars server scripts (install, update, backup, restore).
#
# This file is not run on its own; the other scripts load it with "source".
#
# shellcheck shell=bash
# shellcheck disable=SC2034  # the constants are used by the scripts that load this file

# Where things live on the server. One place to look them up:
#
#   /opt/rentalars/releases/<version>-<time>/app    one installed version of the program
#   /opt/rentalars/releases/<version>-<time>/venv   and the Python libraries that belong to it
#   /opt/rentalars/app   -> the "app" folder of the version in use   (a link)
#   /opt/rentalars/venv  -> its "venv" folder                        (a link)
#   /etc/rentalars            the configuration file and certificates
#   /var/lib/rentalars        uploaded files, collected static files
#   /var/backups/rentalars    the daily backups
#
# An update installs the new version next to the old one and then moves the
# two links. Going back is moving them back (see update.sh).
readonly RENTALARS_HOME="/opt/rentalars"
readonly RELEASES_DIR="${RENTALARS_HOME}/releases"
readonly APP_DIR="${RENTALARS_HOME}/app"
readonly VENV_DIR="${RENTALARS_HOME}/venv"
# Remembers the release and the backup from before the last update, for "rollback".
readonly LAST_UPDATE_FILE="${RENTALARS_HOME}/last-update"
readonly CONFIG_DIR="/etc/rentalars"
readonly CONFIG_FILE="${RENTALARS_CONFIG:-${CONFIG_DIR}/rentalars.conf}"
readonly SERVICE_USER="rentalars"
readonly SERVICE_NAME="rentalars"

# Everything else the installer puts on the server, named once (uninstall; NFA-078): "rentalars uninstall"
# (uninstall.sh) removes exactly these places and no others, so the installer, the other scripts and the
# uninstaller must not each spell them out. tests/deploy/test_uninstall.sh checks that they do not drift.
readonly DEFAULT_DATA_DIR="/var/lib/rentalars"        # uploads, media, collected static files (the service user's home)
readonly DEFAULT_BACKUP_DIR="/var/backups/rentalars"  # the backups; [backup] directory may name another
readonly CLI_LINK="/usr/local/bin/rentalars"          # the command "rentalars" (install_cli)
readonly SYSTEMD_UNIT_DIR="/etc/systemd/system"       # rentalars*.service, rentalars*.timer (install_units)
readonly NGINX_SITE_LINK="/etc/nginx/sites-enabled/rentalars"
readonly ACME_ROOT="/var/www/rentalars-acme"          # the folder Let's Encrypt checks the domain in
readonly LETSENCRYPT_LIVE_DIR="/etc/letsencrypt/live"
readonly NGINX_LOG_PATTERN="/var/log/nginx/rentalars.*"          # deploy/nginx/rentalars.conf (access_log, error_log)
readonly MARIADB_SLOW_LOG_PATTERN="/var/log/mysql/rentalars-slow.log*"   # deploy/mariadb/60-rentalars.cnf
# Below the folders of the local AI and of the route service (ai.sh, route.sh) lies a list of the packages they installed.
readonly AI_DIR="${RENTALARS_HOME}/ai"
readonly ROUTE_DIR="${RENTALARS_HOME}/routes"
readonly INSTALLED_PACKAGES_NAME="installed-packages"

# The Ubuntu Server versions the scripts are tried on, each with its own
# packages (NFA-063):
#
#   24.04 LTS   Python 3.12, NGINX 1.24, MariaDB 10.11
#   26.04 LTS   Python 3.14, NGINX 1.28, MariaDB 11.8
#
# Older versions are refused. Other newer ones are not: the installation
# says that they are untried and goes on.
readonly TESTED_UBUNTU_VERSIONS=("24.04" "26.04")
readonly OLDEST_UBUNTU_MAJOR=24

# On a Raspberry Pi 4 or 5 (64 bit) Rentalars also runs on Raspberry Pi OS,
# which is Debian with the Pi's own additions (NFA-070). Debian 13 brings
# Python 3.13, NGINX 1.26, MariaDB 11.8 and certbot 4.0 – between the
# versions of the two Ubuntu releases, and handled by the same decisions
# (adapt_nginx_site, check_python_version). Plain Debian on any other
# computer is refused as before.
readonly TESTED_DEBIAN_VERSIONS=("13")
readonly OLDEST_DEBIAN_MAJOR=13

# Where the scripts learn about the system and the device (check_system).
readonly OS_RELEASE_FILE="/etc/os-release"
readonly DEVICE_MODEL_FILE="/proc/device-tree/model"
readonly MEMORY_INFO_FILE="/proc/meminfo"
readonly SYS_BLOCK_DIR="/sys/dev/block"

# A Raspberry Pi "with 4 GB" shows about 3.7 GB to the system; the rest
# belongs to the firmware and the graphics. Below these many MB a Pi counts
# as one with less than 4 GB, or less than 2 GB (sizing_for_memory).
readonly FOUR_GB_IN_MB=3500
readonly TWO_GB_IN_MB=1500
# MariaDB reads the files of its folder in alphabetical order; this one comes
# after 60-rentalars.cnf and overrides its memory on a small Raspberry Pi.
readonly MARIADB_MEMORY_SETTINGS="/etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf"

# The oldest Python the application runs on (the one of Ubuntu 24.04 LTS).
readonly MIN_PYTHON_MAJOR=3
readonly MIN_PYTHON_MINOR=12

readonly NGINX_SITE="/etc/nginx/sites-available/rentalars"
readonly NGINX_PROXY_SNIPPET="/etc/nginx/snippets/rentalars-proxy.conf"
readonly NGINX_REALIP_SNIPPET="/etc/nginx/snippets/rentalars-realip.conf"  # Who may name the address of a visitor
readonly MARIADB_SETTINGS="/etc/mysql/mariadb.conf.d/60-rentalars.cnf"

# Encryption (NFA-067). One secret opens everything: the recovery key. It
# encrypts the backups, and it locks the key with which the MariaDB on this
# server encrypts its files. It is shown once at the installation (or at
# "rentalars encryption enable"); on the server only root can read it.
readonly RECOVERY_KEY_FILE="${CONFIG_DIR}/recovery-key"
readonly MARIADB_KEY_DIR="/etc/mysql/rentalars-encryption"
readonly MARIADB_ENCRYPTION_SETTINGS="/etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf"
# How backups are encrypted – written out in docs/betrieb/verschluesselung.md
# for decrypting a backup by hand, with nothing but openssl.
readonly BACKUP_CIPHER=(-aes-256-cbc -pbkdf2 -iter 200000 -md sha256)

# UIX-029: the scripts speak German when the operator's locale is German – LC_ALL, else
# LC_MESSAGES, else LANG starting with "de" –, otherwise English. RENTALARS_LANG=de or =en decides
# instead (the tests set it). Every text the operator reads is written in both languages:
#
#     note "$(t "Die Sicherung ist fertig." "The backup is ready.")"
#     fail "$(t "Auf ${path} ist kein Platz." "There is no room on ${path}.")"
#
# Management commands run through "manage" learn the language from RENTALARS_LANG as well.
operator_language() {
    local locale="${RENTALARS_LANG:-${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}}"
    if [[ "${locale}" == de* ]]; then echo de; else echo en; fi
}
# The German or the English text, as the operator reads: t GERMAN ENGLISH
t() {
    if [[ "$(operator_language)" == de ]]; then printf '%s' "$1"; else printf '%s' "$2"; fi
}

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
# One line of a table: row WIDTH LABEL VALUE. Pads by characters, not bytes,
# so that labels with umlauts line up.
row()  { printf '    %s%*s %s\n' "$2" $(( $1 - ${#2} )) "" "$3"; }
note() { printf '    %s\n' "$*"; }
fail() { printf '\n\033[1;31m%s\033[0m %s\n' "$(t "Fehler:" "Error:")" "$*" >&2; exit 1; }
# Something went wrong, but not badly enough to stop.
warn() { printf '\n\033[1;33m%s\033[0m %s\n' "$(t "Achtung:" "Warning:")" "$*" >&2; }

require_root() {
    [[ "${EUID}" -eq 0 ]] || fail "$(t "Dieses Skript braucht Administratorrechte. Bitte mit sudo starten." "This script needs administrator rights. Please start it with sudo.")"
}

# Read one value from the configuration file: config_get SECTION KEY [DEFAULT]
#
# The file has the INI format that Python reads natively, so the system's own
# Python does the parsing. Nothing else has to be installed for that.
config_get() {
    local section="$1" key="$2" default="${3:-}"
    python3 - "${CONFIG_FILE}" "${section}" "${key}" "${default}" <<'PYTHON'
import configparser
import sys

path, section, key, default = sys.argv[1:5]
parser = configparser.ConfigParser(interpolation=None)
parser.read(path, encoding="utf-8")
print(parser.get(section, key, fallback=default))
PYTHON
}

# Set one value in a configuration file: config_set FILE SECTION KEY VALUE
#
# Replaces the line of the key in that section – also a commented-out one
# such as "# host =" – or adds the key at the end of the section. Comments
# and everything else in the file stay as they are.
config_set() {
    python3 - "$@" <<'PYTHON'
import re
import sys

path, section, key, value = sys.argv[1:5]
if "\n" in value or value != value.strip():
    sys.exit(f"{key}: a value must be one line without spaces at the start or end.")
with open(path, encoding="utf-8") as file:
    lines = file.read().splitlines()
start = next((i for i, line in enumerate(lines) if line.strip() == f"[{section}]"), None)
if start is None:
    lines += ["", f"[{section}]"]
    start = len(lines) - 1
end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
pattern = re.compile(rf"^#?\s*{re.escape(key)}\s*=")
new = f"{key} = {value}" if value else f"{key} ="
for i in range(start + 1, end):
    if pattern.match(lines[i]):
        lines[i] = new
        break
else:
    insert = end
    while insert > start + 1 and not lines[insert - 1].strip():
        insert -= 1
    lines.insert(insert, new)
with open(path, "w", encoding="utf-8") as file:
    file.write("\n".join(lines) + "\n")
PYTHON
}

# Run a management command of the application as the service user.
manage() {
    runuser -u "${SERVICE_USER}" -- env RENTALARS_CONFIG="${CONFIG_FILE}" RENTALARS_LANG="$(operator_language)" \
        "${VENV_DIR}/bin/python" "${APP_DIR}/manage.py" "$@"
}

# The version number of a source tree: version_of /path/to/tree
version_of() {
    sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$1/rentalars/__init__.py"
}

# NFA-077: the oldest version whose database this version can bring to its own state. The older migrations are
# squashed (rentalars/core/checks.py): an older installation or backup cannot be updated directly.
OLDEST_UPDATABLE_VERSION="0.9.0"

# The oldest updatable version a source tree names (empty for an older source tree that names none): oldest_updatable_of TREE
oldest_updatable_of() {
    sed -n 's/^OLDEST_UPDATABLE_VERSION="\(.*\)"$/\1/p' "$1/deploy/lib.sh"
}

# Succeeds if version $1 is older than version $2 (numbers like 1.0.1): version_older 1.0.0 1.1.0
version_older() {
    [[ "$1" =~ ^[0-9]+(\.[0-9]+)*$ && "$2" =~ ^[0-9]+(\.[0-9]+)*$ && "$1" != "$2" ]] \
        && [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n 1)" == "$1" ]]
}

# Fail unless the system's Python is new enough (NFA-054).
check_python_version() {
    python3 - "${MIN_PYTHON_MAJOR}" "${MIN_PYTHON_MINOR}" <<'PYTHON' || fail "$(t "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} oder neuer wird gebraucht (Ubuntu 24.04 LTS und 26.04 LTS bringen es mit, auf dem Raspberry Pi auch Raspberry Pi OS auf Basis von Debian 13)." "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} or newer is needed (Ubuntu 24.04 LTS and 26.04 LTS bring it, on the Raspberry Pi also Raspberry Pi OS based on Debian 13).")"
import sys

needed = (int(sys.argv[1]), int(sys.argv[2]))
sys.exit(0 if sys.version_info[:2] >= needed else 1)
PYTHON
}

# Succeeds if the scripts are tried on this Ubuntu version: is_tested_ubuntu 26.04
is_tested_ubuntu() {
    local version
    for version in "${TESTED_UBUNTU_VERSIONS[@]}"; do
        [[ "$1" == "${version}" ]] && return 0
    done
    return 1
}

# The tried versions as words: "24.04 LTS und 26.04 LTS" ("… and …" in English); with "oder"/"or": tested_ubuntu_versions or
tested_ubuntu_versions() {
    local text="" version joiner
    if [[ "${1:-}" == or ]]; then joiner="$(t " oder " " or ")"; else joiner="$(t " und " " and ")"; fi
    for version in "${TESTED_UBUNTU_VERSIONS[@]}"; do
        text+="${text:+${joiner}}${version} LTS"
    done
    echo "${text}"
}

# Fail unless at least the given number of megabytes is free: check_free_space /path 1024
check_free_space() {
    local path="$1" needed_mb="$2" free_mb
    free_mb="$(df --output=avail -m "${path}" | tail -n 1 | tr -d ' ')"
    [[ "${free_mb}" -ge "${needed_mb}" ]] \
        || fail "$(t "Auf ${path} sind nur ${free_mb} MB frei; gebraucht werden mindestens ${needed_mb} MB." "Only ${free_mb} MB are free on ${path}; at least ${needed_mb} MB are needed.")"
}

# --- The system and the device (NFA-063, NFA-070) ------------------------------------------
#
# Rentalars runs on Ubuntu Server – on a server with an x86-64 processor or
# on a Raspberry Pi 4 or 5 – and on a Raspberry Pi also on Raspberry Pi OS
# based on Debian 13. Everything special about the Raspberry Pi happens only
# on a Raspberry Pi: on every other computer the scripts do exactly what
# they did before. The functions take the files they read as arguments, so
# that tests can hand them made-up ones (tests/deploy/test_system.sh).

# Succeeds if the scripts are tried on this Debian version: is_tested_debian 13
is_tested_debian() {
    local version
    for version in "${TESTED_DEBIAN_VERSIONS[@]}"; do
        [[ "$1" == "${version}" ]] && return 0
    done
    return 1
}

# One value of an os-release file, without quotes: os_release_value FILE KEY
os_release_value() {
    local value
    value="$(sed -n "s/^$2=//p" "$1" 2> /dev/null | tail -n 1)"
    value="${value#\"}" && value="${value%\"}"
    value="${value#\'}" && value="${value%\'}"
    printf '%s\n' "${value}"
}

# The model of the device as its firmware names it, e.g. "Raspberry Pi 5
# Model B Rev 1.0"; nothing on a computer without a device tree, such as a
# usual x86 server: device_model FILE
device_model() {
    [[ -r "$1" ]] || return 0
    # The firmware ends the name with a zero byte.
    tr -d '\0' < "$1"
    echo
}

# Succeeds for any Raspberry Pi: is_raspberry_pi MODEL
is_raspberry_pi() {
    [[ "$1" == "Raspberry Pi"* ]]
}

# Succeeds for the models Rentalars is meant for (NFA-070): the Raspberry Pi
# 4 and 5, also as keyboard (400, 500) and as Compute Module.
is_intended_raspberry_pi() {
    local pattern='^Raspberry Pi (4|5|400|500|Compute Module (4|5))([^0-9]|$)'
    [[ "$1" =~ ${pattern} ]]
}

# The total memory in MB, 0 if unknown: memory_mb MEMINFO_FILE
memory_mb() {
    [[ -r "$1" ]] || { echo 0; return 0; }
    awk '/^MemTotal:/ { mb = int($2 / 1024) } END { print mb + 0 }' "$1"
}

# Memory as people say it, with a decimal comma in German: memory_text 3790 -> "3,7 GB" ("3.7 GB" in English)
memory_text() {
    if [[ "$(operator_language)" == de ]]; then
        awk -v mb="$1" 'BEGIN { printf "%.1f GB\n", mb / 1024 }' | tr . ,
    else
        awk -v mb="$1" 'BEGIN { printf "%.1f GB\n", mb / 1024 }'
    fi
}

# Check the operating system before anything is changed (NFA-063, NFA-070):
# check_system OS_RELEASE_FILE DEVICE_MODEL_FILE ARCHITECTURE
#
# ARCHITECTURE is that of the installed packages (dpkg --print-architecture),
# not that of the processor: a Raspberry Pi with a 64-bit processor may run a
# 32-bit system, and Rentalars needs 64 bit.
#
# Fails, with the reason, on a system Rentalars does not run on:
#   - a 32-bit system;
#   - Ubuntu older than 24.04;
#   - Debian (Raspberry Pi OS) older than 13, or Debian on a computer that
#     is not a Raspberry Pi;
#   - anything else.
# A newer version than the tried ones, or a Raspberry Pi other than 4 and 5,
# is not refused – it usually works – but noted (NFA-063). Otherwise sets
#   SYSTEM_ID             ubuntu or debian
#   SYSTEM_VERSION        e.g. 24.04 or 13
#   SYSTEM_NAME           as the system calls itself, e.g. "Ubuntu 24.04.3 LTS"
#   SYSTEM_ARCHITECTURE   e.g. amd64 or arm64
#   SYSTEM_MODEL          the model of a Raspberry Pi; empty on other computers
#   SYSTEM_NOTE           empty, or "  – nicht erprobt; …"
check_system() {
    local os_release="$1" model_file="$2" architecture="$3" id="" major model pi_hint=""
    SYSTEM_ID="" SYSTEM_VERSION="" SYSTEM_NAME="" SYSTEM_MODEL="" SYSTEM_NOTE=""
    SYSTEM_ARCHITECTURE="${architecture}"
    if [[ -r "${os_release}" ]]; then
        id="$(os_release_value "${os_release}" ID)"
        SYSTEM_VERSION="$(os_release_value "${os_release}" VERSION_ID)"
        SYSTEM_NAME="$(os_release_value "${os_release}" PRETTY_NAME)"
    fi
    model="$(device_model "${model_file}")"
    if is_raspberry_pi "${model}"; then
        SYSTEM_MODEL="${model}"
        pi_hint="$(t " Auf einem Raspberry Pi geht auch Raspberry Pi OS auf Basis von Debian 13, 64 Bit." " On a Raspberry Pi, Raspberry Pi OS based on Debian 13, 64 bit, works as well.")"
    fi

    case "${architecture}" in
        armhf|armel|i386)
            if [[ -n "${SYSTEM_MODEL}" ]]; then
                fail "$(t "Rentalars braucht ein 64-Bit-System; hier läuft eines mit 32 Bit (${architecture}). Installiere auf dem Raspberry Pi \"Raspberry Pi OS Lite (64-bit)\" oder Ubuntu Server für den Raspberry Pi (docs/betrieb/installation.md, Abschnitt Raspberry Pi)." "Rentalars needs a 64-bit system; this one runs 32 bit (${architecture}). On the Raspberry Pi, install \"Raspberry Pi OS Lite (64-bit)\" or Ubuntu Server for the Raspberry Pi (docs/en/operations/installation.md, section Raspberry Pi).")"
            fi
            fail "$(t "Rentalars braucht ein 64-Bit-System; hier läuft eines mit 32 Bit (${architecture})." "Rentalars needs a 64-bit system; this one runs 32 bit (${architecture}).")" ;;
    esac

    major="${SYSTEM_VERSION%%.*}"
    [[ "${major}" =~ ^[0-9]+$ ]] || major=0
    case "${id}" in
        ubuntu)
            SYSTEM_ID="ubuntu"
            (( major >= OLDEST_UBUNTU_MAJOR )) \
                || fail "$(t "Ubuntu ${SYSTEM_VERSION} ist zu alt. Gebraucht wird Ubuntu Server $(tested_ubuntu_versions or)." "Ubuntu ${SYSTEM_VERSION} is too old. Ubuntu Server $(tested_ubuntu_versions or) is needed.")"
            # A version between or after the tried ones is not refused – it usually
            # works – but the administrator should know (NFA-063).
            is_tested_ubuntu "${SYSTEM_VERSION}" || SYSTEM_NOTE="$(t "  – nicht erprobt; erprobt sind $(tested_ubuntu_versions)" "  – not tried; tried are $(tested_ubuntu_versions)")"
            ;;
        debian|raspbian)
            # Raspberry Pi OS calls itself "debian" (64 bit) or "raspbian" (32 bit).
            [[ -n "${SYSTEM_MODEL}" ]] \
                || fail "$(t "Dieses Skript ist für Ubuntu Server gemacht; Debian nur als Raspberry Pi OS auf einem Raspberry Pi (gefunden: ${SYSTEM_NAME:-Debian})." "This script is made for Ubuntu Server; Debian only as Raspberry Pi OS on a Raspberry Pi (found: ${SYSTEM_NAME:-Debian}).")"
            SYSTEM_ID="debian"
            if [[ -n "${SYSTEM_VERSION}" ]]; then
                (( major >= OLDEST_DEBIAN_MAJOR )) \
                    || fail "$(t "${SYSTEM_NAME:-Debian ${SYSTEM_VERSION}} ist zu alt. Gebraucht wird Raspberry Pi OS auf Basis von Debian 13 (trixie), 64 Bit – oder Ubuntu Server ab 24.04 LTS für den Raspberry Pi." "${SYSTEM_NAME:-Debian ${SYSTEM_VERSION}} is too old. Raspberry Pi OS based on Debian 13 (trixie), 64 bit, is needed – or Ubuntu Server 24.04 LTS or newer for the Raspberry Pi.")"
            fi
            # Debian "testing" has no version number; it is newer than 13.
            is_tested_debian "${major}" || SYSTEM_NOTE="$(t "  – nicht erprobt; vorgesehen ist Raspberry Pi OS auf Basis von Debian 13" "  – not tried; meant is Raspberry Pi OS based on Debian 13")"
            ;;
        *)
            fail "$(t "Dieses Skript ist für Ubuntu Server gemacht (gefunden: ${SYSTEM_NAME:-unbekannt})." "This script is made for Ubuntu Server (found: ${SYSTEM_NAME:-unknown}).")${pi_hint}" ;;
    esac
    if [[ -n "${SYSTEM_MODEL}" ]] && ! is_intended_raspberry_pi "${SYSTEM_MODEL}"; then
        SYSTEM_NOTE+="$(t "  – nicht erprobt; vorgesehen sind Raspberry Pi 4 und 5" "  – not tried; meant are the Raspberry Pi 4 and 5")"
    fi
    return 0
}

# The packages of the operating system that Rentalars needs (NFA-029), one per
# line: system_packages SYSTEM_ID LOCAL_DATABASE TLS_MODE DNS_PLUGIN
#
# SYSTEM_ID is that of check_system; LOCAL_DATABASE is "true" when MariaDB is
# set up on this server; TLS_MODE and DNS_PLUGIN are the options of
# install.sh. Debian 13 (Raspberry Pi OS) has every package under the name
# Ubuntu uses: mysqlclient is built against libmariadb-dev there as well,
# because PyPI has no ready-made package of it for any Linux, and WeasyPrint
# finds Pango and HarfBuzz under the same names. Should a future Debian
# rename one, it is swapped here.
system_packages() {
    local system_id="$1" local_database="$2" tls_mode="$3" dns_plugin="$4"
    local packages=(
        python3 python3-venv python3-dev      # the runtime, from the distribution
        build-essential pkg-config libmariadb-dev   # to build the MariaDB connector
        mariadb-client nginx                  # the client for backups, also with a database elsewhere
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0   # text layout for PDF creation
        openssl curl rsync ca-certificates
        ffmpeg                                # NFA-076: chat videos (added_packages)
    )
    case "${system_id}" in
        ubuntu|debian) ;;
        *) fail "$(t "Unbekanntes System für die Paketauswahl: ${system_id}" "Unknown system for the choice of packages: ${system_id}")" ;;
    esac
    if [[ "${local_database}" == "true" ]]; then
        packages+=(mariadb-server)
    fi
    case "${tls_mode}" in
        letsencrypt|dns) packages+=(certbot) ;;
    esac
    if [[ -n "${dns_plugin}" ]]; then
        packages+=("python3-certbot-dns-${dns_plugin}")
    fi
    printf '%s\n' "${packages[@]}"
}

# The packages of system_packages that came with a later version, one per
# line: a server installed before gets them with the update
# (install_added_packages). Each stays in system_packages as well.
added_packages() {
    printf '%s\n' ffmpeg   # NFA-076: videos in the chat are made smaller (rentalars/chat/media.py)
}

# The packages that the added_packages of another version's lib.sh names –
# of the version being installed: packages_added_by LIB. Empty for a version
# without the function.
packages_added_by() {
    bash -c 'source "$1" > /dev/null 2>&1 && declare -F added_packages > /dev/null && added_packages' _ "$1" 2> /dev/null || true
}

# Of the packages named, those not installed, one per line:
# missing_packages DPKG_QUERY PACKAGE…  (tests give another command than dpkg-query)
missing_packages() {
    local query="$1" package
    shift
    for package in "$@"; do
        # shellcheck disable=SC2016  # ${Status} is a field of dpkg-query, not of the shell
        "${query}" -W -f='${Status}' "${package}" 2> /dev/null | grep -q "install ok installed" || echo "${package}"
    done
}

# The packages of added_packages (of this version, or of the lib.sh named) that
# this server lacks, one per line: missing_added_packages [LIB]
# RENTALARS_DPKG_QUERY and RENTALARS_APT_GET replace dpkg-query and apt-get –
# only for the tests (tests/deploy/test_system.sh).
missing_added_packages() {
    local wanted
    if [[ -n "${1:-}" ]]; then
        mapfile -t wanted < <(packages_added_by "$1")
    else
        mapfile -t wanted < <(added_packages)
    fi
    (( ${#wanted[@]} > 0 )) || return 0
    missing_packages "${RENTALARS_DPKG_QUERY:-dpkg-query}" "${wanted[@]}"
}

# Install what the new version names in added_packages and this server lacks
# (NFA-029): install_added_packages [LIB_OF_THE_NEW_VERSION]. Nothing missing:
# nothing is done, apt is not called. Never fails the update: without such a
# package Rentalars runs, only what needs it is refused – videos in the chat
# without ffmpeg – and the self-check says so.
install_added_packages() {
    local missing apt="${RENTALARS_APT_GET:-apt-get}"
    mapfile -t missing < <(missing_added_packages "${1:-}")
    (( ${#missing[@]} > 0 )) || return 0
    note "$(t "Installiere fehlende Pakete: ${missing[*]}" "Installing missing packages: ${missing[*]}")"
    # Waits up to two minutes for an apt that runs at the same time (automatic security updates).
    if ! { "${apt}" -o DPkg::Lock::Timeout=120 update -qq \
        && DEBIAN_FRONTEND=noninteractive "${apt}" -o DPkg::Lock::Timeout=120 install -y -qq --no-install-recommends "${missing[@]}" > /dev/null; }; then
        warn "$(t "Die Pakete ${missing[*]} ließen sich nicht installieren; Rentalars läuft trotzdem. Videos im Chat werden abgelehnt, bis ffmpeg da ist: sudo apt install ${missing[*]}" "The packages ${missing[*]} could not be installed; Rentalars runs all the same. Videos in the chat are refused until ffmpeg is there: sudo apt install ${missing[*]}")"
    fi
    return 0
}

# The names of the block devices a folder lies on, from the partition down to
# the disks: storage_devices FOLDER [SYS_BLOCK_DIR]
#
# Found through the device number of the file system, so that it also works
# where the system mounts its root as "/dev/root", and through the layers of
# an encrypted or LVM volume. Prints nothing where it cannot tell (a network
# file system, a btrfs subvolume).
storage_devices() {
    local folder="$1" sys_block="${2:-${SYS_BLOCK_DIR}}" number
    while [[ ! -e "${folder}" && "${folder}" != "/" ]]; do
        folder="$(dirname "${folder}")"
    done
    number="$(findmnt -n -o MAJ:MIN --target "${folder}" 2> /dev/null | head -n 1 | tr -d ' ')" || true
    [[ "${number}" =~ ^[0-9]+:[0-9]+$ ]] || return 0
    block_device_names "${sys_block}/${number}"
}

# A block device of /sys and everything it is built on: block_device_names DIR
block_device_names() {
    local device lower
    [[ -e "$1" ]] || return 0
    device="$(readlink -f "$1")"
    basename "${device}"
    for lower in "${device}"/slaves/*; do
        [[ -e "${lower}" ]] && block_device_names "${lower}"
    done
    return 0
}

# Succeeds if one of the device names is an SD card – or the built-in memory
# (eMMC) of a Compute Module, which wears out alike: names_include_sd_card NAME…
names_include_sd_card() {
    local name
    for name in "$@"; do
        [[ "${name}" == mmcblk* ]] && return 0
    done
    return 1
}

# The folders of the list that lie on an SD card, one per line:
# places_on_sd_card FOLDER…
places_on_sd_card() {
    local folder devices
    for folder in "$@"; do
        mapfile -t devices < <(storage_devices "${folder}")
        if names_include_sd_card "${devices[@]}"; then
            echo "${folder}"
        fi
    done
}

# The folders of this installation that lie on an SD card, one per line: the
# database (if it is on this server), the data folder, the backups. Nothing
# on a computer that is not a Raspberry Pi (NFA-070).
installation_places_on_sd_card() {
    local places
    is_raspberry_pi "$(device_model "${DEVICE_MODEL_FILE}")" || return 0
    places=("$(config_get rentalars data_dir "${DEFAULT_DATA_DIR}")" "$(config_get backup directory "${DEFAULT_BACKUP_DIR}")")
    if database_is_local; then
        places=(/var/lib/mysql "${places[@]}")
    fi
    places_on_sd_card "${places[@]}"
}

# The settings for a Raspberry Pi with less than 4 GB (NFA-042, NFA-070):
# "WORKERS BUFFER_POOL", or nothing if the settings of the reference system
# fit – sizing_for_memory MEMORY_MB
#
# The reference system runs five worker processes of about 90 MB each and
# gives MariaDB 1 GB, a quarter of 4 GB. A Raspberry Pi 4 or 5 has four cores
# like the reference system; with 4 GB and more it gets the same. With less,
# fewer processes and less memory for MariaDB leave room for the system,
# PDF creation and the backup.
sizing_for_memory() {
    local memory="$1"
    if (( memory >= FOUR_GB_IN_MB || memory == 0 )); then
        return 0
    elif (( memory >= TWO_GB_IN_MB )); then
        echo "3 512M"
    else
        echo "2 256M"
    fi
}

# On a Raspberry Pi with little memory, fewer worker processes for the
# application: adapt_workers UNIT_FILE MODEL MEMORY_MB
#
# Called for the installed rentalars.service at every installation and update
# (install_units). Changes nothing on other computers and on a Raspberry Pi
# with 4 GB or more.
adapt_workers() {
    local unit="$1" model="$2" memory="$3" sizing workers
    is_raspberry_pi "${model}" || return 0
    sizing="$(sizing_for_memory "${memory}")"
    [[ -n "${sizing}" ]] || return 0
    workers="${sizing%% *}"
    sed -i -E "s/--workers [0-9]+/--workers ${workers}/" "${unit}"
}

# On a Raspberry Pi with little memory, less memory for the MariaDB on this
# server: write_database_memory_settings FILE MODEL MEMORY_MB
#
# Writes the file with the smaller value, or removes it when the Pi has 4 GB
# or more. Changes nothing on other computers. Takes effect at the next start
# of MariaDB.
write_database_memory_settings() {
    local file="$1" model="$2" memory="$3" sizing
    is_raspberry_pi "${model}" || return 0
    sizing="$(sizing_for_memory "${memory}")"
    if [[ -z "${sizing}" ]]; then
        rm -f "${file}"
        return 0
    fi
    cat > "${file}" <<SETTINGS
# Written by Rentalars for a Raspberry Pi with $(memory_text "${memory}") of memory
# (NFA-042, NFA-070). It overrides 60-rentalars.cnf; every update writes it
# anew, and removes it on a Raspberry Pi with 4 GB or more.
[mysqld]
innodb_buffer_pool_size = ${sizing#* }
SETTINGS
    chmod 644 "${file}"
}

# A value for a MariaDB option file, in quotes: a "#" would otherwise start a
# comment, and a password may contain anything.
option_value() {
    local value="${1//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "${value}"
}

# The connection data for the MariaDB command line tools, as a [client] file:
# write_client_file TARGET USER PASSWORD HOST PORT TLS TLS_CA
#
# Passing the password as an argument would show it to every user in the
# process list. The caller removes the file again (see "trap" in the scripts).
#
# TLS is "true" or "false". Without a CA the connection is encrypted but the
# server's certificate is not checked – the same as the application does
# (rentalars/settings.py). With a CA the certificate and the server's name
# are checked.
write_client_file() {
    local target="$1" user="$2" password="$3" host="$4" port="$5" tls="$6" tls_ca="$7"
    ( umask 077
      {
          echo "[client]"
          echo "user=$(option_value "${user}")"
          echo "password=$(option_value "${password}")"
          [[ -n "${host}" ]] && echo "host=$(option_value "${host}")"
          [[ -n "${port}" ]] && echo "port=${port}"
          if [[ "${tls}" == "true" ]]; then
              echo "ssl"
              if [[ -n "${tls_ca}" ]]; then
                  echo "ssl-ca=$(option_value "${tls_ca}")"
                  echo "ssl-verify-server-cert"
              else
                  echo "skip-ssl-verify-server-cert"
              fi
          elif [[ -n "${host}" ]] && ! is_local_host "${host}"; then
              # Explicitly without: newer clients would otherwise try TLS
              # and refuse a server whose certificate they cannot check.
              echo "skip-ssl"
          fi
          true
      } > "${target}" )
}

# Succeeds for the host names that mean "the MariaDB on this server".
is_local_host() {
    [[ -z "$1" || "$1" == "localhost" || "$1" == "127.0.0.1" || "$1" == "::1" ]]
}

# Succeeds if the configured database is the MariaDB on this server.
database_is_local() {
    is_local_host "$(config_get database host)"
}

# Whether the configured connection uses TLS: "true" or "false".
database_tls() {
    local tls tls_ca
    tls="$(config_get database tls false)"
    tls_ca="$(config_get database tls_ca)"
    if [[ -n "${tls_ca}" || "${tls,,}" =~ ^(true|yes|on|1)$ ]]; then echo true; else echo false; fi
}

# The [client] file for the database in the configuration file.
write_database_credentials() {
    write_client_file "$1" "$(config_get database user rentalars)" "$(config_get database password)" \
        "$(config_get database host)" "$(config_get database port)" "$(database_tls)" "$(config_get database tls_ca)"
}

# Succeeds if the configured database answers: database_answers
database_answers() {
    local credentials status=0
    credentials="$(mktemp)"
    write_database_credentials "${credentials}"
    mariadb --defaults-extra-file="${credentials}" --connect-timeout=10 \
        "$(config_get database name rentalars)" -e "SELECT 1" > /dev/null 2>&1 || status=$?
    rm -f "${credentials}"
    return "${status}"
}

# Check a database account with the system's Python, before anything is
# written (NFA-066): check_database_account TREE CLIENT_FILE DATABASE [options]
#
# TREE is the Rentalars source tree that brings the check along. The options
# are those of rentalars/core/database_account.py. Prints the result; the
# exit status is 0 (fit), 1 (refused) or 2 (no connection).
check_database_account() {
    local tree="$1" client_file="$2" database="$3"
    shift 3
    python3 "${tree}/rentalars/core/database_account.py" --client-file "${client_file}" --database "${database}" "$@"
}

# Install a source tree as a new release next to the existing ones and print
# its folder: build_release /path/to/source/tree
#
# Nothing that is in use is touched. If anything fails, the half-built folder
# is removed and the running installation is exactly as before.
build_release() {
    local source_tree="$1" version release
    version="$(version_of "${source_tree}")"
    [[ -n "${version}" ]] || fail "$(t "In ${source_tree} liegt kein Rentalars (rentalars/__init__.py fehlt)." "${source_tree} holds no Rentalars (rentalars/__init__.py is missing).")"
    release="${RELEASES_DIR}/${version}-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "${release}"
    # shellcheck disable=SC2064  # the folder name is meant to be fixed now
    trap "rm -rf '${release}'" ERR

    # The program: everything except what belongs to a developer's machine.
    rsync -a --delete \
        --exclude '.git' --exclude '.venv' --exclude 'var' --exclude '__pycache__' \
        --exclude '.coverage' --exclude '.mypy_cache' --exclude '.ruff_cache' --exclude 'wheels' \
        "${source_tree}/" "${release}/app/"

    # The libraries, in exactly the versions the release names (NFA-029). The
    # environment is created at its final place, because it cannot be moved.
    python3 -m venv "${release}/venv"
    local pip_options=(--disable-pip-version-check --no-input --quiet)
    if [[ -d "${source_tree}/wheels" ]]; then
        # A package that brings its libraries along installs without internet access.
        pip_options+=(--no-index --find-links "${source_tree}/wheels")
    fi
    "${release}/venv/bin/pip" install "${pip_options[@]}" -r "${release}/app/requirements.txt" >&2

    chown -R root:root "${release}"
    chmod -R go-w "${release}"
    make_scripts_executable "${release}/app"
    trap - ERR
    echo "${release}"
}

# Make a release the one in use: activate_release /opt/rentalars/releases/1.0.0-…
#
# "mv -T" replaces a link in one step, so there is no moment without a program.
activate_release() {
    local release="$1"
    ln -sfn "${release}/app" "${APP_DIR}.new" && mv -T "${APP_DIR}.new" "${APP_DIR}"
    ln -sfn "${release}/venv" "${VENV_DIR}.new" && mv -T "${VENV_DIR}.new" "${VENV_DIR}"
}

# Succeeds if the Python libraries of a release can be loaded on this system:
# release_runs /opt/rentalars/releases/1.0.0-…
#
# They cannot after Ubuntu was upgraded to a version with another Python: the
# libraries of a release are installed for the Python that was there when the
# release was built (NFA-063). Such a release can neither be started nor gone
# back to.
release_runs() {
    "$1/venv/bin/python" -c "import django" > /dev/null 2>&1
}

# The release folder that is in use, or nothing if Rentalars is not installed.
current_release() {
    [[ -L "${APP_DIR}" ]] && dirname "$(readlink -f "${APP_DIR}")"
}

# Install the service definitions of the active release and tell systemd.
#
# Units of Rentalars that the active release does not have – after going
# back to an older version, the mail timer of a newer one – are switched off
# and removed: they would start commands the program does not know.
install_units() {
    local unit name
    for unit in "${SYSTEMD_UNIT_DIR}"/rentalars*.service "${SYSTEMD_UNIT_DIR}"/rentalars*.timer; do
        [[ -e "${unit}" ]] || continue
        name="$(basename "${unit}")"
        if [[ ! -e "${APP_DIR}/deploy/systemd/${name}" ]]; then
            systemctl disable --now "${name}" > /dev/null 2>&1 || true
            rm -f "${unit}"
        fi
    done
    install -m 644 "${APP_DIR}"/deploy/systemd/*.service "${APP_DIR}"/deploy/systemd/*.timer "${SYSTEMD_UNIT_DIR}/"
    # A Raspberry Pi with little memory runs fewer worker processes (NFA-042, NFA-070).
    adapt_workers "${SYSTEMD_UNIT_DIR}/rentalars.service" "$(device_model "${DEVICE_MODEL_FILE}")" "$(memory_mb "${MEMORY_INFO_FILE}")"
    systemctl daemon-reload
}

# The timers of the active release: rentalars-backup.timer …
rentalars_timers() {
    local timer
    for timer in "${APP_DIR}"/deploy/systemd/*.timer; do
        basename "${timer}"
    done
}

# Switch on every timer of the active release – also one that came with an update.
enable_timers() {
    local timers
    mapfile -t timers < <(rentalars_timers)
    systemctl enable --quiet --now "${timers[@]}"
}

# Succeeds if the installed NGINX knows the directive "http2 on;".
#
# NGINX 1.25.1 introduced it and calls the older way – the word "http2" on the
# "listen" line – deprecated. Ubuntu 24.04 ships NGINX 1.24, which only knows
# the word; Ubuntu 26.04 ships 1.28, which warns about the word at every start.
nginx_has_http2_directive() {
    local version major minor patch
    version="$(nginx -v 2>&1 | sed -n 's|.*nginx/\([0-9][0-9.]*\).*|\1|p')"
    [[ -n "${version}" ]] || return 1
    IFS=. read -r major minor patch <<<"${version}"
    minor="${minor:-0}" patch="${patch:-0}"
    (( major > 1 || (major == 1 && (minor > 25 || (minor == 25 && patch >= 1))) ))
}

# Write HTTP/2 into an NGINX site in the way the installed NGINX understands:
# adapt_nginx_site /etc/nginx/sites-available/rentalars
#
#   NGINX 1.25.1 and newer        NGINX before that
#     listen 443 ssl;               listen 443 ssl http2;
#     http2 on;
#
# Works in both directions and changes nothing if the file already has the
# right form. Called by the installation and by every update, so that a
# server whose Ubuntu was upgraded gets the new form with the next update.
adapt_nginx_site() {
    local site="$1" adapted
    [[ -f "${site}" ]] || return 0
    adapted="$(mktemp)"
    if nginx_has_http2_directive; then
        # Take the word off the listen lines, and put the directive once after
        # the listen lines of each server that speaks TLS.
        sed -E 's/^([[:space:]]*listen[[:space:]].*[[:space:]]ssl)[[:space:]]+http2;/\1;/' "${site}" \
            | sed -E '/^[[:space:]]*http2[[:space:]]+on;/d' \
            | awk '
                /^[[:space:]]*listen[[:space:]].*[[:space:]]ssl;/ {
                    print; pending = 1; indent = $0; sub(/listen.*/, "", indent); next
                }
                pending && !/^[[:space:]]*listen[[:space:]]/ { print indent "http2 on;"; pending = 0 }
                { print }
            ' > "${adapted}"
    else
        sed -E '/^[[:space:]]*http2[[:space:]]+on;/d' "${site}" \
            | sed -E 's/^([[:space:]]*listen[[:space:]].*[[:space:]]ssl);/\1 http2;/' > "${adapted}"
    fi
    # Only write when something changed; the file keeps its owner and rights.
    cmp -s "${adapted}" "${site}" || cat "${adapted}" > "${site}"
    rm -f "${adapted}"
    ensure_realip_include "${site}"
}

# The address of a visitor behind a server that is put in front of this one (S8).
#
# Behind another proxy (a load balancer, a firewall that encrypts) every request comes from that proxy, so all visitors
# have its address: the lock after failed logins and the limit of NGINX would be one for everybody – whoever fails
# twenty logins locks all. [rentalars] trusted_proxies names the addresses of such servers (comma separated; addresses
# or networks such as 10.0.0.0/8); the realip module of NGINX then takes the address of the visitor from the header
# X-Forwarded-For – but only from a request that comes from one of them. Empty: nothing is trusted, as before.
#   write_realip_snippet TARGET PROXIES
write_realip_snippet() {
    local target="$1" proxies="$2" entry lines="" entries
    proxies="${proxies%%#*}"  # a comment after the addresses
    # Split at commas and blanks without letting the shell expand a "*" into file names.
    read -r -a entries <<< "${proxies//,/ }" || true
    for entry in "${entries[@]}"; do
        if proxy_address_valid "${entry}"; then
            lines+="set_real_ip_from ${entry};"$'\n'
        else
            note "$(t "Hinweis: ${entry} unter trusted_proxies ist keine brauchbare Adresse (oder ein Netz, das alle Adressen umfasst) und wird nicht beachtet." "Note: ${entry} under trusted_proxies is no usable address (or a network that holds all addresses) and is ignored.")" >&2
        fi
    done
    {
        echo "# Written by Rentalars (rentalars update, rentalars nginx-site) from [rentalars] trusted_proxies in ${CONFIG_FILE}."
        echo "# Changes made here are overwritten."
        if [[ -n "${lines}" ]]; then
            printf '%s' "${lines}"
            echo "real_ip_header X-Forwarded-For;"
            echo "real_ip_recursive on;"
        fi
    } > "${target}"
    chmod 644 "${target}"
}

# Whether a word is an IPv4 or IPv6 address, or a network of one, that may be trusted to name the address of a visitor:
# the prefix must not be 0 (a network of all addresses would let anybody name his address).
#   proxy_address_valid ENTRY
proxy_address_valid() {
    local entry="$1" address prefix="" group groups count=0 part
    address="${entry%%/*}"
    [[ "${entry}" == */* ]] && prefix="${entry#*/}"
    if [[ -n "${prefix}" || "${entry}" == */* ]]; then
        [[ "${prefix}" =~ ^[0-9]{1,3}$ ]] || return 1
        prefix=$((10#${prefix}))
        [[ "${prefix}" -gt 0 ]] || return 1
    fi
    if [[ "${address}" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
        [[ -z "${prefix}" || "${prefix}" -le 32 ]] || return 1
        IFS=. read -r -a groups <<< "${address}"
        for part in "${groups[@]}"; do
            [[ $((10#${part})) -le 255 ]] || return 1
        done
        return 0
    fi
    [[ "${address}" =~ ^[0-9A-Fa-f:]+$ && "${address}" == *:*:* ]] || return 1
    [[ -z "${prefix}" || "${prefix}" -le 128 ]] || return 1
    [[ "${address}" != *:::* ]] || return 1
    [[ "$(grep -o '::' <<< "${address}" | wc -l)" -le 1 ]] || return 1
    IFS=: read -r -a groups <<< "${address}"
    for group in "${groups[@]}"; do
        [[ ${#group} -le 4 ]] || return 1
        [[ -z "${group}" ]] || count=$((count + 1))
    done
    if [[ "${address}" == *::* ]]; then [[ "${count}" -le 7 ]]; else [[ "${count}" -eq 8 ]]; fi
}

# The two snippets of NGINX that Rentalars keeps: how a request goes to the application, and who may name the address
# of a visitor.
install_nginx_snippets() {
    install -m 644 "${APP_DIR}/deploy/nginx/rentalars-proxy.conf" "${NGINX_PROXY_SNIPPET}"
    write_realip_snippet "${NGINX_REALIP_SNIPPET}" "$(config_get rentalars trusted_proxies "")"
}

# Put the line that includes the snippet of the visitor's address into the site of Rentalars if it is not there: in
# front of the first certificate line, which is the server of Rentalars (sites made by older versions).
#   ensure_realip_include SITE
ensure_realip_include() {
    local site="$1" adapted
    [[ -f "${site}" ]] || return 0
    grep -q 'rentalars-realip.conf' "${site}" && return 0
    adapted="$(mktemp)"
    awk '
        !done && /^[[:space:]]*ssl_certificate[[:space:]]/ {
            indent = $0; sub(/[^[:space:]].*/, "", indent)
            print indent "include snippets/rentalars-realip.conf;"; done = 1
        }
        { print }
    ' "${site}" > "${adapted}"
    cmp -s "${adapted}" "${site}" || cat "${adapted}" > "${site}"
    rm -f "${adapted}"
}

# Write an NGINX site from a template of the package, with the placeholders
# filled in and HTTP/2 in the form the installed NGINX understands:
# render_nginx_site TEMPLATE TARGET DOMAIN CERTIFICATE PRIVATE_KEY DATA_DIR
render_nginx_site() {
    local template="$1" target="$2" domain="$3" certificate="$4" private_key="$5" data_dir="$6"
    sed -e "s|@DOMAIN@|${domain}|g" -e "s|@CERTIFICATE@|${certificate}|g" \
        -e "s|@PRIVATE_KEY@|${private_key}|g" -e "s|@DATA_DIR@|${data_dir}|g" \
        "${template}" > "${target}"
    # A server without IPv6 cannot listen on an IPv6 address; NGINX would refuse to start.
    [[ -f /proc/net/if_inet6 ]] || sed -i '/listen \[::\]/d' "${target}"
    # HTTP/2 in the way the NGINX of this Ubuntu version understands (NFA-063).
    adapt_nginx_site "${target}"
}

# Bring the files that Rentalars keeps in the configuration of NGINX and
# MariaDB up to what the active release and the installed versions of NGINX
# and MariaDB need. Called by every update (and when going back).
#
# NGINX is only reloaded if it accepts the result; otherwise the files are put
# back as they were and a note is printed. A working web server is never
# traded for a tidy one.
refresh_server_configuration() {
    local keep
    if [[ -f "${NGINX_SITE}" ]]; then
        keep="$(mktemp -d)"
        cp -p "${NGINX_SITE}" "${keep}/site"
        [[ -f "${NGINX_PROXY_SNIPPET}" ]] && cp -p "${NGINX_PROXY_SNIPPET}" "${keep}/snippet"
        [[ -f "${NGINX_REALIP_SNIPPET}" ]] && cp -p "${NGINX_REALIP_SNIPPET}" "${keep}/realip"
        install_nginx_snippets
        adapt_nginx_site "${NGINX_SITE}"
        if nginx -t -q 2> "${keep}/messages"; then
            if ! cmp -s "${keep}/site" "${NGINX_SITE}" || ! cmp -s "${keep}/snippet" "${NGINX_PROXY_SNIPPET}" 2> /dev/null \
                || ! cmp -s "${keep}/realip" "${NGINX_REALIP_SNIPPET}" 2> /dev/null; then
                if systemctl is-active --quiet nginx; then
                    systemctl reload nginx
                fi
            fi
        else
            cp -p "${keep}/site" "${NGINX_SITE}"
            [[ -f "${keep}/snippet" ]] && cp -p "${keep}/snippet" "${NGINX_PROXY_SNIPPET}"
            if [[ -f "${keep}/realip" ]]; then cp -p "${keep}/realip" "${NGINX_REALIP_SNIPPET}"; else rm -f "${NGINX_REALIP_SNIPPET}"; fi
            note "$(t "Hinweis: Die NGINX-Konfiguration wurde nicht angepasst, weil NGINX sie so nicht annimmt:" "Note: the NGINX configuration was not adapted, because NGINX does not accept it like that:")"
            note "$(head -n 3 "${keep}/messages")"
        fi
        rm -rf "${keep}"
    fi
    # MariaDB 11 calls this setting deprecated and will drop it; a server that
    # no longer knows a setting does not start. It has been the default since
    # long before MariaDB 10.11, so the line can simply go. Everything else in
    # the file – including what the administrator changed – stays.
    if [[ -f "${MARIADB_SETTINGS}" ]]; then
        sed -i -E '/^[[:space:]]*innodb_file_per_table[[:space:]]*=/d' "${MARIADB_SETTINGS}"
        # On a Raspberry Pi: the memory for MariaDB follows the memory of the
        # Pi, from its next start on (NFA-070). Nothing on other computers.
        write_database_memory_settings "${MARIADB_MEMORY_SETTINGS}" "$(device_model "${DEVICE_MODEL_FILE}")" "$(memory_mb "${MEMORY_INFO_FILE}")"
    fi
    protect_configuration "${CONFIG_FILE}"  # An installation made by an older version is converted
    install_cli
}

# Put a file in a folder that belongs to the service account, as root, without following a link (S6).
#
# The service account may lay a link at the name of the file, hoping that root writes through it (to /etc/shadow, say).
# The old file or link is removed (``rm`` does not follow), and the new file is created with O_EXCL (noclobber): a link
# that appears in between makes this fail instead of being followed. The file is created with mode 644 by the umask,
# so that there is no later change of the mode by name (``install -m`` does that, and could follow a link laid in the
# short time between). It belongs to whoever runs this (root).
#   place_file SOURCE TARGET
place_file() {
    local source="$1" target="$2"
    rm -f -- "${target}"
    (
        umask 022
        set -o noclobber
        cat -- "${source}" > "${target}"
    )
}

# The configuration file holds the database password and the secret key. NGINX (user www-data) is a member of the
# group of the service account – it needs that to reach the socket of the application and the files of "media" –, and a
# file that is readable for that group is readable for NGINX (and for whatever takes NGINX over). The file
# belongs to the service account and has no group permission: the application reads it as its owner, root reads
# everything, www-data is "other" for it and cannot.
#   protect_configuration FILE
protect_configuration() {
    local file="$1"
    [[ -f "${file}" ]] || return 0
    chown "${SERVICE_USER}:root" "${file}"
    chmod 400 "${file}"
}

# Install the command "rentalars" (NFA-069).
#
# It is a small script of its own, not a link: it runs the command of the
# active release through bash, so it is always the one that belongs to the
# installed version and works even if the files of a release lost their
# execute bit on their way to the server.
make_scripts_executable() {
    # make_scripts_executable APP_DIR – the server scripts of a version are executable,
    # whatever happened to the package on its way to the server: unpacked on another
    # computer, copied through a share (NFA-069). Also for an older installed version,
    # so that its own commands work again after going back to it.
    chmod 755 "$1/deploy/"*.sh "$1/deploy/rentalars" 2> /dev/null || true
}

install_cli() {
    local cli="${CLI_LINK}" tmp
    tmp="$(mktemp "$(dirname "${CLI_LINK}")/.rentalars.XXXXXX")"
    cat > "${tmp}" <<'CLI'
#!/bin/sh
# The command "rentalars", installed by Rentalars. It runs the command of the
# installed version: /opt/rentalars/app/deploy/rentalars (sudo rentalars help).
exec /bin/bash /opt/rentalars/app/deploy/rentalars "$@"
CLI
    chmod 755 "${tmp}"
    # "mv" replaces a link as well as a file, in one step.
    mv -f "${tmp}" "${cli}"
}

# Ask the application for its login page through the local socket; succeeds
# when it answers. Used after installation and update: "is it really up?"
application_answers() {
    local host attempt
    host="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.urlparse(sys.argv[1]).hostname or "localhost")' "$(config_get rentalars url http://localhost)")"
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        if curl --silent --fail --output /dev/null --max-time 10 \
            --unix-socket /run/rentalars/gunicorn.sock \
            -H "Host: ${host}" -H "X-Forwarded-Proto: https" "http://localhost/login/"; then
            return 0
        fi
        sleep 2
    done
    return 1
}

# --- Encryption (NFA-067) ----------------------------------------------------------------

# A new recovery key: 40 hexadecimal characters in groups of four, easy to
# write down and to type – e.g. 3f9a-1c0b-…  (160 random bits).
new_recovery_key() {
    openssl rand -hex 20 | sed 's/..../&-/g; s/-$//'
}

# The key as it is used, from whatever was typed: upper or lower case, with
# or without dashes and spaces. Fails if it cannot be a recovery key.
normalize_recovery_key() {
    local digits
    digits="$(tr -cd '0-9A-Fa-f' <<<"$1" | tr 'A-F' 'a-f')"
    [[ ${#digits} -eq 40 ]] || return 1
    sed 's/..../&-/g; s/-$//' <<<"${digits}"
}

# Succeeds if new backups are to be encrypted ([backup] encrypt = true).
backups_encrypted() {
    [[ "$(config_get backup encrypt false)" =~ ^(true|yes|on|1)$ ]]
}

# Succeeds if a file is an encrypted backup (openssl writes "Salted__" first).
is_encrypted_file() {
    [[ "$(head -c 8 "$1" 2>/dev/null)" == "Salted__" ]]
}

# Encrypt or decrypt standard input to standard output with a key file:
# encrypt_stream KEY_FILE / decrypt_stream KEY_FILE
encrypt_stream() { openssl enc -e "${BACKUP_CIPHER[@]}" -salt -pass "file:$1"; }
decrypt_stream() { openssl enc -d "${BACKUP_CIPHER[@]}" -pass "file:$1"; }

# Succeeds if the MariaDB on this server encrypts its files with the key of Rentalars.
mariadb_encryption_active() {
    [[ -f "${MARIADB_ENCRYPTION_SETTINGS}" ]] || return 1
    [[ "$(mariadb --batch --skip-column-names -e \
        "SELECT PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_NAME = 'file_key_management'" 2>/dev/null)" == "ACTIVE" ]]
}

# Give the MariaDB on this server its encryption key and settings:
# write_mariadb_encryption RECOVERY_KEY_FILE TREE
#
# TREE is the Rentalars source tree with the settings file.
#
# The key with which MariaDB encrypts is random; it is stored encrypted with
# the recovery key (the only form MariaDB's key management reads). MariaDB
# needs the recovery key at every start, so it gets its own copy, readable by
# the database server only. Takes effect at the next start of MariaDB.
#
# An existing key is never replaced: the files encrypted with it could not be
# read any more.
write_mariadb_encryption() {
    local recovery_key_file="$1" tree="$2" keys
    [[ -f "${MARIADB_KEY_DIR}/keys.enc" ]] \
        || {
            install -d -m 700 -o mysql -g mysql "${MARIADB_KEY_DIR}"
            ( umask 077
              printf '%s' "$(head -n 1 "${recovery_key_file}")" > "${MARIADB_KEY_DIR}/filekey"
              keys="$(mktemp)"
              printf '1;%s\n' "$(openssl rand -hex 32)" > "${keys}"
              # MariaDB reads only this older openssl format (key derivation with SHA-1).
              openssl enc -aes-256-cbc -md sha1 -pass "file:${MARIADB_KEY_DIR}/filekey" \
                  -in "${keys}" -out "${MARIADB_KEY_DIR}/keys.enc" 2> /dev/null
              rm -f "${keys}" )
            chown mysql:mysql "${MARIADB_KEY_DIR}/filekey" "${MARIADB_KEY_DIR}/keys.enc"
            chmod 400 "${MARIADB_KEY_DIR}/filekey" "${MARIADB_KEY_DIR}/keys.enc"
            chmod 500 "${MARIADB_KEY_DIR}"
        }
    install -m 644 "${tree}/deploy/mariadb/61-rentalars-encryption.cnf" "${MARIADB_ENCRYPTION_SETTINGS}"
}

# The recovery key of an existing MariaDB encryption, or of the configuration:
# so that a second attempt of the installation does not make a new one.
existing_recovery_key() {
    if [[ -f "${RECOVERY_KEY_FILE}" ]]; then
        head -n 1 "${RECOVERY_KEY_FILE}"
    elif [[ -f "${MARIADB_KEY_DIR}/filekey" ]]; then
        cat "${MARIADB_KEY_DIR}/filekey"
    fi
}

# Store the recovery key for root: store_recovery_key KEY
store_recovery_key() {
    install -d -m 750 -o root -g "${SERVICE_USER}" "${CONFIG_DIR}" 2> /dev/null || install -d -m 750 "${CONFIG_DIR}"
    ( umask 077; printf '%s\n' "$1" > "${RECOVERY_KEY_FILE}" )
    chown root:root "${RECOVERY_KEY_FILE}"
    chmod 400 "${RECOVERY_KEY_FILE}"
}

# Show the recovery key in a box and – at a terminal – make sure it was
# written down: present_recovery_key KEY
present_recovery_key() {
    local key="$1" answer
    note ""
    note "┌──────────────────────────────────────────────────────────────────────┐"
    if [[ "$(operator_language)" == de ]]; then
        note "│  WIEDERHERSTELLUNGSSCHLÜSSEL – jetzt aufschreiben oder ausdrucken    │"
    else
        note "│  RECOVERY KEY – write it down or print it now                        │"
    fi
    note "│                                                                      │"
    note "│      $(printf '%-62s' "${key}")  │"
    note "│                                                                      │"
    if [[ "$(operator_language)" == de ]]; then
        note "│  Er entschlüsselt die Sicherungen. Fällt dieser Server aus, sind die │"
        note "│  Sicherungen ohne ihn nicht mehr lesbar – niemand kann sie öffnen,   │"
        note "│  auch nicht die Entwickler von Rentalars. Getrennt vom Server und    │"
        note "│  sicher aufbewahren (Tresor, Passwortverwaltung der Firma).          │"
        note "│  Wieder anzeigen, solange der Server läuft:                          │"
    else
        note "│  It decrypts the backups. Should this server fail, the backups       │"
        note "│  cannot be read without it – nobody can open them, not even the      │"
        note "│  developers of Rentalars. Keep it safe and apart from the server     │"
        note "│  (a safe, the company's password manager).                           │"
        note "│  Show it again while the server runs:                                │"
    fi
    note "│      sudo rentalars encryption show-key                              │"
    note "└──────────────────────────────────────────────────────────────────────┘"
    note ""
    if [[ -t 0 ]]; then
        while true; do
            read -r -p "    $(t "Zur Bestätigung die letzten vier Zeichen des Schlüssels eingeben: " "To confirm, enter the last four characters of the key: ")" answer
            [[ "${answer,,}" == "${key: -4}" ]] && break
            note "$(t "Das passt nicht. Bitte den Schlüssel noch einmal ansehen." "That does not match. Please look at the key again.")"
        done
    fi
}

# Run a management command with another configuration file:
# manage_with_config FILE COMMAND …  (used when moving the database)
manage_with_config() {
    local config="$1"
    shift
    runuser -u "${SERVICE_USER}" -- env RENTALARS_CONFIG="${config}" RENTALARS_LANG="$(operator_language)" \
        "${VENV_DIR}/bin/python" "${APP_DIR}/manage.py" "$@"
}

# Stop the application and the timers that use the database, and start them
# again: stop_rentalars / start_rentalars
stop_rentalars() {
    local timers
    mapfile -t timers < <(rentalars_timers)
    systemctl stop "${timers[@]}" 2> /dev/null || true
    systemctl stop "${SERVICE_NAME}"
}
start_rentalars() {
    local timers
    mapfile -t timers < <(rentalars_timers)
    systemctl start "${SERVICE_NAME}"
    systemctl start "${timers[@]}" 2> /dev/null || true
}

# Compare two outputs of "manage database_fingerprint"; prints the tables
# that differ and fails if there are any: compare_fingerprints BEFORE AFTER
compare_fingerprints() {
    python3 - "$1" "$2" "$(operator_language)" <<'PYTHON'
import json
import sys

before = json.load(open(sys.argv[1], encoding="utf-8"))["tables"]
after = json.load(open(sys.argv[2], encoding="utf-8"))["tables"]
german = sys.argv[3] == "de"
different = sorted(name for name in set(before) | set(after) if before.get(name) != after.get(name))
for name in different:
    old, new = before.get(name, {}).get("rows"), after.get(name, {}).get("rows")
    if german:
        line = f"    {name}: vorher {old if old is not None else 'fehlt'} Zeilen, nachher {new if new is not None else 'fehlt'} Zeilen"
        print(line + ("" if old != new else ", aber andere Inhalte"))
    else:
        line = f"    {name}: before {old if old is not None else 'missing'} rows, after {new if new is not None else 'missing'} rows"
        print(line + ("" if old != new else ", but different contents"))
total = sum(t["rows"] for t in before.values())
print(f"    {len(before)} Tabellen, {total} Zeilen verglichen." if german else f"    {len(before)} tables, {total} rows compared.")
sys.exit(1 if different else 0)
PYTHON
}
