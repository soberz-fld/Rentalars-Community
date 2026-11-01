#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – take Rentalars off this server (uninstall; NFA-078).
#
#   sudo rentalars uninstall --dry-run [--keep-data|--purge]    only show what would be removed and what stays
#   sudo rentalars uninstall --keep-data [--yes]                remove the application, keep the data
#   sudo rentalars uninstall --purge [options]                  also remove database, backups and configuration
#
# One of the three choices is needed. Without any, the command prints this
# help and changes nothing: nothing is ever removed by default.
#
# --dry-run     changes nothing and lists everything that would be removed, and
#               everything that stays, for the chosen kind. Alone it shows
#               --keep-data; "--dry-run --purge" shows the purge.
#
# --keep-data   the exact opposite of the installation, minus the data. It
#                 - stops and disables the application, its timers and the local AI,
#                   and removes their units from /etc/systemd/system;
#                 - removes the NGINX site (NGINX is reloaded only if its
#                   configuration test passes) and the folder for the
#                   certificate check;
#                 - removes the program, the Python libraries, the local AI and the map
#                   data of the route service (/opt/rentalars) and the command "rentalars".
#               It KEEPS the database, the data folder (uploads, media), the backups,
#               the configuration in /etc/rentalars (with the recovery key and the
#               certificates), the encryption key of MariaDB, the Let's Encrypt
#               certificate, the logs and the system user. At the end it says how to
#               set Rentalars up again on top of the data.
#               --yes   do not ask (needed when no terminal is attached)
#
# --purge       does everything --keep-data does and, in addition, removes
#                 - the database and its user (on this server: only the database and the
#                   user of Rentalars, never another database; on a database server
#                   elsewhere: the tables of Rentalars' database – the database and the
#                   account belong to the administrator of that server);
#                 - the backups, the data folder (uploads, media), the configuration
#                   folder /etc/rentalars including the recovery key and the own certificates;
#                 - the Let's Encrypt certificate of the site (unless another site uses it);
#                 - the logs of NGINX and MariaDB that are Rentalars' own;
#                 - the MariaDB settings of Rentalars (only if no other database lives on this
#                   server) and the system user "rentalars" with its group.
#               It NEVER removes packages (MariaDB, NGINX, Python, certbot, ffmpeg …) nor the
#               encryption key of MariaDB: MariaDB cannot read its files without it. It names
#               them at the end.
#               A purge cannot be undone. It asks you to type the host name of the site; without
#               a terminal it refuses unless it is given the long option below.
#               --backup-to DIR       first write a last backup and put a copy in DIR (not in a
#                                     folder that is removed; offered at a terminal, default /root)
#               --no-final-backup     do not write a last backup
#               --yes-i-really-want-to-delete-everything
#                                     the confirmation for scripts and for a run without terminal;
#                                     replaces the typing of the host name. --yes does NOT do that.
#                                     Without a terminal it needs --backup-to or --no-final-backup as
#                                     well (exit status 2 otherwise): the last backup is a decision.
#
# Exit status: 0 done (or dry run), 1 error, cancelled or not everything could be removed,
# 2 wrong use (nothing was done).
#
# The script runs from a copy of itself (the command "rentalars" makes it), because it
# removes the folder it comes from. After --keep-data the command "rentalars" is gone;
# a later --purge is started from the unpacked package:  sudo ./deploy/uninstall.sh --purge
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "${RENTALARS_LIB:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh}"

# --- Test hooks ----------------------------------------------------------------------------------
# RENTALARS_UNINSTALL_TEST_ROOT puts every path below a folder, RENTALARS_UNINSTALL_STUBS names a folder with
# stand-ins for the commands that change the system (systemctl, mariadb, nginx, certbot, getent, userdel,
# groupdel, gpasswd), put first in the PATH, and RENTALARS_UNINSTALL_TEST_INTERACTIVE=1 lets standard input
# count as a terminal – only for the tests (tests/deploy/test_uninstall.sh). With a test folder, root is not
# required, and the script refuses to run without every stand-in, so that a test can never reach the real system.
readonly TEST_ROOT="${RENTALARS_UNINSTALL_TEST_ROOT:-}"
if [[ -n "${TEST_ROOT}" ]]; then
    [[ "${TEST_ROOT}" == /?* && -d "${TEST_ROOT}" ]] || fail "RENTALARS_UNINSTALL_TEST_ROOT: ${TEST_ROOT} is no folder."
    stubs="${RENTALARS_UNINSTALL_STUBS:-}"
    [[ -n "${stubs}" && -d "${stubs}" ]] || fail "RENTALARS_UNINSTALL_STUBS: a test folder needs the folder with the stand-ins."
    for stub in systemctl mariadb nginx certbot getent userdel groupdel gpasswd; do
        [[ -x "${stubs}/${stub}" ]] || fail "RENTALARS_UNINSTALL_STUBS: ${stub} is missing in ${stubs}."
    done
    PATH="${stubs}:${PATH}"
fi

# A path of the system, below the test folder when there is one: at_root /etc/rentalars
at_root() { printf '%s%s' "${TEST_ROOT}" "$1"; }
# Succeeds if a file, folder or link is there (a link that leads nowhere counts).
exists() { [[ -e "$1" || -L "$1" ]]; }
# Succeeds at a terminal – or in a test that says so.
interactive() { [[ -t 0 ]] || [[ -n "${TEST_ROOT}" && "${RENTALARS_UNINSTALL_TEST_INTERACTIVE:-}" == "1" ]]; }

# The copy of this script that the command "rentalars" made goes when the script ends.
work=""
# shellcheck disable=SC2317  # run by the trap
cleanup() {
    [[ -z "${work}" ]] || rm -rf "${work}"
    if [[ -n "${RENTALARS_UNINSTALL_COPY:-}" && "${RENTALARS_UNINSTALL_COPY}" == "${BASH_SOURCE[0]}" ]]; then
        rm -f -- "${BASH_SOURCE[0]}"
    fi
    return 0
}
trap cleanup EXIT

# --- Options -------------------------------------------------------------------------------------------

usage() {
    if [[ "$(operator_language)" == de ]]; then
        cat <<'USAGE'
Rentalars von diesem Server entfernen – wähle eine Art:

  sudo rentalars uninstall --dry-run     zeigt, was entfernt würde und was bleibt; ändert nichts
                                         (allein: wie --keep-data; mit --purge: wie das Löschen)
  sudo rentalars uninstall --keep-data   entfernt die Anwendung, behält aber die Daten: Datenbank,
                                         Dateien, Sicherungen, Konfiguration, Schlüssel
  sudo rentalars uninstall --purge       entfernt zusätzlich Datenbank, Sicherungen und Konfiguration
                                         – nach ausdrücklicher Bestätigung; nicht rückgängig zu machen

Ohne Angabe passiert nichts. Ausführlich: sudo rentalars uninstall --help
USAGE
    else
        cat <<'USAGE'
Take Rentalars off this server – choose a kind:

  sudo rentalars uninstall --dry-run     shows what would be removed and what stays; changes nothing
                                         (alone: like --keep-data; with --purge: like the purge)
  sudo rentalars uninstall --keep-data   removes the application but keeps the data: database,
                                         files, backups, configuration, keys
  sudo rentalars uninstall --purge       also removes database, backups and configuration – after
                                         explicit confirmation; cannot be undone

Without a choice nothing happens. In detail: sudo rentalars uninstall --help
USAGE
    fi
}

# Wrong use: say what is wrong, show the choices, change nothing – exit status 2.
usage_error() {
    printf '\n\033[1;31m%s\033[0m %s\n\n' "$(t "Fehler:" "Error:")" "$1" >&2
    usage >&2
    exit 2
}

dry_run=false keep_data=false purge=false assume_yes=false delete_everything=false
backup_to="" no_final_backup=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) dry_run=true; shift ;;
        --keep-data) keep_data=true; shift ;;
        --purge) purge=true; shift ;;
        --yes) assume_yes=true; shift ;;
        --yes-i-really-want-to-delete-everything) delete_everything=true; shift ;;
        --backup-to) [[ -n "${2:-}" ]] || usage_error "$(t "--backup-to braucht einen Ordner." "--backup-to needs a folder.")"
                     backup_to="$2"; shift 2 ;;
        --no-final-backup) no_final_backup=true; shift ;;
        -h|--help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) usage_error "$(t "Unbekannte Option: $1" "Unknown option: $1")" ;;
    esac
done
if ${keep_data} && ${purge}; then
    usage_error "$(t "--keep-data und --purge schließen sich aus. Bitte nur eines." "--keep-data and --purge exclude each other. Please give only one.")"
fi
if ! ${keep_data} && ! ${purge} && ! ${dry_run}; then
    # Nothing is removed by default.
    usage
    exit 2
fi
if ! ${purge} && { ${delete_everything} || ${no_final_backup} || [[ -n "${backup_to}" ]]; }; then
    usage_error "$(t "--backup-to, --no-final-backup und --yes-i-really-want-to-delete-everything gehören zu --purge." "--backup-to, --no-final-backup and --yes-i-really-want-to-delete-everything belong to --purge.")"
fi
if ${no_final_backup} && [[ -n "${backup_to}" ]]; then
    usage_error "$(t "--backup-to und --no-final-backup schließen sich aus." "--backup-to and --no-final-backup exclude each other.")"
