#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – restore a backup (NFA-015).
#
#   sudo rentalars restore /var/backups/rentalars/rentalars-2026-10-10_023000.tar.gz
#
# This REPLACES the database and the uploaded files with the state of the
# backup. Everything entered since the backup was made is lost. The script
# therefore makes a backup of the current state first and asks before it
# changes anything.
#
# The configuration file is NOT replaced. It is part of the backup so that a
# completely new server can be set up from it; see docs/betrieb/sicherung.md,
# "Umzug auf einen neuen Server".
#
# An encrypted backup (….tar.gz.enc, NFA-067) is decrypted with the recovery
# key of this server. A backup from another server – after a move, or after
# the server was set up again – needs that server's key: it is asked for, or
# given with --key-file.
#
# Options:
#   --key-file FILE     a file with the recovery key of an encrypted backup
#   --yes               do not ask (for scripts)
#   --no-safety-backup  skip the backup of the current state, e.g. when the
#                       current database is damaged and cannot be dumped
#   --data-only         put database and files back, but neither bring the
#                       database to the state of the installed program nor
#                       start Rentalars. Used by the update when the installed
#                       program cannot run on this system (see update.sh).
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

require_root

archive=""
key_file=""
assume_yes=false
safety_backup=true
data_only=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --key-file) key_file="${2:-}"; shift ;;
        --yes) assume_yes=true ;;
        --no-safety-backup) safety_backup=false ;;
        --data-only) data_only=true ;;
        -*) fail "$(t "Unbekannte Option: $1" "Unknown option: $1")" ;;
        *) archive="$1" ;;
    esac
    shift
done
[[ -n "${archive}" ]] || fail "$(t "Bitte die Sicherungsdatei angeben: sudo rentalars restore DATEI.tar.gz" "Please give the backup file: sudo rentalars restore FILE.tar.gz")"
[[ -f "${archive}" ]] || fail "$(t "Die Datei ${archive} gibt es nicht." "The file ${archive} does not exist.")"
[[ -f "${CONFIG_FILE}" ]] || fail "$(t "${CONFIG_FILE} fehlt. Ist Rentalars installiert?" "${CONFIG_FILE} is missing. Is Rentalars installed?")"
[[ -z "${key_file}" || -f "${key_file}" ]] || fail "$(t "Die Schlüsseldatei ${key_file} gibt es nicht." "The key file ${key_file} does not exist.")"

data_dir="$(config_get rentalars data_dir "${DEFAULT_DATA_DIR}")"
database="$(config_get database name rentalars)"

# Unpack in the folder of the backups, not in /tmp: since Ubuntu 24.10 /tmp lives in the main memory, and a backup
# with many uploaded files does not belong there. Not in the data folder either (S6): that belongs to the
# service account, which could exchange the working folder for a link while this script – as root – writes the decrypted
# archive and the key into it. The folder of the backups is root's.
backup_dir="$(config_get backup directory "${DEFAULT_BACKUP_DIR}")"
mkdir -p "${backup_dir}"
# Check before anything is done to it: a folder of the service account is not a place to unpack in as root.
[[ "$(stat -c %u "${backup_dir}")" == 0 ]] || fail "$(t "Der Ordner ${backup_dir} gehört nicht root; dorthin wird nichts entpackt." "The folder ${backup_dir} does not belong to root; nothing is unpacked there.")"
chmod 700 "${backup_dir}"
work="$(mktemp -d "${backup_dir}/.restore.XXXXXX")"
trap 'rm -rf "${work}"' EXIT

# An encrypted backup is decrypted first – with the given key, the key of
# this server, or the key typed in.
if is_encrypted_file "${archive}"; then
    decrypted=false
    try_key() {
        local normalized
        normalized="$(normalize_recovery_key "$1")" || return 1
        ( umask 077; printf '%s\n' "${normalized}" > "${work}/key" )
        decrypt_stream "${work}/key" < "${archive}" > "${work}/archive.tar.gz" 2> /dev/null \
            && gzip -t "${work}/archive.tar.gz" 2> /dev/null
    }
    if [[ -n "${key_file}" ]]; then
        try_key "$(head -n 1 "${key_file}")" \
            || fail "$(t "Mit dem Schlüssel aus ${key_file} lässt sich die Sicherung nicht entschlüsseln." "The key in ${key_file} does not decrypt the backup.")"
        decrypted=true
    elif [[ -f "${RECOVERY_KEY_FILE}" ]] && try_key "$(head -n 1 "${RECOVERY_KEY_FILE}")"; then
        decrypted=true
    elif [[ -t 0 ]]; then
        note "$(t "Die Sicherung ist verschlüsselt, und der Schlüssel dieses Servers passt nicht zu ihr." "The backup is encrypted, and the key of this server does not fit it.")"
        for attempt in 1 2 3; do
            read -r -s -p "    $(t "Wiederherstellungsschlüssel der Sicherung: " "Recovery key of the backup: ")" typed
            echo
            if try_key "${typed}"; then decrypted=true; break; fi
            note "$(t "Dieser Schlüssel passt nicht (Versuch ${attempt} von 3)." "This key does not fit (attempt ${attempt} of 3).")"
        done
    fi
    ${decrypted} || fail "$(t "Die Sicherung ist verschlüsselt, und kein Schlüssel passt. Mit dem Wiederherstellungsschlüssel des Servers, der sie geschrieben hat: sudo rentalars restore ${archive} --key-file DATEI" "The backup is encrypted, and no key fits. With the recovery key of the server that wrote it: sudo rentalars restore ${archive} --key-file FILE")"
    # The key stays until the database is back: the dump inside is encrypted as well (database.sql.enc).
    note "$(t "Die Sicherung ist entschlüsselt." "The backup is decrypted.")"
    archive_label="${archive}"
    archive="${work}/archive.tar.gz"
