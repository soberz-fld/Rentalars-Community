#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – move the database to another database (NFA-068).
#
#   sudo rentalars move-database --host db.example.de --name rentalars --user rentalars [options]
#   sudo rentalars move-database --local
#
# Moves all data into a new, empty database – on another MariaDB server, or
# back onto the MariaDB of this server – and connects Rentalars to it only
# after a check. Uses: a database server with encrypted storage, a central
# database server of the company, or the way back from one.
#
# What happens, in this order:
#
#   1. The new database is checked before anything is changed: it must be
#      empty, and its user must have all rights on it and NO others – root,
#      or any user with rights on the whole server or on further databases,
#      is refused (NFA-066).
#   2. A backup of the present state is written (never deleted automatically).
#   3. Rentalars is stopped. All data is copied into the new database.
#   4. Every table is compared – number of rows and a checksum over all
#      values. Only if not one value differs is the configuration switched to
#      the new database and Rentalars started again.
#   5. If anything fails, Rentalars starts again with the old database, as
#      before.
#
# The old database is NOT deleted. It stays as it was at the moment of the
# move, as a way back, until it is removed by hand (docs/betrieb/betrieb.md).
#
# Options for a database on another server:
#   --host HOST, --port PORT (3306), --name NAME, --user USER
#   --password-file FILE     the password in its first line; otherwise asked for,
#                            or taken from the variable RENTALARS_DB_PASSWORD
#   --tls-ca FILE            check the server's certificate against this CA
#   --no-tls                 do not encrypt the connection
# Options for a database on this server:
#   --local                  installs MariaDB if needed and creates database and user
#   --name NAME              the database to create (default: rentalars, or rentalars2
#                            if that is taken)
# Both:
#   --yes                    do not ask
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

require_root
[[ -f "${CONFIG_FILE}" && -L "${APP_DIR}" ]] || fail "$(t "Rentalars ist auf diesem Server nicht installiert." "Rentalars is not installed on this server.")"

target_local=false host="" port="" name="" user="" password_file="" tls="" tls_ca="" assume_yes=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --local) target_local=true; shift ;;
        --host) host="${2:-}"; shift 2 ;;
        --port) port="${2:-}"; shift 2 ;;
        --name) name="${2:-}"; shift 2 ;;
        --user) user="${2:-}"; shift 2 ;;
        --password-file) password_file="${2:-}"; shift 2 ;;
        --tls-ca) tls_ca="${2:-}"; tls=true; shift 2 ;;
        --no-tls) tls=false; shift ;;
        --yes) assume_yes=true; shift ;;
        -h|--help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "$(t "Unbekannte Option: $1 (Hilfe: rentalars move-database --help)" "Unknown option: $1 (help: rentalars move-database --help)")" ;;
    esac
done

old_database="$(config_get database name rentalars)"
old_host="$(config_get database host)"
old_label="${old_database} $(t "auf" "on") ${old_host:-$(t "diesem Server" "this server")}"

# --- 1. The new database ---------------------------------------------------------------------

if ${target_local}; then
    [[ -z "${host}${user}${password_file}${tls_ca}${port}" ]] || fail "$(t "--local verträgt sich nicht mit --host, --user, --password-file, --port und --tls-ca." "--local does not go with --host, --user, --password-file, --port and --tls-ca.")"
    if [[ -z "${name}" ]]; then
        name="rentalars"
        if database_is_local && [[ "${old_database}" == "rentalars" ]]; then name="rentalars2"; fi
    fi
    [[ "${name}" =~ ^[A-Za-z0-9_]+$ ]] || fail "$(t "'${name}' ist kein gültiger Name für die Datenbank (Buchstaben, Ziffern, _)." "'${name}' is no valid name for the database (letters, digits, _).")"
    if database_is_local && [[ "${name}" == "${old_database}" ]]; then
        fail "$(t "Das ist die Datenbank, die Rentalars schon verwendet." "That is the database Rentalars uses already.")"
    fi
    user="${name}"