fi
# A dry run alone shows what the safe removal does.
mode="keep"
${purge} && mode="purge"
# (uninstall; NFA-078) A relative folder for the last backup is made absolute at once, so that every message names the real place.
if [[ -n "${backup_to}" && "${backup_to}" != /* ]]; then
    relative_backup_to="${backup_to}"
    backup_to="${PWD%/}"
    backup_to="${backup_to#"${TEST_ROOT}"}/${relative_backup_to}"   # in a test the working folder lies below the test root
fi
# (uninstall; NFA-078) A script that deletes everything must also say what happens to the last backup: no silent default.
if ${purge} && ! ${dry_run} && ${delete_everything} && ! interactive && [[ -z "${backup_to}" ]] && ! ${no_final_backup}; then
    usage_error "$(t "Ohne Terminal muss bei --yes-i-really-want-to-delete-everything auch stehen, was mit der letzten Sicherung geschieht: --backup-to ORDNER (schreibt eine und kopiert sie dorthin) oder --no-final-backup (schreibt keine). Es wurde nichts verändert." "Without a terminal, --yes-i-really-want-to-delete-everything must also say what happens to the last backup: --backup-to FOLDER (writes one and copies it there) or --no-final-backup (writes none). Nothing was changed.")"
fi

[[ -n "${TEST_ROOT}" ]] || require_root
if [[ -z "${TEST_ROOT}" && "${CONFIG_FILE}" != "${CONFIG_DIR}/rentalars.conf" ]]; then
    fail "$(t "RENTALARS_CONFIG ist gesetzt (${CONFIG_FILE}). Beim Entfernen gilt nur ${CONFIG_DIR}/rentalars.conf; bitte die Variable nicht setzen." "RENTALARS_CONFIG is set (${CONFIG_FILE}). Removing only goes by ${CONFIG_DIR}/rentalars.conf; please do not set the variable.")"
fi

# --- What there is -----------------------------------------------------------------------------------------
# Every path comes from lib.sh. Nothing is spelled out twice, and nothing is removed that is not named here.

home="$(at_root "${RENTALARS_HOME}")"
program_dir="$(at_root "${APP_DIR}")"
conf_dir="$(at_root "${CONFIG_DIR}")"
conf_file="${CONFIG_FILE}"
unit_dir="$(at_root "${SYSTEMD_UNIT_DIR}")"
command_link="$(at_root "${CLI_LINK}")"
configured=false
[[ -f "${conf_file}" ]] && configured=true

# All values in one go (the same reading as config_get, lib.sh, but one start of Python instead of many).
# (uninstall; NFA-078) A file Python cannot read (a key twice, a missing section header) makes Python print the
# reason and end with status 1 instead of a traceback; the script decides what that means for the chosen kind below.
config_unreadable=false config_reason=""
if ! settings_text="$(python3 - "${conf_file}" "${DEFAULT_DATA_DIR}" "${DEFAULT_BACKUP_DIR}" 2> /dev/null <<'PYTHON'
import configparser
import sys
import urllib.parse

path, default_data, default_backup = sys.argv[1:4]
parser = configparser.ConfigParser(interpolation=None)
try:
    parser.read(path, encoding="utf-8")
    url = parser.get("rentalars", "url", fallback="")
    values = (
        parser.get("rentalars", "data_dir", fallback=default_data),
        parser.get("backup", "directory", fallback=default_backup),
        url,
        urllib.parse.urlparse(url).hostname or "",
        parser.get("database", "name", fallback="rentalars"),
        parser.get("database", "user", fallback="rentalars"),
        parser.get("database", "host", fallback=""),
        parser.get("database", "port", fallback=""),
        parser.get("backup", "encrypt", fallback="false"),
    )
except (configparser.Error, UnicodeError, ValueError) as error:
    print(" ".join(str(error).split()))
    sys.exit(1)
for value in values:
    print(value.replace("\n", " "))
PYTHON
)"; then
    config_unreadable=true config_reason="${settings_text}"
fi
if ${config_unreadable}; then
    if [[ "${mode}" == purge ]]; then
        fail "$(t "Die Konfiguration ${conf_file} lässt sich nicht lesen (${config_reason:-unbekannter Fehler}). Ohne sie ist nicht sicher, welche Datenbank und welche Ordner zu Rentalars gehören; darum löscht --purge nichts. Bitte die Datei reparieren und noch einmal versuchen. Es wurde nichts verändert." "The configuration ${conf_file} cannot be read (${config_reason:-unknown error}). Without it it is not certain which database and which folders belong to Rentalars, so --purge deletes nothing. Please repair the file and try again. Nothing was changed.")"
    fi
    warn "$(t "Die Konfiguration ${conf_file} lässt sich nicht lesen (${config_reason:-unbekannter Fehler}). Es gelten die Standardwerte; die Datenbank ist unbekannt und wird nicht angefasst." "The configuration ${conf_file} cannot be read (${config_reason:-unknown error}). The defaults apply; the database is unknown and is not touched.")"
    settings=("${DEFAULT_DATA_DIR}" "${DEFAULT_BACKUP_DIR}" "" "" rentalars rentalars "" "" false)
else
    mapfile -t settings <<<"${settings_text}"
fi
data_dir="${settings[0]%/}" backup_dir="${settings[1]%/}" site_url="${settings[2]}" host_name="${settings[3]}"
db_name="${settings[4]}" db_user="${settings[5]}" db_host="${settings[6]}" db_port="${settings[7]}"
encrypted_backups=false
[[ "${settings[8],,}" =~ ^(true|yes|on|1)$ ]] && encrypted_backups=true
[[ "${data_dir}" == /?* && "${data_dir}" != *..* && "${backup_dir}" == /?* && "${backup_dir}" != *..* ]] \
    || fail "$(t "In ${conf_file} stehen für data_dir oder das Sicherungsverzeichnis keine vollständigen Pfade. Es wurde nichts verändert." "${conf_file} gives no full paths for data_dir or the backup directory. Nothing was changed.")"

# (uninstall; NFA-078) Where the database is, as the messages name it; and whether it is the MariaDB of this server.
# A port other than the default with a TCP host (127.0.0.1 …) is a tunnel to another server: only its tables are dropped.
db_where="${db_host:-localhost}${db_port:+:${db_port}}"
database_is_here() { # database_is_here HOST PORT
    is_local_host "$1" || return 1
    [[ -z "$2" || "$2" == 3306 ]]
}

db_local=false
if ${configured} && ! ${config_unreadable} && database_is_here "${db_host}" "${db_port}"; then db_local=true; fi
site_file="$(at_root "${NGINX_SITE}")"

# What the plan holds. REMOVE_*: removed in this kind of run; KEEP_*: stays; BY_HAND: stays and is for the administrator.
REMOVE_LABELS=() REMOVE_PATHS=() KEEP_LABELS=() KEEP_TEXTS=() BY_HAND=()
UNITS=()                  # the units to stop, timers first
STOP_NOTE=""
DATABASE_ACTION="none"    # drop-local | empty-remote | none
DATABASE_USER_DROP=false
SETTINGS_REMOVE=false
CERTIFICATE_NAME=""       # a Let's Encrypt certificate to delete
USER_REMOVE=false
FOREIGN_DATABASES=()
FOREIGN_KNOWN=false
NGINX_TOUCHED=false
BACKUPS_REMOVED=false     # the backup folder is in the removal list (it stays when the configuration moved it elsewhere)
LINKED_TARGETS=()         # links to folders on the removal list: the link goes, the target (and its data) stays

add_remove() { # add_remove LABEL PATH – only what is there
    exists "$2" || return 0
    REMOVE_LABELS+=("$1")
    REMOVE_PATHS+=("$2")
}
add_keep() { # add_keep LABEL TEXT
    KEEP_LABELS+=("$1")
    KEEP_TEXTS+=("$2")
}
add_matching() { # add_matching LABEL PATTERN – every file of a folder that matches (the pattern is a path of lib.sh)
    local label="$1" pattern dir name path
    pattern="$(at_root "$2")"
    dir="$(dirname "${pattern}")" name="$(basename "${pattern}")"
    [[ -d "${dir}" ]] || return 0
    while IFS= read -r path; do
        add_remove "${label}" "${path}"
    done < <(find "${dir}" -maxdepth 1 -name "${name}" -print | sort)
}

# Is this installation of the kind the installer sets up? The service user must be a system account without a
# login whose home is the data folder – otherwise it is somebody else's account and stays.
service_user_is_ours() {
    local entry shell account_home
    entry="$(getent passwd "${SERVICE_USER}" 2> /dev/null)" || return 1
    shell="${entry##*:}"
    account_home="${entry%:*}"
    account_home="${account_home##*:}"
    [[ "${SERVICE_USER}" != root && "${shell}" == */nologin && "${account_home}" == "${DEFAULT_DATA_DIR}" ]]
}

# The tables of the MariaDB on this server other than the system's own and Rentalars' (names, one per line).
# Sets FOREIGN_KNOWN to false if MariaDB does not answer.
find_foreign_databases() {
    local all
    FOREIGN_DATABASES=() FOREIGN_KNOWN=false
    if all="$(mariadb --batch --skip-column-names --connect-timeout=10 -e \
        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME NOT IN ('information_schema','mysql','performance_schema','sys')" 2> /dev/null)"; then
        FOREIGN_KNOWN=true
        mapfile -t FOREIGN_DATABASES < <(grep -vxF -e "${db_name}" -e "" <<<"${all}" || true)
    fi
}

# Succeeds if the user may be dropped: it has rights on Rentalars' database only (and none else).
database_user_is_exclusive() {
    local grants line escaped="${db_name//_/\\_}"
    grants="$(mariadb --batch --skip-column-names -e "SHOW GRANTS FOR '${db_user}'@'localhost'" 2> /dev/null)" || return 1
    [[ -n "${grants}" ]] || return 1
    while IFS= read -r line; do
        [[ -z "${line}" || "${line}" == "GRANT USAGE ON *.*"* ]] && continue
        [[ "${line}" == *"ON \`${db_name}\`.*"* || "${line}" == *"ON \`${escaped}\`.*"* ]] && continue
        return 1
    done <<<"${grants}"
    return 0
}