else
    archive_label="${archive}"
fi

# Look into the archive before touching anything.
gzip -t "${archive}" || fail "$(t "Die Sicherungsdatei ist beschädigt." "The backup file is damaged.")"
contents="$(tar -tzf "${archive}")"
dump_name=""
if grep -qx "database.sql.enc" <<<"${contents}"; then dump_name="database.sql.enc"; elif grep -qx "database.sql" <<<"${contents}"; then dump_name="database.sql"; fi
[[ -n "${dump_name}" ]] || fail "$(t "Das ist keine Rentalars-Sicherung (database.sql fehlt)." "This is no Rentalars backup (database.sql is missing).")"
if [[ "${dump_name}" == "database.sql.enc" && ! -f "${work}/key" ]]; then
    # A backup whose outer encryption was taken off (rentalars encryption decrypt-backup) still holds the encrypted
    # dump: the key is taken from --key-file, else from this server.
    for candidate in "${key_file}" "${RECOVERY_KEY_FILE}"; do
        [[ -n "${candidate}" && -f "${candidate}" ]] || continue
        if normalized_key="$(normalize_recovery_key "$(head -n 1 "${candidate}")")"; then
            ( umask 077; printf '%s\n' "${normalized_key}" > "${work}/key" )
            break
        fi
    done
fi
if [[ "${dump_name}" == "database.sql.enc" && ! -f "${work}/key" ]]; then
    fail "$(t "In dieser Sicherung ist die Datenbank zusätzlich verschlüsselt, aber der Schlüssel fehlt. Es wurde nichts verändert." "The database in this backup is encrypted as well, but the key is missing. Nothing was changed.")"
fi
backup_version="$(tar -xzOf "${archive}" VERSION 2>/dev/null || t unbekannt unknown)"
installed_version="$(version_of "${APP_DIR}")"
# NFA-077: a backup of a version older than OLDEST_UPDATABLE_VERSION cannot be brought to this version any more (the older
# migrations are squashed, lib.sh) – refused before anything is touched.
if version_older "${backup_version}" "${OLDEST_UPDATABLE_VERSION}"; then
    fail "$(t "Diese Sicherung stammt von Rentalars ${backup_version}. Rentalars ${installed_version} spielt nur Sicherungen ab ${OLDEST_UPDATABLE_VERSION} ein. Es wurde nichts verändert." "This backup was written by Rentalars ${backup_version}. Rentalars ${installed_version} only restores backups of ${OLDEST_UPDATABLE_VERSION} or later. Nothing was changed.")"
fi

say "$(t "Wiederherstellung" "Restore")"
if [[ "$(operator_language)" == de ]]; then
    note "Sicherung:            ${archive_label}"
    note "geschrieben mit:      Rentalars ${backup_version}"
    note "installiert ist:      Rentalars ${installed_version}"
    if database_is_local; then
        note "Datenbank:            ${database} wird vollständig ersetzt"
    else
        note "Datenbank:            ${database} auf $(config_get database host) wird vollständig ersetzt"
    fi
    note "Dateien:              ${data_dir}/media wird vollständig ersetzt"
else
    note "Backup:               ${archive_label}"
    note "written by:           Rentalars ${backup_version}"
    note "installed is:         Rentalars ${installed_version}"
    if database_is_local; then
        note "Database:             ${database} is replaced completely"
    else
        note "Database:             ${database} on $(config_get database host) is replaced completely"
    fi
    note "Files:                ${data_dir}/media is replaced completely"
fi
if [[ "${backup_version}" != "${installed_version}" ]]; then
    note ""
    if [[ "$(operator_language)" == de ]]; then
        note "Die Versionen unterscheiden sich. Eine ältere Sicherung wird nach dem"
        note "Einspielen auf den Stand der installierten Version gebracht (migrate)."
        note "Eine NEUERE Sicherung passt nicht zu einem älteren Programm – dann"
        note "zuerst die passende Programmversion einspielen (rentalars update)."
    else
        note "The versions differ. An older backup is brought to the state of the"
        note "installed version after it was put back (migrate)."
        note "A NEWER backup does not fit an older program – then install the"
        note "matching version of the program first (rentalars update)."
    fi
fi
if ! ${assume_yes}; then
    read -r -p "    $(t "Jetzt wiederherstellen? Alles seit der Sicherung Eingegebene geht verloren. [ja/NEIN] " "Restore now? Everything entered since the backup is lost. [yes/NO] ")" answer
    [[ "${answer,,}" == "ja" || "${answer,,}" == "yes" ]] || fail "$(t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed.")"