else
    [[ -n "${host}" ]] || fail "$(t "Wohin? Bitte --host HOST angeben, oder --local für den MariaDB dieses Servers." "Where to? Please give --host HOST, or --local for the MariaDB of this server.")"
    [[ "${host}" =~ ^[A-Za-z0-9]([A-Za-z0-9.:-]*[A-Za-z0-9])?$ ]] || fail "$(t "'${host}' ist kein gültiger Hostname und keine IP-Adresse." "'${host}' is neither a valid host name nor an IP address.")"
    port="${port:-3306}"
    [[ "${port}" =~ ^[0-9]+$ ]] || fail "$(t "'${port}' ist kein gültiger Port." "'${port}' is no valid port.")"
    [[ -n "${name}" && -n "${user}" ]] || fail "$(t "Bitte --name DATENBANK und --user BENUTZER angeben." "Please give --name DATABASE and --user USER.")"
    [[ "${user,,}" != "root" ]] \
        || fail "$(t "Der Benutzer root wird nicht hinterlegt. Bitte auf dem Datenbankserver einen Benutzer anlegen, der nur Rechte auf die Datenbank ${name} hat." "The user root is not stored. Please create a user on the database server that has rights on the database ${name} only.")"
    if [[ "${host}" == "${old_host}" && "${name}" == "${old_database}" ]]; then
        fail "$(t "Das ist die Datenbank, die Rentalars schon verwendet." "That is the database Rentalars uses already.")"
    fi
    if [[ -n "${password_file}" ]]; then
        [[ -f "${password_file}" ]] || fail "$(t "Die Passwortdatei ${password_file} gibt es nicht." "The password file ${password_file} does not exist.")"
        password="$(head -n 1 "${password_file}")"
    elif [[ -n "${RENTALARS_DB_PASSWORD:-}" ]]; then
        password="${RENTALARS_DB_PASSWORD}"
    elif [[ -t 0 ]]; then
        read -r -s -p "$(t "Passwort von ${user}: " "Password of ${user}: ")" password
        echo
    else
        password=""
    fi
    [[ -n "${password}" ]] || fail "$(t "Bitte das Passwort angeben: --password-file DATEI" "Please give the password: --password-file FILE")"
    tls="${tls:-true}"
    if [[ -n "${tls_ca}" ]]; then
        [[ -f "${tls_ca}" ]] || fail "$(t "Das CA-Zertifikat ${tls_ca} gibt es nicht." "The CA certificate ${tls_ca} does not exist.")"
        openssl x509 -in "${tls_ca}" -noout > /dev/null 2>&1 || fail "$(t "${tls_ca} ist kein Zertifikat im PEM-Format." "${tls_ca} is no certificate in PEM format.")"
    fi
fi

work="$(mktemp -d "${RENTALARS_HOME}/.move.XXXXXX")"
chmod 700 "${work}"
new_config="${CONFIG_FILE}.new"
cleanup() { rm -rf "${work}"; rm -f "${new_config}"; }
trap cleanup EXIT

say "$(t "Prüfe die bisherige Datenbank" "Checking the database used so far")"
database_answers || fail "$(t "Die bisherige Datenbank (${old_label}) antwortet nicht. Ohne sie gibt es nichts umzuziehen." "The database used so far (${old_label}) does not answer. Without it there is nothing to move.")"
note "$(t "${old_label} antwortet." "${old_label} answers.")"