build_plan() {
    local unit label certificate_path="" other=""

    # 1. Services and timers – the units the installer, the local AI and the updates put there.
    local timers=() services=()
    while IFS= read -r unit; do
        [[ -n "${unit}" ]] || continue
        case "${unit}" in
            *.timer) timers+=("${unit}") ;;
            "${SERVICE_NAME}.service") ;;
            *) services+=("${unit}") ;;
        esac
    done < <(
        find "${unit_dir}" -maxdepth 1 \( -name 'rentalars*.service' -o -name 'rentalars*.timer' \) ! -type d -printf '%f\n' 2> /dev/null | sort
    )
    UNITS=("${timers[@]}" "${services[@]}")
    exists "${unit_dir}/${SERVICE_NAME}.service" && UNITS+=("${SERVICE_NAME}.service")
    label="$(t "Dienst-Dateien" "Unit files")"
    add_matching "${label}" "${SYSTEMD_UNIT_DIR}/rentalars*.timer"
    add_matching "${label}" "${SYSTEMD_UNIT_DIR}/rentalars*.service"
    add_matching "${label}" "${SYSTEMD_UNIT_DIR}/rentalars*.service.d"
    ((${#UNITS[@]} == 0)) || STOP_NOTE="${UNITS[*]}"

    # 2. NGINX: the site, the link that switches it on, the proxy snippet, the folder of the certificate check.
    label="NGINX"
    add_remove "${label}" "$(at_root "${NGINX_SITE_LINK}")"
    add_remove "${label}" "${site_file}"
    add_remove "${label}" "$(at_root "${NGINX_PROXY_SNIPPET}")"
    add_remove "${label}" "$(at_root "${NGINX_REALIP_SNIPPET}")"
    add_remove "${label}" "$(at_root "${ACME_ROOT}")"

    # 3. The program: releases, program and libraries, the local AI and the maps of the route service, the command.
    label="$(t "Programm" "Program")"
    add_remove "${label}" "${home}"
    if exists "${command_link}"; then
        if grep -qF "${APP_DIR}/deploy/rentalars" "${command_link}" 2> /dev/null; then
            add_remove "$(t "Befehl rentalars" "Command rentalars")" "${command_link}"
        else
            BY_HAND+=("$(t "${CLI_LINK} gehört nicht zu Rentalars (er ruft ${APP_DIR}/deploy/rentalars nicht auf) – er bleibt." "${CLI_LINK} does not belong to Rentalars (it does not call ${APP_DIR}/deploy/rentalars) – it stays.")")
        fi
    fi
    add_matching "$(t "Sperrdateien" "Lock files")" "/run/rentalars-*.lock"

    # 4. The data. Removed by the purge – but only where the installer made them: a folder that the
    #    configuration moved elsewhere is named, not removed.
    local what
    for what in data backup; do
        local configured_path default_path label_text
        if [[ "${what}" == data ]]; then
            configured_path="${data_dir}" default_path="${DEFAULT_DATA_DIR}" label_text="$(t "Datenordner (Dateien, Medien)" "Data folder (files, media)")"
        else
            configured_path="${backup_dir}" default_path="${DEFAULT_BACKUP_DIR}" label_text="$(t "Sicherungen" "Backups")"
        fi
        if [[ "${mode}" == purge ]]; then
            add_remove "${label_text}" "$(at_root "${default_path}")"
            if [[ "${configured_path}" != "${default_path}" ]]; then
                BY_HAND+=("$(t "${label_text}: ${conf_file} nennt ${configured_path}. Das hat der Installer nicht angelegt; es bleibt. Von Hand entfernen, wenn gewollt." "${label_text}: ${conf_file} names ${configured_path}. The installer did not create it; it stays. Remove it by hand if you want to.")")
            fi
        elif exists "$(at_root "${configured_path}")"; then
            add_keep "${label_text}" "${configured_path}"
        fi
    done

    # 5. The configuration: the file, certificates of its own, the recovery key, the copies of address changes.
    if [[ "${mode}" == purge ]]; then
        add_remove "$(t "Konfiguration" "Configuration")" "${conf_dir}"
    elif exists "${conf_dir}"; then
        add_keep "$(t "Konfiguration" "Configuration")" "${CONFIG_DIR} ($(t "rentalars.conf, Wiederherstellungsschlüssel, eigene Zertifikate" "rentalars.conf, recovery key, own certificates"))"
    fi

    # 6. Logs of Rentalars' own.
    if [[ "${mode}" == purge ]]; then
        label="$(t "Protokolle" "Logs")"
        add_matching "${label}" "${NGINX_LOG_PATTERN}"
        # (uninstall; NFA-078) The slow log goes with the MariaDB settings that write it (section 9): if those stay,
        # MariaDB keeps the file open and would write to a deleted one.
    elif compgen -G "$(at_root "${NGINX_LOG_PATTERN}")" > /dev/null || compgen -G "$(at_root "${MARIADB_SLOW_LOG_PATTERN}")" > /dev/null; then
        add_keep "$(t "Protokolle" "Logs")" "${NGINX_LOG_PATTERN}, ${MARIADB_SLOW_LOG_PATTERN}"
    fi

    # 7. The certificate of Let's Encrypt, named by the site that is removed.
    if [[ -f "${site_file}" ]]; then
        certificate_path="$(sed -n -E "s|^[[:space:]]*ssl_certificate[[:space:]]+${LETSENCRYPT_LIVE_DIR}/([^/;]+)/fullchain\.pem;.*|\1|p" "${site_file}" | head -n 1)"
        if [[ "${certificate_path}" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
            if [[ "${mode}" == purge ]]; then
                other="$(grep -rlF --exclude="$(basename "${NGINX_SITE}")" "${LETSENCRYPT_LIVE_DIR}/${certificate_path}/" "$(dirname "$(dirname "${site_file}")")" 2> /dev/null | head -n 1 || true)"
                if [[ -n "${other}" ]]; then
                    BY_HAND+=("$(t "Das Zertifikat von Let's Encrypt für ${certificate_path} bleibt: ${other} benutzt es auch." "The Let's Encrypt certificate for ${certificate_path} stays: ${other} uses it as well.")")
                elif command -v certbot > /dev/null 2>&1; then
                    CERTIFICATE_NAME="${certificate_path}"
                else
                    BY_HAND+=("$(t "Das Zertifikat von Let's Encrypt für ${certificate_path} bleibt, certbot fehlt. Von Hand: certbot delete --cert-name ${certificate_path}" "The Let's Encrypt certificate for ${certificate_path} stays, certbot is missing. By hand: certbot delete --cert-name ${certificate_path}")")
                fi
            else
                add_keep "$(t "Zertifikat (Let's Encrypt)" "Certificate (Let's Encrypt)")" "${LETSENCRYPT_LIVE_DIR}/${certificate_path} – $(t "certbot erneuert es nicht mehr, solange die NGINX-Seite fehlt (Löschen: certbot delete --cert-name ${certificate_path})" "certbot cannot renew it while the NGINX site is missing (to delete: certbot delete --cert-name ${certificate_path})")"
            fi
        fi
    fi

    # 8. The database.
    if ${config_unreadable}; then
        BY_HAND+=("$(t "${conf_file} ließ sich nicht lesen: Welche Datenbank zu Rentalars gehört, ist unbekannt. Die Datenbank wird nicht angefasst." "${conf_file} could not be read: which database belongs to Rentalars is unknown. The database is not touched.")")
    elif ${configured}; then
        if [[ "${mode}" == keep ]]; then
            if ${db_local}; then
                add_keep "$(t "Datenbank" "Database")" "${db_name} ($(t "MariaDB auf diesem Server" "MariaDB on this server")), $(t "Benutzer" "user") ${db_user}"
            else
                add_keep "$(t "Datenbank" "Database")" "${db_name} $(t "auf" "on") ${db_where}"
            fi
        else
            [[ "${db_name}" =~ ^[A-Za-z0-9_]+$ && ! "${db_name,,}" =~ ^(information_schema|mysql|performance_schema|sys)$ ]] \
                || fail "$(t "Der Datenbankname '${db_name}' in ${conf_file} sieht nicht nach der Datenbank von Rentalars aus. Es wurde nichts verändert." "The database name '${db_name}' in ${conf_file} does not look like the database of Rentalars. Nothing was changed.")"
            [[ "${db_user}" =~ ^[A-Za-z0-9_.-]+$ && ! "${db_user,,}" =~ ^(root|mysql|mariadb\.sys)$ ]] \
                || fail "$(t "Der Datenbankbenutzer '${db_user}' in ${conf_file} sieht nicht nach dem Benutzer von Rentalars aus. Es wurde nichts verändert." "The database user '${db_user}' in ${conf_file} does not look like the user of Rentalars. Nothing was changed.")"
            if ${db_local}; then
                DATABASE_ACTION="drop-local"
                find_foreign_databases
                if ${FOREIGN_KNOWN} && ((${#FOREIGN_DATABASES[@]} == 0)); then
                    SETTINGS_REMOVE=true
                fi
                if mariadb --batch --skip-column-names -e "SELECT 1" > /dev/null 2>&1 && database_user_is_exclusive; then
                    DATABASE_USER_DROP=true
                fi
            else
                DATABASE_ACTION="empty-remote"
            fi
        fi
    else
        BY_HAND+=("$(t "${conf_file} fehlt: Welche Datenbank zu Rentalars gehört, ist unbekannt. Die Datenbank wird nicht angefasst." "${conf_file} is missing: which database belongs to Rentalars is unknown. The database is not touched.")")
    fi

    # 9. The settings of Rentalars in MariaDB (they apply to the whole server: only if no other database lives there).
    if [[ "${mode}" == purge ]] && ${db_local}; then
        if ${SETTINGS_REMOVE}; then
            label="$(t "MariaDB-Einstellungen" "MariaDB settings")"
            add_remove "${label}" "$(at_root "${MARIADB_SETTINGS}")"
            add_remove "${label}" "$(at_root "${MARIADB_MEMORY_SETTINGS}")"
            add_matching "$(t "Protokolle" "Logs")" "${MARIADB_SLOW_LOG_PATTERN}"
            if exists "$(at_root "${MARIADB_SETTINGS}")" || exists "$(at_root "${MARIADB_MEMORY_SETTINGS}")"; then
                BY_HAND+=("$(t "Die entfernten MariaDB-Einstellungen gelten erst nach einem Neustart von MariaDB (sudo systemctl restart mariadb); das Skript startet MariaDB nicht neu." "The removed MariaDB settings apply only after MariaDB is restarted (sudo systemctl restart mariadb); the script does not restart MariaDB.")")
            fi
        elif exists "$(at_root "${MARIADB_SETTINGS}")"; then
            if compgen -G "$(at_root "${MARIADB_SLOW_LOG_PATTERN}")" > /dev/null; then
                add_keep "$(t "Protokolle" "Logs")" "${MARIADB_SLOW_LOG_PATTERN} ($(t "MariaDB schreibt sie weiter, solange seine Einstellungen bleiben" "MariaDB keeps writing them while its settings stay"))"
            fi
            BY_HAND+=("$(t "Die Einstellungen ${MARIADB_SETTINGS} gelten für den ganzen MariaDB-Server und bleiben" "The settings ${MARIADB_SETTINGS} apply to the whole MariaDB server and stay") ($(
                if ${FOREIGN_KNOWN}; then t "weitere Datenbanken dort: ${FOREIGN_DATABASES[*]}" "other databases there: ${FOREIGN_DATABASES[*]}"; else t "MariaDB antwortet nicht" "MariaDB does not answer"; fi
            )).")
        fi
    elif exists "$(at_root "${MARIADB_SETTINGS}")"; then
        add_keep "$(t "MariaDB-Einstellungen" "MariaDB settings")" "${MARIADB_SETTINGS}"
        # (uninstall; NFA-078) A purge with the database elsewhere: the settings stay, so does the slow log they write.
        if [[ "${mode}" == purge ]] && compgen -G "$(at_root "${MARIADB_SLOW_LOG_PATTERN}")" > /dev/null; then
            add_keep "$(t "Protokolle" "Logs")" "${MARIADB_SLOW_LOG_PATTERN}"
        fi
    fi

    # 10. The key of MariaDB's encryption – always stays: MariaDB would not start without it.
    if exists "$(at_root "${MARIADB_ENCRYPTION_SETTINGS}")" || exists "$(at_root "${MARIADB_KEY_DIR}")"; then
        add_keep "$(t "DB-Verschlüsselung" "DB encryption")" "${MARIADB_KEY_DIR}, ${MARIADB_ENCRYPTION_SETTINGS}"
        if [[ "${mode}" == purge ]]; then
            BY_HAND+=("$(t "Schlüssel und Einstellungen der Verschlüsselung (${MARIADB_KEY_DIR}, ${MARIADB_ENCRYPTION_SETTINGS}) bleiben immer: MariaDB kann seine Dateien ohne sie nicht mehr lesen und startet nicht. Sie gehören zu MariaDB selbst; entferne sie nur zusammen mit MariaDB (apt purge mariadb-server, dazu /var/lib/mysql)." "Key and settings of the encryption (${MARIADB_KEY_DIR}, ${MARIADB_ENCRYPTION_SETTINGS}) always stay: MariaDB cannot read its files without them and would not start. They belong to MariaDB itself; remove them only together with MariaDB (apt purge mariadb-server, and /var/lib/mysql).")")
        fi
    fi

    # 11. The system user.
    if [[ "${mode}" == purge ]]; then
        if getent passwd "${SERVICE_USER}" > /dev/null 2>&1; then
            if service_user_is_ours; then
                USER_REMOVE=true
            else
                BY_HAND+=("$(t "Das Konto ${SERVICE_USER} ist kein Systemkonto des Installers (Shell oder Heimatordner passen nicht) und bleibt." "The account ${SERVICE_USER} is not a system account of the installer (shell or home do not fit) and stays.")")
            fi
        fi
    elif getent passwd "${SERVICE_USER}" > /dev/null 2>&1; then
        add_keep "$(t "Systemkonto" "System account")" "${SERVICE_USER} ($(t "und Gruppe; www-data bleibt in der Gruppe" "and group; www-data stays in the group"))"
    fi

    # 12. What this script never touches.
    local packages=() package_file
    local tls_hint=""
    [[ -z "${certificate_path}" ]] || tls_hint="letsencrypt"
    mapfile -t packages < <(system_packages ubuntu "${db_local}" "${tls_hint}" "")
    for package_file in "${AI_DIR}/${INSTALLED_PACKAGES_NAME}" "${ROUTE_DIR}/${INSTALLED_PACKAGES_NAME}"; do
        if [[ -f "$(at_root "${package_file}")" ]]; then
            mapfile -t -O "${#packages[@]}" packages < "$(at_root "${package_file}")"
        fi
    done
    BY_HAND+=("$(t "Pakete des Betriebssystems werden nie entfernt: ${packages[*]}. Wenn du sie nicht mehr brauchst: sudo apt remove …, nachdem du geprüft hast, dass nichts anderes auf diesem Server sie nutzt." "Packages of the operating system are never removed: ${packages[*]}. If you do not need them any more: sudo apt remove …, after you checked that nothing else on this server uses them.")")
    if [[ -f "${site_file}" ]]; then
        BY_HAND+=("$(t "Die Standard-Seite von NGINX (sites-enabled/default), die der Installer abgeschaltet hat, wird nicht zurückgeschaltet." "The default site of NGINX (sites-enabled/default), which the installer switched off, is not switched on again.")")
    fi
    BY_HAND+=("$(t "Das Journal von systemd (journalctl -u rentalars) ist Sache von systemd und bleibt." "The systemd journal (journalctl -u rentalars) is systemd's business and stays.")")
    # An old database that "move-database" left behind is not Rentalars' current one.
    if [[ "${mode}" == purge ]] && ${db_local} && ${FOREIGN_KNOWN} && ((${#FOREIGN_DATABASES[@]} > 0)); then
        BY_HAND+=("$(t "Weitere Datenbanken auf diesem MariaDB-Server werden nicht angefasst: ${FOREIGN_DATABASES[*]} (auch eine alte Datenbank von Rentalars, die \"move-database\" stehen ließ, gehört dazu)." "Other databases on this MariaDB server are not touched: ${FOREIGN_DATABASES[*]} (this includes an old database of Rentalars that \"move-database\" left behind).")")
    fi

    # 13. (uninstall; NFA-078) A data or backup folder that stays must not lie in a path that is removed – whatever the
    #     configuration says (/opt/rentalars/backups, a link into /opt/rentalars …). Both kinds, before anything is changed.
    local planned planned_real configured_real
    for what in data backup; do
        if [[ "${what}" == data ]]; then
            configured_path="${data_dir}" default_path="${DEFAULT_DATA_DIR}" label_text="$(t "Der Datenordner" "The data folder")"
        else
            configured_path="${backup_dir}" default_path="${DEFAULT_BACKUP_DIR}" label_text="$(t "Der Sicherungsordner" "The backup folder")"
        fi
        # The installer's own folder is meant to go in a purge.
        [[ "${mode}" == purge && "${configured_path}" == "${default_path}" ]] && continue
        exists "$(at_root "${configured_path}")" || continue
        configured_real="$(readlink -f -- "$(at_root "${configured_path}")")"
        for planned in "${REMOVE_PATHS[@]}"; do
            # The place of the entry itself – a link on the list is removed, not followed.
            planned_real="$(readlink -f -- "$(dirname "${planned}")")/$(basename "${planned}")"
            if [[ "${configured_real}" == "${planned_real}" || "${configured_real}" == "${planned_real}/"* ]]; then
                fail "$(t "${label_text} ${configured_path} (aus ${conf_file}) liegt in ${planned#"${TEST_ROOT}"}, das bei diesem Entfernen gelöscht wird – er würde mit verschwinden, obwohl er bleiben soll. Bitte erst an einen Ort außerhalb verschieben (und ${conf_file} anpassen). Es wurde nichts verändert." "${label_text} ${configured_path} (from ${conf_file}) lies in ${planned#"${TEST_ROOT}"}, which is removed by this run – it would vanish although it is meant to stay. Please move it to a place outside first (and adjust ${conf_file}). Nothing was changed.")"
            fi
        done
    done

    # 14. What the list holds really: is the backup folder on it, and which entries are links to folders (only the link goes).
    for planned in "${REMOVE_PATHS[@]}"; do
        if [[ "${planned}" == "$(at_root "${DEFAULT_BACKUP_DIR}")" && "${backup_dir}" == "${DEFAULT_BACKUP_DIR}" ]]; then BACKUPS_REMOVED=true; fi
        if [[ -L "${planned}" && -d "${planned}" ]]; then
            LINKED_TARGETS+=("$(t "${planned#"${TEST_ROOT}"} ist ein Link auf $(readlink -f -- "${planned}"): nur der Link wird entfernt, das Ziel mit seinem Inhalt bleibt. Von Hand entfernen, wenn gewollt." "${planned#"${TEST_ROOT}"} is a link to $(readlink -f -- "${planned}"): only the link is removed, the target with its content stays. Remove it by hand if you want to.")")
        fi
    done
    ((${#LINKED_TARGETS[@]} == 0)) || BY_HAND+=("${LINKED_TARGETS[@]}")
}

# --- Showing the plan ----------------------------------------------------------------------------------------

print_plan() {
    local index previous="" label kind_text
    if [[ "${mode}" == purge ]]; then
        kind_text="--purge: $(t "Anwendung UND Daten entfernen" "remove the application AND the data")"
    else
        kind_text="--keep-data: $(t "Anwendung entfernen, Daten behalten" "remove the application, keep the data")"
    fi
    if ${dry_run}; then
        say "$(t "Rentalars entfernen – Probelauf" "Removing Rentalars – dry run") (${kind_text})"
    else
        say "$(t "Rentalars entfernen" "Removing Rentalars") (${kind_text})"
    fi
    note "$(t "Rentalars" "Rentalars") $(version_of "${program_dir}" 2> /dev/null || true)  –  ${site_url:-$(t "Adresse unbekannt" "address unknown")}"
    note ""
    note "$(t "Wird entfernt:" "Will be removed:")"
    if [[ -n "${STOP_NOTE}" ]]; then
        row 32 "$(t "Dienste und Zeitpläne" "Services and timers")" "$(t "anhalten und abschalten:" "stop and disable:") ${STOP_NOTE}"
    fi
    for index in "${!REMOVE_PATHS[@]}"; do
        label="${REMOVE_LABELS[index]}"
        if [[ "${label}" == "${previous}" ]]; then label=""; else previous="${label}"; fi
        row 32 "${label}" "${REMOVE_PATHS[index]#"${TEST_ROOT}"}"
    done
    case "${DATABASE_ACTION}" in
        drop-local)
            row 32 "$(t "Datenbank" "Database")" "${db_name} ($(t "DROP DATABASE auf dem MariaDB dieses Servers" "DROP DATABASE on the MariaDB of this server"))"
            if ${DATABASE_USER_DROP}; then
                row 32 "" "$(t "Datenbankbenutzer" "database user") ${db_user}@localhost"
            else
                row 32 "" "$(t "Datenbankbenutzer ${db_user}@localhost bleibt (er hat auch Rechte auf anderes oder fehlt)" "database user ${db_user}@localhost stays (it has rights on something else too, or is missing)")"
            fi ;;
        empty-remote)
            row 32 "$(t "Datenbank" "Database")" "$(t "alle Tabellen von ${db_name} auf ${db_where} (Datenbank und Konto gehören dem Administrator jenes Servers und bleiben)" "all tables of ${db_name} on ${db_where} (the database and the account belong to the administrator of that server and stay)")" ;;
    esac
    if [[ -n "${CERTIFICATE_NAME}" ]]; then
        row 32 "$(t "Zertifikat (Let's Encrypt)" "Certificate (Let's Encrypt)")" "certbot delete --cert-name ${CERTIFICATE_NAME}"
    fi
    if ${USER_REMOVE}; then
        row 32 "$(t "Systemkonto" "System account")" "${SERVICE_USER} ($(t "und Gruppe" "and group"))"
    fi
    if ((${#REMOVE_PATHS[@]} == 0)) && [[ -z "${STOP_NOTE}${CERTIFICATE_NAME}" && "${DATABASE_ACTION}" == none ]] && ! ${USER_REMOVE}; then
        note "  $(t "(nichts)" "(nothing)")"
    fi
    note ""
    note "$(t "Bleibt erhalten:" "Stays:")"
    for index in "${!KEEP_TEXTS[@]}"; do
        row 32 "${KEEP_LABELS[index]}" "${KEEP_TEXTS[index]}"
    done
    ((${#KEEP_TEXTS[@]} > 0)) || note "  $(t "(nichts von Rentalars)" "(nothing of Rentalars)")"
    note ""
    note "$(t "Das fasst dieses Skript nie an – für dich zum Prüfen:" "This script never touches these – for you to check:")"
    for index in "${!BY_HAND[@]}"; do
        note "  - ${BY_HAND[index]}"
    done
    if [[ "${mode}" == purge ]]; then
        local backups_fate
        # (uninstall; NFA-078) Only what is on the removal list is "deleted as well"; a folder the configuration moved stays.
        if ${BACKUPS_REMOVED}; then backups_fate="$(t "werden mit gelöscht" "are deleted as well")"; else backups_fate="$(t "bleiben unberührt" "are not touched")"; fi
        note ""
        if [[ -n "${backup_to}" ]]; then
            note "$(t "Vor dem Löschen schreibt das Skript eine letzte Sicherung und kopiert sie nach ${backup_to}." "Before deleting, the script writes a last backup and copies it to ${backup_to}.")"
        elif ${no_final_backup}; then
            note "$(t "Es wird keine letzte Sicherung geschrieben (--no-final-backup); die Sicherungen unter ${backup_dir} ${backups_fate}." "No last backup is written (--no-final-backup); the backups in ${backup_dir} ${backups_fate}.")"
        else
            note "$(t "Vor dem Löschen: eine letzte Sicherung. Die Sicherungen unter ${backup_dir} ${backups_fate};" "Before deleting: a last backup. The backups in ${backup_dir} ${backups_fate};")"
            note "$(t "mit --backup-to ORDNER legt das Skript eine Kopie an einen Ort, der bleibt (bei einem Terminal fragt es danach;" "with --backup-to FOLDER the script puts a copy in a place that stays (at a terminal it asks;")"
            note "$(t "Vorschlag: /root), und nennt dir den Pfad. Von Hand: sudo rentalars backup --keep, die Datei wegkopieren." "suggestion: /root), and names the path. By hand: sudo rentalars backup --keep, then copy the file away.")"
        fi
        if ${encrypted_backups}; then
            note "$(t "Die Sicherungen sind verschlüsselt. Der Wiederherstellungsschlüssel liegt in ${RECOVERY_KEY_FILE} und wird mit gelöscht: Hol ihn dir vorher (sudo rentalars encryption show-key) und bewahre ihn getrennt vom Server auf." "The backups are encrypted. The recovery key is in ${RECOVERY_KEY_FILE} and is deleted too: get it first (sudo rentalars encryption show-key) and keep it apart from the server.")"
        fi
    fi
}

# --- Taking things away -------------------------------------------------------------------------------------------

problems=()
problem() { # A step went wrong, but the rest can still be done.
    problems+=("$1")
    warn "$1"
}

# Is this path one that may be removed? A path that is empty, not absolute, with "..", or one of the
# folders every server has, never is – whatever happened to the variables above.
path_is_safe() {
    local path="${1#"${TEST_ROOT}"}" rest
    [[ -n "${path}" && "${path}" == /* && "${path}" != *..* && "${path}" != */ ]] || return 1
    # Everything Rentalars put on the server has "rentalars" in its name.
    [[ "${path}" == *rentalars* ]] || return 1
    case "${path}" in /run/rentalars-*.lock) return 0 ;; esac
    rest="${path#/}"
    [[ "${rest}" == */* ]] || return 1     # at least two levels: never /etc, /var, /opt …
    case "${path}" in
        /etc/nginx|/etc/mysql|/etc/systemd|/etc/systemd/system|/etc/letsencrypt|/usr/local|/usr/local/bin|/usr/bin|/usr/lib \
            |/var/lib|/var/log|/var/backups|/var/www|/var/log/nginx|/var/log/mysql|/run/systemd|/home|/root) return 1 ;;
    esac
    return 0
}

remove_path() { # remove_path PATH – a link is removed itself, never followed; a mount point is emptied, not removed
    local path="$1"
    if ! path_is_safe "${path}"; then
        problem "$(t "Übersprungen (unsicherer Pfad): ${path}" "Skipped (unsafe path): ${path}")"
        return 0
    fi
    exists "${path}" || return 0
    if [[ -L "${path}" ]]; then
        if [[ -d "${path}" ]]; then note "$(t "${path} ist ein Link: nur der Link wird entfernt, sein Ziel ($(readlink -f -- "${path}" 2> /dev/null || echo "?")) nicht angefasst." "${path} is a link: only the link is removed, its target ($(readlink -f -- "${path}" 2> /dev/null || echo "?")) is not touched.")"; fi
        rm -f -- "${path}"
    elif [[ -d "${path}" ]]; then
        if mountpoint -q -- "${path}" 2> /dev/null; then
            find "${path}" -xdev -mindepth 1 -delete || problem "$(t "${path} ließ sich nicht ganz leeren." "${path} could not be emptied completely.")"
            note "$(t "${path} ist ein eigenes Laufwerk: der Inhalt ist weg, der Ordner bleibt." "${path} is a drive of its own: its content is gone, the folder stays.")"
        else
            rm -rf --one-file-system -- "${path}" || problem "$(t "${path} ließ sich nicht ganz entfernen." "${path} could not be removed completely.")"
        fi
    else
        rm -f -- "${path}" || problem "$(t "${path} ließ sich nicht entfernen." "${path} could not be removed.")"
    fi
}

# (uninstall; NFA-078) Stopping and disabling are two steps with the database step between them: if the database cannot
# be dropped, the units are stopped but still enabled, so that a reboot or "systemctl start" brings Rentalars back as it was.
WAS_ACTIVE=()             # units that ran before they were stopped
STILL_ACTIVE=()           # units that still run after "systemctl stop"
unit_is_running() {
    case "$(systemctl is-active "$1" 2> /dev/null || true)" in
        active|activating|deactivating|reloading) return 0 ;;
    esac
    return 1
}
stop_units() {
    local unit
    WAS_ACTIVE=() STILL_ACTIVE=()
    ((${#UNITS[@]} > 0)) || return 0
    for unit in "${UNITS[@]}"; do
        if unit_is_running "${unit}"; then WAS_ACTIVE+=("${unit}"); fi
    done
    for unit in "${UNITS[@]}"; do
        systemctl stop "${unit}" > /dev/null 2>&1 || true
    done
    for unit in "${UNITS[@]}"; do
        if unit_is_running "${unit}"; then STILL_ACTIVE+=("${unit}"); fi
    done
}
disable_units() {
    local unit
    ((${#UNITS[@]} > 0)) || return 0
    for unit in "${UNITS[@]}"; do
        systemctl disable "${unit}" > /dev/null 2>&1 || true
    done
}
# The command that starts again what ran before: the application and the services first, the timers last.
restart_hint() {
    local list=() index
    for ((index = ${#WAS_ACTIVE[@]} - 1; index >= 0; index--)); do list+=("${WAS_ACTIVE[index]}"); done
    if ((${#list[@]} == 0)); then
        t "(es lief vorher keine Einheit von Rentalars)" "(no unit of Rentalars was running before)"
    else
        printf 'sudo systemctl start %s' "${list[*]}"
    fi
}
# Where the data of before the deletion can be had from.
backup_pointer() {
    if [[ -n "${LAST_BACKUP}" ]]; then
        t "die letzte Sicherung ${LAST_BACKUP}" "the last backup ${LAST_BACKUP}"
    else
        t "die vorhandenen Sicherungen unter ${backup_dir}" "the existing backups in ${backup_dir}"
    fi
}

# Dangling links of the units in the "….wants" folders are tidied by systemd itself; a link that a removed unit file
# left anyway is dropped here.
forget_units() {
    systemctl daemon-reload || true
    systemctl reset-failed 'rentalars*' > /dev/null 2>&1 || true
    if [[ -d "${unit_dir}" ]]; then
        find "${unit_dir}" -mindepth 2 -maxdepth 2 -type l -name 'rentalars*' ! -exec test -e {} \; -delete 2> /dev/null || true
    fi
}

reload_nginx() { # only if NGINX accepts its configuration without the site
    local messages
    command -v nginx > /dev/null 2>&1 || return 0
    messages="$(nginx -t 2>&1)" && {
        if systemctl is-active --quiet nginx; then
            systemctl reload nginx || problem "$(t "NGINX ließ sich nicht neu laden." "NGINX could not be reloaded.")"
        fi
        return 0
    }
    problem "$(t "NGINX nimmt seine Konfiguration ohne die Seite von Rentalars nicht an und wurde nicht neu geladen. NGINX meldet: $(head -n 3 <<<"${messages}" | tr '\n' ' ')" "NGINX does not accept its configuration without the site of Rentalars and was not reloaded. NGINX says: $(head -n 3 <<<"${messages}" | tr '\n' ' ')")"
}

drop_local_database() {
    mariadb <<SQL || fail "$(t "Die Datenbank ${db_name} ließ sich nicht löschen. Zustand: Die Dienste und Zeitpläne von Rentalars sind angehalten, aber noch eingeschaltet; Dateien, Konfiguration und Sicherungen sind unberührt. Wieder in Betrieb nehmen: $(restart_hint). Oder den Befehl noch einmal starten. Brach MariaDB mitten im Löschen ab, kann die Datenbank unvollständig sein – dann zuerst $(backup_pointer) einspielen (sudo rentalars restore DATEI)." "The database ${db_name} could not be dropped. State: the services and timers of Rentalars are stopped but still enabled; files, configuration and backups are untouched. To bring Rentalars back: $(restart_hint). Or start the command again. If MariaDB broke off in the middle, the database may be incomplete – then first restore $(backup_pointer) (sudo rentalars restore FILE).")"
DROP DATABASE IF EXISTS \`${db_name}\`;
SQL
    if ${DATABASE_USER_DROP}; then
        mariadb <<SQL || problem "$(t "Der Datenbankbenutzer ${db_user} ließ sich nicht löschen." "The database user ${db_user} could not be dropped.")"
DROP USER IF EXISTS '${db_user}'@'localhost';
FLUSH PRIVILEGES;
SQL
    fi
}

empty_remote_database() {
    local client="${work}/client.cnf" listing table statements=""
    write_database_credentials "${client}"
    listing="$(mariadb --defaults-extra-file="${client}" --batch --skip-column-names --connect-timeout=10 "${db_name}" -e \
        "SELECT CONCAT(IF(TABLE_TYPE = 'VIEW', 'VIEW', 'TABLE'), ' ', TABLE_NAME) FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE()")" \
        || fail "$(t "Die Datenbank ${db_name} auf ${db_where} antwortet nicht. Zustand: Es wurde keine Tabelle gelöscht. Die Dienste und Zeitpläne von Rentalars sind angehalten, aber noch eingeschaltet. Wieder in Betrieb nehmen: $(restart_hint). Oder den Befehl noch einmal starten." "The database ${db_name} on ${db_where} does not answer. State: no table was dropped. The services and timers of Rentalars are stopped but still enabled. To bring Rentalars back: $(restart_hint). Or start the command again.")"
    while read -r kind table; do
        [[ -n "${table}" ]] || continue
        if [[ ! "${table}" =~ ^[A-Za-z0-9_]+$ ]]; then
            problem "$(t "Die Tabelle '${table}' hat einen ungewöhnlichen Namen und bleibt." "The table '${table}' has an unusual name and stays.")"
            continue
        fi
        if [[ "${kind}" == VIEW ]]; then statements+="DROP VIEW IF EXISTS \`${table}\`;"$'\n'; else statements+="DROP TABLE IF EXISTS \`${table}\`;"$'\n'; fi
    done <<<"${listing}"
    printf 'SET FOREIGN_KEY_CHECKS = 0;\n%s' "${statements}" \
        | mariadb --defaults-extra-file="${client}" --connect-timeout=10 "${db_name}" \
        || fail "$(t "Die Tabellen in ${db_name} auf ${db_where} ließen sich nicht alle löschen. MariaDB bricht beim ersten Fehler ab: Tabellen davor sind womöglich schon gelöscht, die Datenbank kann also unvollständig sein. Der Stand von vor dem Löschen steckt in $(backup_pointer) (einspielen: sudo rentalars restore DATEI). Zustand: Die Dienste und Zeitpläne von Rentalars sind angehalten, aber noch eingeschaltet; Dateien, Konfiguration und Sicherungen sind unberührt. Den Rest löschen: den Befehl noch einmal starten. Rentalars wieder in Betrieb nehmen (erst nach dem Einspielen): $(restart_hint)." "The tables in ${db_name} on ${db_where} could not all be dropped. MariaDB stops at the first error: tables before it may be dropped already, so the database may be incomplete. The state from before the deletion is in $(backup_pointer) (restore: sudo rentalars restore FILE). State: the services and timers of Rentalars are stopped but still enabled; files, configuration and backups are untouched. To delete the rest: start the command again. To bring Rentalars back (only after the restore): $(restart_hint).")"
    rm -f "${client}"
}

remove_service_user() {
    # Members of the group keep userdel from removing it: www-data was added by the installer.
    gpasswd -d www-data "${SERVICE_USER}" > /dev/null 2>&1 || true
    userdel "${SERVICE_USER}" > /dev/null 2>&1 || problem "$(t "Das Konto ${SERVICE_USER} ließ sich nicht entfernen (läuft noch ein Prozess von ihm?)." "The account ${SERVICE_USER} could not be removed (does a process of it still run?).")"
    if getent group "${SERVICE_USER}" > /dev/null 2>&1; then
        groupdel "${SERVICE_USER}" > /dev/null 2>&1 || problem "$(t "Die Gruppe ${SERVICE_USER} ließ sich nicht entfernen." "The group ${SERVICE_USER} could not be removed.")"
    fi
}

# --- A last backup -----------------------------------------------------------------------------------------------------

final_backup_wanted=false
final_backup_dir=""
final_backup_target=""     # the folder for the copy, absolute and without links (readlink -f)

# Decide about the last backup before anything is asked about the purge itself.
decide_final_backup() {
    ${no_final_backup} && return 0
    if [[ ! -f "${program_dir}/deploy/backup.sh" || ! -f "${conf_file}" ]]; then
        # The program or the configuration is gone already (a purge after --keep-data): there is nothing to write a backup with.
        if [[ -n "${backup_to}" ]]; then
            fail "$(t "Das Programm ist schon entfernt (${APP_DIR}/deploy/backup.sh fehlt): eine letzte Sicherung ist nicht mehr möglich. Die vorhandenen Sicherungen liegen in ${backup_dir}; hol sie dir, oder lösche ohne: --no-final-backup. Es wurde nichts verändert." "The program is removed already (${APP_DIR}/deploy/backup.sh is missing): a last backup is no longer possible. The existing backups are in ${backup_dir}; get them, or delete without: --no-final-backup. Nothing was changed.")"
        fi
        local fate_de="bleiben unberührt" fate_en="are not touched"
        if ${BACKUPS_REMOVED}; then fate_de="werden mit gelöscht" fate_en="are deleted too"; fi
        warn "$(t "Das Programm ist schon entfernt: eine letzte Sicherung ist nicht mehr möglich. Die vorhandenen Sicherungen unter ${backup_dir} ${fate_de}." "The program is removed already: a last backup is no longer possible. The backups in ${backup_dir} ${fate_en}.")"
        return 0
    fi
    if [[ -n "${backup_to}" ]]; then
        final_backup_wanted=true final_backup_dir="${backup_to}"
    elif interactive && ! ${delete_everything}; then
        local answer proposal
        proposal="$(at_root /root)" && proposal="${proposal#"${TEST_ROOT}"}"
        note ""
        ask "$(t "Vorher eine letzte Sicherung schreiben und nach ${proposal} kopieren? [J/n] " "Write a last backup first and copy it to ${proposal}? [Y/n] ")"
        if [[ -z "${answer}" || "${answer}" =~ ^[JjYy] ]]; then
            final_backup_wanted=true final_backup_dir="${proposal}"
        else
            warn "$(t "Es wird keine letzte Sicherung geschrieben." "No last backup is written.")"
        fi
    else
        warn "$(t "Es wird keine letzte Sicherung geschrieben (mit --backup-to ORDNER würde eine geschrieben)." "No last backup is written (with --backup-to FOLDER one would be).")"
    fi
    if ${final_backup_wanted}; then
        local target planned real
        [[ -d "$(at_root "${final_backup_dir}")" ]] || fail "$(t "Der Ordner ${final_backup_dir} für die letzte Sicherung gibt es nicht. Es wurde nichts verändert." "The folder ${final_backup_dir} for the last backup does not exist. Nothing was changed.")"
        target="$(readlink -f -- "$(at_root "${final_backup_dir}")")"
        final_backup_target="${target}"
        for planned in "${REMOVE_PATHS[@]}"; do
            real="$(readlink -f -- "${planned}")"
            if [[ "${target}" == "${real}" || "${target}" == "${real}/"* ]]; then
                fail "$(t "Der Ordner ${final_backup_dir} liegt in ${planned}, das gelöscht wird. Bitte einen anderen wählen. Es wurde nichts verändert." "The folder ${final_backup_dir} lies in ${planned}, which is removed. Please choose another. Nothing was changed.")"
            fi
        done
    fi
}

make_final_backup() {
    ${final_backup_wanted} || return 0
    local written copy
    say "$(t "Letzte Sicherung" "Last backup")"
    written="$(bash "${program_dir}/deploy/backup.sh" --keep | tail -n 1)" \
        || fail "$(t "Die letzte Sicherung ist fehlgeschlagen. Es wurde nichts verändert. Behebe die Ursache oder lösche ohne sie: --no-final-backup" "The last backup failed. Nothing was changed. Fix the cause, or delete without it: --no-final-backup")"
    [[ -f "${written}" ]] || written="$(at_root "${written}")"
    [[ -f "${written}" ]] || fail "$(t "Die Sicherung ${written} gibt es nicht. Es wurde nichts verändert." "The backup ${written} does not exist. Nothing was changed.")"
    copy="${final_backup_target}/$(basename "${written}")"   # (uninstall; NFA-078) the absolute place, never the folder as typed
    install -m 600 -o root -g root "${written}" "${copy}" 2> /dev/null || install -m 600 "${written}" "${copy}"
    cmp -s "${written}" "${copy}" || fail "$(t "Die Kopie ${copy} weicht von der Sicherung ab. Es wurde nichts verändert." "The copy ${copy} differs from the backup. Nothing was changed.")"
    note "$(t "Die letzte Sicherung liegt in:" "The last backup is in:") ${copy#"${TEST_ROOT}"}"
    LAST_BACKUP="${copy#"${TEST_ROOT}"}"
    if ${encrypted_backups}; then
        note "$(t "Sie ist verschlüsselt: zum Öffnen brauchst du den Wiederherstellungsschlüssel, der mit gelöscht wird – hol ihn jetzt (sudo rentalars encryption show-key)." "It is encrypted: to open it you need the recovery key, which is deleted too – get it now (sudo rentalars encryption show-key).")"
    fi
}
LAST_BACKUP=""

# Asks a question at the terminal and puts the answer in "answer". The question is written to standard error
# whether or not there is a terminal, so that it shows in the output of a script and of a test.
ask() {
    printf '    %s' "$1" >&2
    answer=""
    read -r answer || true
}

# --- Asking -----------------------------------------------------------------------------------------------------------

confirm_keep_data() {
    local answer
    ${assume_yes} && return 0
    interactive || fail "$(t "Ohne Terminal fragt das Skript nicht: bitte --yes angeben. Es wurde nichts verändert." "Without a terminal the script does not ask: please give --yes. Nothing was changed.")"
    note ""
    note "$(t "Rentalars ist danach nicht mehr erreichbar. Die Daten bleiben." "Rentalars cannot be reached afterwards. The data stays.")"
    ask "$(t "Die Anwendung jetzt entfernen? [j/N] " "Remove the application now? [y/N] ")"
    [[ "${answer}" =~ ^[JjYy] ]] || fail "$(t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed.")"
}

confirm_purge() {
    local phrase answer
    if ${delete_everything}; then
        note ""
        warn "$(t "--yes-i-really-want-to-delete-everything ist angegeben: Es wird nicht gefragt." "--yes-i-really-want-to-delete-everything is given: nothing is asked.")"
        return 0
    fi
    interactive || fail "$(t "Ohne Terminal löscht das Skript nichts. Zum Löschen in einem Skript: --yes-i-really-want-to-delete-everything. Es wurde nichts verändert." "Without a terminal the script deletes nothing. To delete from a script: --yes-i-really-want-to-delete-everything. Nothing was changed.")"
    phrase="${host_name:-PURGE}"
    note ""
    note "$(t "ACHTUNG: Das löscht die Daten von Rentalars endgültig – Datenbank, Dateien, Sicherungen, Konfiguration." "WARNING: This deletes the data of Rentalars for good – database, files, backups, configuration.")"
    note "$(t "Es gibt kein Zurück, außer mit einer Sicherung, die du außerhalb dieses Servers hast." "There is no way back, except with a backup that you have outside this server.")"
    ask "$(t "Zur Bestätigung tippe genau: ${phrase}    " "To confirm, type exactly: ${phrase}    ")"
    [[ "${answer}" == "${phrase}" ]] || fail "$(t "Das ist nicht ${phrase}. Abgebrochen. Es wurde nichts verändert." "That is not ${phrase}. Cancelled. Nothing was changed.")"
}

# --- Running -----------------------------------------------------------------------------------------------------------

work="$(mktemp -d)"
build_plan

nothing_to_do=false
if ((${#REMOVE_PATHS[@]} == 0)) && [[ -z "${STOP_NOTE}${CERTIFICATE_NAME}" && "${DATABASE_ACTION}" == none ]] && ! ${USER_REMOVE}; then
    nothing_to_do=true
fi

if ${nothing_to_do}; then
    say "$(t "Hier ist nichts von Rentalars zu entfernen – nichts zu tun." "There is nothing of Rentalars to remove here – nothing to do.")"
    ${dry_run} && note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
    exit 0
fi

print_plan

if ${dry_run}; then
    note ""
    note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
    exit 0
fi

# Before anything is changed: what the run needs must be there.
if [[ "${DATABASE_ACTION}" != none ]]; then
    if [[ "${DATABASE_ACTION}" == drop-local ]]; then
        mariadb --batch --skip-column-names --connect-timeout=10 -e "SELECT 1" > /dev/null 2>&1 \
            || fail "$(t "MariaDB auf diesem Server antwortet nicht; die Datenbank ließe sich nicht löschen. Bitte starten (sudo systemctl start mariadb) und noch einmal versuchen. Es wurde nichts verändert." "MariaDB on this server does not answer; the database could not be dropped. Please start it (sudo systemctl start mariadb) and try again. Nothing was changed.")"
    else
        database_answers || fail "$(t "Die Datenbank ${db_name} auf ${db_where} antwortet nicht; ihre Tabellen ließen sich nicht löschen. Es wurde nichts verändert." "The database ${db_name} on ${db_where} does not answer; its tables could not be dropped. Nothing was changed.")"
    fi
fi

if [[ "${mode}" == purge ]]; then
    decide_final_backup
    confirm_purge
    make_final_backup
else
    confirm_keep_data
fi

# (uninstall; NFA-078) From here on the run is not to be cut short by a closing terminal: SIGHUP is ignored (the commands
# started below inherit that, so a DROP DATABASE is not killed with the connection to a terminal). INT and TERM end the run at
# once with a clear text and status 1 – every step is safe to repeat, the plan is made from what is still there.
# shellcheck disable=SC2317  # run by the trap
interrupted() {
    trap '' INT TERM
    printf '\n\033[1;31m%s\033[0m %s\n' "$(t "Abgebrochen mitten in der Entfernung –" "Cancelled in the middle of the removal –")" \
        "$(t "starte den Befehl erneut (ist der Befehl \"rentalars\" schon weg: aus dem entpackten Paket, sudo ./deploy/uninstall.sh …). Er macht mit dem weiter, was noch da ist." "start the command again (if the command \"rentalars\" is gone already: from the unpacked package, sudo ./deploy/uninstall.sh …). It carries on with what is still there.")" >&2
    exit 1
}
trap '' HUP
trap interrupted INT TERM

say "$(t "Entferne" "Removing")"
# 1. Nobody uses the application any more. Stopped only – disabling comes after the database step.
if ((${#UNITS[@]} > 0)); then note "$(t "Dienste und Zeitpläne anhalten …" "Stopping services and timers …")"; fi
stop_units
if ((${#STILL_ACTIVE[@]} > 0)); then
    if [[ "${mode}" == purge ]]; then
        fail "$(t "Nach \"systemctl stop\" laufen noch: ${STILL_ACTIVE[*]}. Zustand: Es wurde nichts entfernt und die Datenbank nicht angefasst; die übrigen Einheiten sind angehalten, aber noch eingeschaltet. Bitte die laufenden Einheiten von Hand beenden (sudo systemctl stop ${STILL_ACTIVE[*]}; Ursache: journalctl -u ${STILL_ACTIVE[0]}) und den Befehl noch einmal starten. Oder Rentalars wieder in Betrieb nehmen: $(restart_hint)." "After \"systemctl stop\" still running: ${STILL_ACTIVE[*]}. State: nothing was removed and the database was not touched; the other units are stopped but still enabled. Please end the running units by hand (sudo systemctl stop ${STILL_ACTIVE[*]}; cause: journalctl -u ${STILL_ACTIVE[0]}) and start the command again. Or bring Rentalars back: $(restart_hint).")"
    fi
    problem "$(t "Nach \"systemctl stop\" laufen noch: ${STILL_ACTIVE[*]}. Sie werden trotzdem abgeschaltet und ihre Dateien entfernt; von Hand anhalten: sudo systemctl stop ${STILL_ACTIVE[*]}" "After \"systemctl stop\" still running: ${STILL_ACTIVE[*]}. They are disabled and their files removed all the same; stop them by hand: sudo systemctl stop ${STILL_ACTIVE[*]}")"
fi
# 2. The data base first: if that fails, the configuration is still there and the run can be repeated.
case "${DATABASE_ACTION}" in
    drop-local) note "$(t "Datenbank ${db_name} löschen …" "Dropping the database ${db_name} …")"; drop_local_database ;;
    empty-remote) note "$(t "Tabellen von ${db_name} auf ${db_where} löschen …" "Dropping the tables of ${db_name} on ${db_where} …")"; empty_remote_database ;;
esac
# 2b. Only now the units are switched off for good.
if ((${#UNITS[@]} > 0)); then note "$(t "Dienste und Zeitpläne abschalten …" "Disabling services and timers …")"; fi
disable_units
# 3. The paths, in the order of the plan; the configuration folder is last of the data.
note "$(t "Dateien und Ordner entfernen …" "Removing files and folders …")"
config_index=-1
for index in "${!REMOVE_PATHS[@]}"; do
    if [[ "${REMOVE_PATHS[index]}" == "${conf_dir}" ]]; then config_index="${index}"; continue; fi
    remove_path "${REMOVE_PATHS[index]}"
done
forget_units
if [[ -n "${CERTIFICATE_NAME}" ]]; then
    certbot delete --non-interactive --cert-name "${CERTIFICATE_NAME}" > /dev/null 2>&1 \
        || problem "$(t "Das Zertifikat ${CERTIFICATE_NAME} ließ sich nicht löschen. Von Hand: certbot delete --cert-name ${CERTIFICATE_NAME}" "The certificate ${CERTIFICATE_NAME} could not be deleted. By hand: certbot delete --cert-name ${CERTIFICATE_NAME}")"
fi
# NGINX only if something of it was touched.
for path in "${REMOVE_PATHS[@]}"; do
    case "${path}" in
        "${site_file}"|"$(at_root "${NGINX_SITE_LINK}")"|"$(at_root "${NGINX_PROXY_SNIPPET}")"|"$(at_root "${NGINX_REALIP_SNIPPET}")") NGINX_TOUCHED=true ;;
    esac
done
if ${NGINX_TOUCHED}; then
    note "$(t "NGINX prüfen und neu laden …" "Testing and reloading NGINX …")"
    reload_nginx
fi
if ${USER_REMOVE}; then
    note "$(t "Systemkonto ${SERVICE_USER} entfernen …" "Removing the system account ${SERVICE_USER} …")"
    remove_service_user
fi
if ((config_index >= 0)); then
    remove_path "${REMOVE_PATHS[config_index]}"
fi

# --- Summary -------------------------------------------------------------------------------------------------------------

say "$(t "Zusammenfassung" "Summary")"
if ((${#problems[@]} > 0)); then
    note "$(t "Nicht alles ließ sich entfernen (siehe die Hinweise oben):" "Not everything could be removed (see the warnings above):")"
    for line in "${problems[@]}"; do note "  - ${line}"; done
    note ""
fi
if [[ "${mode}" == keep ]]; then
    if ((${#LINKED_TARGETS[@]} > 0)); then
        note "$(t "Rentalars ist abgeschaltet; die Daten sind noch da – und nicht alles ist weg:" "Rentalars is switched off; the data is still there – and not everything is gone:")"
        for line in "${LINKED_TARGETS[@]}"; do note "  - ${line}"; done
        note ""
    fi
    note "$(t "Rentalars ist entfernt; die Daten sind noch da:" "Rentalars is removed; the data is still there:")"
    for index in "${!KEEP_TEXTS[@]}"; do
        row 32 "${KEEP_LABELS[index]}" "${KEEP_TEXTS[index]}"
    done
    note ""
    note "$(t "Wieder in Betrieb nehmen, auf den vorhandenen Daten:" "Setting Rentalars up again on top of the data:")"
    if [[ "$(operator_language)" == de ]]; then
        note "  1. Der Installer verweigert sich, solange ${CONFIG_FILE} da ist. Leg den Ordner beiseite"
        note "     (eigene Zertifikate liegen dann in ${CONFIG_DIR}.behalten/tls/):"
        note "         sudo mv ${CONFIG_DIR} ${CONFIG_DIR}.behalten"
        note "  2. Das Paket entpacken (dieselbe Version wie vorher oder eine neuere) und installieren:"
        note "         sudo ./deploy/install.sh --domain ${host_name:-NAME} …"
        note "     Eine Datenbank auf diesem Server bleibt mit ihren Tabellen erhalten. Liegt sie auf einem"
        note "     anderen Server, verlangt der Installer eine leere Datenbank: leere sie vorher und spiel die"
        note "     Daten mit Schritt 3 ein. Die Ersteinrichtung im Browser überspringst du."
        note "  3. Falls die Daten nicht schon in der Datenbank stehen: die jüngste Sicherung einspielen:"
        note "         sudo rentalars restore ${backup_dir}/DATEI"
        note "  4. Den geheimen Schlüssel (secret_key) aus ${CONFIG_DIR}.behalten/rentalars.conf in die neue"
        note "     ${CONFIG_DIR}/rentalars.conf übernehmen, damit Anmeldungen und gespeicherte Passwörter"
        note "     weiter gelten; dann: sudo systemctl restart ${SERVICE_NAME}"
        note "  5. War die Verschlüsselung an: MariaDB hat Schlüssel und Einstellungen behalten. Danach:"
        note "         sudo rentalars encryption enable"
        note "     (der Wiederherstellungsschlüssel liegt in ${CONFIG_DIR}.behalten/recovery-key)"
        note ""
        note "Ganz entfernen, auch die Daten: sudo ./deploy/uninstall.sh --purge   (den Befehl \"rentalars\" gibt es nicht mehr)"
    else
        note "  1. The installer refuses while ${CONFIG_FILE} is there. Put the folder aside"
        note "     (own certificates are then in ${CONFIG_DIR}.kept/tls/):"
        note "         sudo mv ${CONFIG_DIR} ${CONFIG_DIR}.kept"
        note "  2. Unpack the package (the same version as before, or a newer one) and install:"
        note "         sudo ./deploy/install.sh --domain ${host_name:-NAME} …"
        note "     A database on this server stays with its tables. If it lies on another server, the"
        note "     installer wants an empty database: empty it first and put the data back with step 3."
        note "     You skip the first-run setup in the browser."
        note "  3. If the data is not in the database already: restore the newest backup:"
        note "         sudo rentalars restore ${backup_dir}/FILE"
        note "  4. Take the secret key (secret_key) from ${CONFIG_DIR}.kept/rentalars.conf into the new"
        note "     ${CONFIG_DIR}/rentalars.conf, so that logins and stored passwords stay valid;"
        note "     then: sudo systemctl restart ${SERVICE_NAME}"
        note "  5. If encryption was on: MariaDB kept its key and settings. Afterwards:"
        note "         sudo rentalars encryption enable"
        note "     (the recovery key is in ${CONFIG_DIR}.kept/recovery-key)"
        note ""
        note "To remove everything, the data as well: sudo ./deploy/uninstall.sh --purge   (the command \"rentalars\" is gone)"
    fi
else
    if ((${#LINKED_TARGETS[@]} > 0)); then
        # (uninstall; NFA-078) A link was removed, not its target: do not claim the data is gone.
        note "$(t "Rentalars ist abgeschaltet, aber NICHT alle Daten sind weg – von Links wurde nur der Link entfernt, das Ziel bleibt:" "Rentalars is switched off, but NOT all data is gone – of links only the link was removed, the target stays:")"
        for line in "${LINKED_TARGETS[@]}"; do note "  - ${line}"; done
    else
        note "$(t "Rentalars ist von diesem Server entfernt, mit seinen Daten." "Rentalars is removed from this server, with its data.")"
    fi
    [[ -z "${LAST_BACKUP}" ]] || note "$(t "Die letzte Sicherung:" "The last backup:") ${LAST_BACKUP}"
    if ((${#KEEP_TEXTS[@]} > 0)); then
        note ""
        note "$(t "Geblieben ist:" "What remains:")"
        for index in "${!KEEP_TEXTS[@]}"; do
            row 32 "${KEEP_LABELS[index]}" "${KEEP_TEXTS[index]}"
        done
    fi
fi
note ""
note "$(t "Für dich zum Prüfen (das Skript fasst es nie an):" "For you to check (the script never touches it):")"
for line in "${BY_HAND[@]}"; do note "  - ${line}"; done
if ((${#problems[@]} > 0)); then
    exit 1
fi
exit 0