fi

if ${safety_backup}; then
    say "$(t "Sichere zuerst den jetzigen Stand" "Backing up the current state first")"
    note "$("$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/backup.sh" --keep)"
fi

tar -xzf "${archive}" -C "${work}" "${dump_name}" media 2>/dev/null || tar -xzf "${archive}" -C "${work}" "${dump_name}"
rm -f "${work}/archive.tar.gz"
write_database_credentials "${work}/client.cnf"

say "$(t "Halte die Anwendung an" "Stopping the application")"
systemctl stop "${SERVICE_NAME}"

say "$(t "Spiele die Datenbank ein" "Putting the database back")"
# Empty the database first: tables that the backup does not know must not survive.
mariadb --defaults-extra-file="${work}/client.cnf" --batch --skip-column-names "${database}" \
    -e "SELECT CONCAT('DROP TABLE IF EXISTS \`', table_name, '\`;') FROM information_schema.tables WHERE table_schema = DATABASE();" \
    > "${work}/drop.sql"
{ echo "SET FOREIGN_KEY_CHECKS = 0;"; cat "${work}/drop.sql"; echo "SET FOREIGN_KEY_CHECKS = 1;"; } \
    | mariadb --defaults-extra-file="${work}/client.cnf" "${database}"
if [[ "${dump_name}" == "database.sql.enc" ]]; then
    # Decrypted on the way into the database – the plain dump is never written to the disk.
    decrypt_stream "${work}/key" < "${work}/${dump_name}" \
        | mariadb --defaults-extra-file="${work}/client.cnf" --default-character-set=utf8mb4 "${database}"
else
    mariadb --defaults-extra-file="${work}/client.cnf" --default-character-set=utf8mb4 "${database}" < "${work}/${dump_name}"
fi
rm -f "${work}/key"

say "$(t "Spiele die Dateien ein" "Putting the files back")"
# The data folder belongs to the service account (S6): everything that is done here to what stands in it is
# done without following a link – "mv -T" replaces a link itself, and the owner is set in the working folder, which
# is root's, before the files are moved to their place.
rm -rf "${data_dir}/media.before-restore"
[[ -d "${data_dir}/media" || -L "${data_dir}/media" ]] && mv -T "${data_dir}/media" "${data_dir}/media.before-restore"
[[ -d "${work}/media" ]] || mkdir -p "${work}/media"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${work}/media"
mv -T "${work}/media" "${data_dir}/media"
rm -rf "${data_dir}/media.before-restore"

if ${data_only}; then
    say "$(t "Fertig. Datenbank und Dateien haben den Stand der Sicherung; Rentalars ist angehalten." "Done. Database and files have the state of the backup; Rentalars is stopped.")"
    exit 0
fi

say "$(t "Bringe die Datenbank auf den Stand des installierten Programms" "Bringing the database to the state of the installed program")"
manage migrate --noinput

say "$(t "Starte die Anwendung" "Starting the application")"
systemctl start "${SERVICE_NAME}"

say "$(t "Fertig. Rentalars läuft mit dem Stand der Sicherung." "Done. Rentalars runs with the state of the backup.")"

# NFA-015: what a backup does not hold is said at the end – the file restores the data, not the whole server.
say "$(t "Nicht in der Sicherung – prüfe, ob es auf diesem Server eingerichtet ist:" "Not in the backup – check that this server has it set up:")"
echo "    $(t "- Zertifikate (/etc/rentalars/tls) und die NGINX-Site: bei einem neuen Server bei der Installation einrichten" "- Certificates (/etc/rentalars/tls) and the NGINX site: set up when installing a new server")"
if [[ ! -d /opt/rentalars/ai ]]; then
    echo "    $(t "- Lokale KI (/opt/rentalars/ai) ist hier nicht eingerichtet: sudo rentalars ai install" "- The local AI (/opt/rentalars/ai) is not set up here: sudo rentalars ai install")"
fi
if [[ ! -d /opt/rentalars/routes ]]; then
    echo "    $(t "- Routendienst (/opt/rentalars/routes) ist hier nicht eingerichtet: sudo rentalars route install" "- The route service (/opt/rentalars/routes) is not set up here: sudo rentalars route install")"
fi
echo "    $(t "- Geheimer Schlüssel: der Server behält seinen eigenen (rentalars.conf wird nicht ersetzt). Gespeicherte Passwörter, Zwei-Faktor-Anmeldungen und Webhook-Geheimnisse der Sicherung gelten nur mit dem Schlüssel aus der Sicherung (docs: Umzug auf einen neuen Server, Schritt 4)" "- Secret key: the server keeps its own (rentalars.conf is not replaced). Stored passwords, two-factor logins and webhook secrets of the backup only work with the key from the backup (docs: moving to a new server, step 4)")"
echo "    $(t "- Dateien, die vor weniger als 7 Tagen gelöscht wurden, liegen in media/.deleted der Sicherung und werden nach Ablauf der Frist entfernt" "- Files deleted less than 7 days before the backup are in media/.deleted of the backup and removed when their time is up")"