if ${target_local}; then
    say "$(t "Richte die neue Datenbank auf diesem Server ein" "Setting up the new database on this server")"
    if ! command -v mariadbd > /dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq --no-install-recommends mariadb-server > /dev/null
    fi
    [[ -f "${MARIADB_SETTINGS}" ]] || install -m 644 "${APP_DIR}/deploy/mariadb/60-rentalars.cnf" "${MARIADB_SETTINGS}"
    # Less memory for MariaDB on a Raspberry Pi with less than 4 GB; nothing elsewhere (NFA-070).
    write_database_memory_settings "${MARIADB_MEMORY_SETTINGS}" "$(device_model "${DEVICE_MODEL_FILE}")" "$(memory_mb "${MEMORY_INFO_FILE}")"
    systemctl enable --quiet mariadb
    systemctl is-active --quiet mariadb || systemctl start mariadb
    if [[ "$(mariadb --batch --skip-column-names -e "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = '${name}'")" != "0" ]]; then
        fail "$(t "Auf diesem Server gibt es die Datenbank ${name} schon. Bitte einen anderen Namen wählen: --name NAME" "The database ${name} exists on this server already. Please choose another name: --name NAME")"
    fi
    password="$(openssl rand -hex 24)"
    mariadb <<SQL
CREATE DATABASE \`${name}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '${user}'@'localhost' IDENTIFIED BY '${password}';
ALTER USER '${user}'@'localhost' IDENTIFIED BY '${password}';
GRANT ALL PRIVILEGES ON \`${name}\`.* TO '${user}'@'localhost';
FLUSH PRIVILEGES;
SQL
    host="" port="" tls=false tls_ca=""
    note "$(t "${name} mit dem Benutzer ${user} angelegt." "${name} created with the user ${user}.")"
fi

say "$(t "Prüfe die neue Datenbank" "Checking the new database")"
write_client_file "${work}/target.cnf" "${user}" "${password}" "${host}" "${port}" "${tls}" "${tls_ca}"
flags=(--require-empty --fix-charset --try-tables)
[[ "${tls}" == "true" ]] && flags+=(--expect-tls)
[[ -n "${tls_ca}" ]] && flags+=(--tls-verified)
check_status=0
check_database_account "${APP_DIR}" "${work}/target.cnf" "${name}" "${flags[@]}" | sed 's/^/    /' || check_status=${PIPESTATUS[0]}
[[ "${check_status}" -eq 0 ]] || fail "$(t "Diese Datenbank kann Rentalars nicht verwenden (siehe oben). Es wurde nichts verändert." "Rentalars cannot use this database (see above). Nothing was changed.")"

target_label="${name} $(t "auf" "on") ${host:-$(t "diesem Server" "this server")}"
say "$(t "Umzug der Datenbank" "Moving the database")"
note "$(t "von:   " "from:  ")${old_label}"
note "$(t "nach:  " "to:    ")${target_label}"
note ""
note "$(t "Rentalars ist während des Umzugs nicht erreichbar. Die bisherige Datenbank bleibt" "Rentalars cannot be reached during the move. The database used so far stays")"
note "$(t "unverändert erhalten, bis sie von Hand gelöscht wird." "unchanged until it is deleted by hand.")"
if ! ${assume_yes}; then
    read -r -p "    $(t "Jetzt umziehen? [J/n] " "Move now? [Y/n] ")" answer
    [[ -z "${answer}" || "${answer}" =~ ^[JjYy] ]] || fail "$(t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed.")"
fi

# --- 2. Backup ---------------------------------------------------------------------------------------

say "$(t "Sichere den jetzigen Stand" "Backing up the current state")"
backup_file="$(bash "${APP_DIR}/deploy/backup.sh" --keep)"
note "${backup_file}"

# --- 3. Copy ---------------------------------------------------------------------------------------------

say "$(t "Halte Rentalars an und kopiere die Daten" "Stopping Rentalars and copying the data")"
stop_rentalars
restart_old() {
    start_rentalars
    application_answers || note "$(t "Achtung: Rentalars antwortet auch mit der bisherigen Datenbank nicht: journalctl -u rentalars" "Warning: Rentalars does not answer with the database used so far either: journalctl -u rentalars")"
}
write_database_credentials "${work}/source.cnf"
# Straight from the old into the new database – no dump file on the disk (it would be unencrypted data
# lying around, whatever the backups are). With pipefail a dump that fails half-way fails the whole line.
if ! mariadb-dump --defaults-extra-file="${work}/source.cnf" \
        --single-transaction --routines --triggers --default-character-set=utf8mb4 \
        "${old_database}" \
    | mariadb --defaults-extra-file="${work}/target.cnf" --default-character-set=utf8mb4 "${name}"; then
    restart_old
    fail "$(t "Die Daten ließen sich nicht vollständig in ${target_label} schreiben (siehe oben). Rentalars läuft wieder mit der bisherigen Datenbank. Die neue ist nun teilweise gefüllt; bitte dort leeren, bevor es noch einmal versucht wird." "The data could not be written completely into ${target_label} (see above). Rentalars runs with the database used so far again. The new one is partly filled now; please empty it before trying once more.")"
fi
note "$(t "Kopiert." "Copied.")"

# --- 4. Compare, then switch ---------------------------------------------------------------------------------

say "$(t "Vergleiche jede Tabelle" "Comparing every table")"
cp -p "${CONFIG_FILE}" "${new_config}"
if [[ -n "${tls_ca}" && "${tls_ca}" != "${CONFIG_DIR}/"* ]]; then
    install -m 640 -o root -g "${SERVICE_USER}" "${tls_ca}" "${CONFIG_DIR}/database-ca-${name}.pem"
    tls_ca="${CONFIG_DIR}/database-ca-${name}.pem"
fi
config_set "${new_config}" database name "${name}"
config_set "${new_config}" database user "${user}"
config_set "${new_config}" database password "${password}"
config_set "${new_config}" database host "${host}"
config_set "${new_config}" database port "${port}"
config_set "${new_config}" database tls "${tls}"
config_set "${new_config}" database tls_ca "${tls_ca}"

manage database_fingerprint > "${work}/before.json"
if ! manage_with_config "${new_config}" database_fingerprint > "${work}/after.json" \
    || ! compare_fingerprints "${work}/before.json" "${work}/after.json"; then
    restart_old
    fail "$(t "Die Kopie stimmt nicht mit dem Original überein (siehe oben). Rentalars läuft wieder mit der bisherigen Datenbank; nichts wurde umgestellt." "The copy does not match the original (see above). Rentalars runs with the database used so far again; nothing was switched.")"
fi

say "$(t "Stelle auf die neue Datenbank um" "Switching to the new database")"
previous_config="${CONFIG_FILE}.before-move-$(date +%Y%m%d-%H%M%S)"
cp -p "${CONFIG_FILE}" "${previous_config}"
chmod 600 "${previous_config}"
mv "${new_config}" "${CONFIG_FILE}"
protect_configuration "${CONFIG_FILE}"
start_rentalars
if ! application_answers; then
    systemctl stop "${SERVICE_NAME}"
    cp -p "${previous_config}" "${CONFIG_FILE}"
    protect_configuration "${CONFIG_FILE}"
    restart_old
    fail "$(t "Rentalars startet mit der neuen Datenbank nicht (journalctl -u rentalars). Es läuft wieder mit der bisherigen; nichts ist verloren." "Rentalars does not start with the new database (journalctl -u rentalars). It runs with the one used so far again; nothing is lost.")"
fi

say "$(t "Fertig. Rentalars arbeitet jetzt mit ${target_label}." "Done. Rentalars works with ${target_label} now.")"
note "$(t "Sicherung von vorher:            " "Backup from before:              ")${backup_file}"
note "$(t "Konfiguration von vorher:        " "Configuration from before:       ")${previous_config}"
note "$(t "Die bisherige Datenbank ${old_label} ist unverändert und wird nicht mehr" "The database used so far, ${old_label}, is unchanged and no longer")"
note "$(t "benutzt. Wenn alles läuft, kann sie gelöscht werden (docs/betrieb/betrieb.md)." "used. When everything runs, it can be deleted (docs/en/operations/operation.md).")"
