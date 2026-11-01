#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – encryption of database and backups (NFA-067).
#
#   sudo rentalars encryption status              what is encrypted, and with which key
#   sudo rentalars encryption enable              switch encryption on afterwards
#   sudo rentalars encryption show-key            show the recovery key again
#   sudo rentalars encryption decrypt-backup FILE [--key-file KEYFILE]
#                                                 write a decrypted copy of a backup
#
# One secret opens everything: the recovery key. It encrypts the backups and
# locks the key with which the MariaDB on this server encrypts its files.
# Whoever is root on the server, or holds the written-down key, can decrypt –
# with Rentalars or with nothing but openssl (docs/betrieb/verschluesselung.md).
#
# "enable" on a server with its own MariaDB:
#
#   1. writes a backup of the present state (kept, never deleted automatically),
#   2. stops Rentalars and takes a fingerprint of every table,
#   3. gives MariaDB its key and restarts it; MariaDB then encrypts every
#      table file in the background – page by page, under its own crash-safe
#      bookkeeping, the same as it does with every other change,
#   4. waits until every table is encrypted, takes the fingerprint again and
#      compares: Rentalars only starts again if not one value differs,
#   5. encrypts the existing backups in the backup folder and switches
#      encryption on for all future backups.
#
# With a database on another server, encrypting its files is that server's
# matter: "enable" then encrypts the backups and says what it finds there.
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

require_root
[[ -f "${CONFIG_FILE}" ]] || fail "$(t "${CONFIG_FILE} fehlt. Ist Rentalars installiert?" "${CONFIG_FILE} is missing. Is Rentalars installed?")"

backup_dir="$(config_get backup directory "${DEFAULT_BACKUP_DIR}")"
database="$(config_get database name rentalars)"

# The tables of Rentalars that MariaDB has not encrypted yet (local database only).
unencrypted_tables() {
    mariadb --batch --skip-column-names -e "
        SELECT t.TABLE_NAME FROM information_schema.TABLES t
        LEFT JOIN information_schema.INNODB_TABLESPACES_ENCRYPTION e
               ON e.NAME = CONCAT(t.TABLE_SCHEMA, '/', t.TABLE_NAME)
        WHERE t.TABLE_SCHEMA = '${database}' AND t.ENGINE = 'InnoDB'
          AND (e.ENCRYPTION_SCHEME IS NULL OR e.ENCRYPTION_SCHEME = 0 OR e.KEY_ROTATION_PAGE_NUMBER IS NOT NULL)"
}

# The server's own account of a database elsewhere: one line.
remote_database_line() {
    local credentials
    credentials="$(mktemp)"
    write_database_credentials "${credentials}"
    check_database_account "${APP_DIR}" "${credentials}" "${database}" --brief || true
    rm -f "${credentials}"
}

show_status() {
    say "$(t "Verschlüsselung" "Encryption")"
    if database_is_local; then
        if mariadb_encryption_active; then
            local total open
            total="$(mariadb --batch --skip-column-names -e "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = '${database}' AND ENGINE = 'InnoDB'")"
            open="$(unencrypted_tables | wc -l)"
            row 28 "$(t "Datenbank" "Database")" "$(t "verschlüsselt ($((total - open)) von ${total} Tabellen)" "encrypted ($((total - open)) of ${total} tables)")"
        else
            row 28 "$(t "Datenbank" "Database")" "$(t "nicht verschlüsselt" "not encrypted")"
        fi
    else
        row 28 "$(t "Datenbank" "Database")" "$(t "auf" "on") $(config_get database host) – $(remote_database_line | head -n 1)"
    fi
    if backups_encrypted; then
        row 28 "$(t "neue Sicherungen" "new backups")" "$(t "verschlüsselt" "encrypted")"
    else
        row 28 "$(t "neue Sicherungen" "new backups")" "$(t "nicht verschlüsselt" "not encrypted")"
    fi
    local plain encrypted
    plain="$(find "${backup_dir}" -maxdepth 1 -type f -name 'rentalars-*.tar.gz' 2> /dev/null | wc -l)"
    encrypted="$(find "${backup_dir}" -maxdepth 1 -type f -name 'rentalars-*.tar.gz.enc' 2> /dev/null | wc -l)"
    row 28 "$(t "Sicherungen im Ordner" "backups in the folder")" "$(t "${encrypted} verschlüsselt, ${plain} unverschlüsselt" "${encrypted} encrypted, ${plain} not encrypted")"
    if [[ -f "${RECOVERY_KEY_FILE}" ]]; then
        row 28 "$(t "Wiederherstellungsschlüssel" "recovery key")" "${RECOVERY_KEY_FILE} ($(t "nur root" "root only"))"
    else
        row 28 "$(t "Wiederherstellungsschlüssel" "recovery key")" "$(t "keiner" "none")"
    fi
}

# Encrypt the unencrypted backups in the backup folder; each one is read back
# before the unencrypted file is removed. The date of the file stays, so that
# the tidy-up deletes it on the same day as before.
encrypt_existing_backups() {
    local file count=0
    while IFS= read -r file; do
        ( umask 077; encrypt_stream "${RECOVERY_KEY_FILE}" < "${file}" > "${file}.enc.partial" )
        decrypt_stream "${RECOVERY_KEY_FILE}" < "${file}.enc.partial" | cmp -s - "${file}" \
            || fail "$(t "Die Sicherung ${file} ließ sich nicht verschlüsselt prüfen; sie bleibt unverändert." "The backup ${file} could not be checked once encrypted; it stays as it was.")"
        touch -r "${file}" "${file}.enc.partial"
        mv "${file}.enc.partial" "${file}.enc"
        rm -f "${file}"
        count=$((count + 1))
    done < <(find "${backup_dir}" -maxdepth 1 -type f -name 'rentalars-*.tar.gz' | sort)
    note "$(t "${count} vorhandene Sicherung(en) verschlüsselt." "${count} existing backup(s) encrypted.")"
    update_backup_status
}

# The record of the last backup for the self-check (written by backup.sh)
# names a file that is now encrypted: point it to the encrypted one.
update_backup_status() {
    local status_file
    status_file="$(config_get rentalars data_dir "${DEFAULT_DATA_DIR}")/backup-status.json"
    [[ -f "${status_file}" ]] || return 0
    python3 - "${status_file}" <<'PYTHON'
import json
import os
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as handle:
    status = json.load(handle)
name = status.get("file", "")
if name and not name.endswith(".enc") and os.path.exists(name + ".enc"):
    status.update(file=name + ".enc", size=os.path.getsize(name + ".enc"), encrypted=True)
    # The folder belongs to the service user – a link laid at the new name must not be followed (O_EXCL).
    new = path + ".new"
    if os.path.lexists(new):
        os.unlink(new)
    descriptor = os.open(new, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(status, handle)
        handle.write("\n")
    os.replace(new, path)
PYTHON
}

enable() {
    local assume_yes=false
    [[ "${1:-}" == "--yes" ]] && assume_yes=true
    local local_database=false
    database_is_local && local_database=true

    if backups_encrypted && { ! ${local_database} || mariadb_encryption_active; }; then
        show_status
        say "$(t "Die Verschlüsselung ist schon eingeschaltet." "Encryption is switched on already.")"
        return 0
    fi

    say "$(t "Verschlüsselung einschalten" "Switching encryption on")"
    if ${local_database}; then
        if [[ "$(operator_language)" == de ]]; then
            note "MariaDB auf diesem Server verschlüsselt seine Dateien, alle Sicherungen werden"
            note "verschlüsselt – auch die vorhandenen im Ordner ${backup_dir}."
            note ""
            note "Rentalars ist dafür kurz nicht erreichbar: Es wird angehalten, MariaDB neu gestartet"
            note "und gewartet, bis alle Tabellen verschlüsselt sind. Danach wird jede Tabelle mit dem"
            note "Stand von vorher verglichen; erst wenn alles gleich ist, startet Rentalars wieder."
        else
            note "MariaDB on this server encrypts its files, and all backups are encrypted – also"
            note "the existing ones in the folder ${backup_dir}."
            note ""
            note "Rentalars cannot be reached for a short while: it is stopped, MariaDB restarted,"
            note "and everything waits until every table is encrypted. Then every table is compared"
            note "with its state before; only when all is the same does Rentalars start again."
        fi
    else
        note "$(t "Die Datenbank liegt auf $(config_get database host). Ob sie ihre Dateien verschlüsselt," "The database is on $(config_get database host). Whether it encrypts its files")"
        note "$(t "entscheidet jener Server:" "is that server's decision:")"
        note "    $(remote_database_line | head -n 1)"
        note ""
        note "$(t "Verschlüsselt werden hier alle Sicherungen – auch die vorhandenen im Ordner ${backup_dir}." "Here, all backups are encrypted – also the existing ones in the folder ${backup_dir}.")"
    fi
    if ! ${assume_yes}; then
        read -r -p "    $(t "Jetzt einschalten? [J/n] " "Switch on now? [Y/n] ")" answer
        [[ -z "${answer}" || "${answer}" =~ ^[JjYy] ]] || fail "$(t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed.")"
    fi

    local key work
    key="$(existing_recovery_key)"
    [[ -n "${key}" ]] || key="$(new_recovery_key)"
    store_recovery_key "${key}"
    work="$(mktemp -d)"
    # shellcheck disable=SC2064  # the folder name is meant to be fixed now
    trap "rm -rf '${work}'" EXIT

    if ${local_database} && ! mariadb_encryption_active; then
        say "$(t "Sichere den jetzigen Stand" "Backing up the current state")"
        note "$(bash "${APP_DIR}/deploy/backup.sh" --keep)"

        say "$(t "Halte Rentalars an und nehme den Fingerabdruck jeder Tabelle" "Stopping Rentalars and taking the fingerprint of every table")"
        stop_rentalars
        manage database_fingerprint > "${work}/before.json"

        say "$(t "MariaDB bekommt seinen Schlüssel und startet neu" "MariaDB gets its key and restarts")"
        write_mariadb_encryption "${RECOVERY_KEY_FILE}" "${APP_DIR}"
        if ! systemctl restart mariadb || ! mariadb_encryption_active; then
            # MariaDB did not start with the key, so nothing was encrypted:
            # back to the settings from before. The key files stay – they
            # are harmless, and a second attempt uses the same key.
            rm -f "${MARIADB_ENCRYPTION_SETTINGS}"
            systemctl restart mariadb
            start_rentalars
            fail "$(t "MariaDB ließ sich mit Verschlüsselung nicht starten; es läuft wieder wie vorher, nichts wurde verschlüsselt. Die Meldungen stehen in: journalctl -u mariadb" "MariaDB did not start with encryption; it runs as before again, nothing was encrypted. The messages are in: journalctl -u mariadb")"
        fi

        say "$(t "Warte, bis alle Tabellen verschlüsselt sind" "Waiting until every table is encrypted")"
        local waited=0 open
        while open="$(unencrypted_tables | wc -l)" && [[ "${open}" -gt 0 ]]; do
            (( waited % 30 == 0 )) && note "$(t "noch ${open} Tabelle(n) …" "${open} table(s) to go …")"
            (( waited >= 3600 )) && fail "$(t "Nach einer Stunde sind noch ${open} Tabellen unverschlüsselt. MariaDB verschlüsselt weiter; Rentalars bleibt angehalten. Später erneut: sudo rentalars encryption enable" "After an hour, ${open} tables are still not encrypted. MariaDB goes on encrypting; Rentalars stays stopped. Later once more: sudo rentalars encryption enable")"
            sleep 2
            waited=$((waited + 2))
        done
        note "$(t "Alle Tabellen sind verschlüsselt." "Every table is encrypted.")"

        say "$(t "Vergleiche jede Tabelle mit dem Stand von vorher" "Comparing every table with its state before")"
        manage database_fingerprint > "${work}/after.json"
        if ! compare_fingerprints "${work}/before.json" "${work}/after.json"; then
            fail "$(t "Die Daten sind nach dem Verschlüsseln nicht mehr dieselben (siehe oben). Rentalars bleibt angehalten. Die Sicherung von vorher spielt ein: sudo rentalars restore DATEI (die Datei steht weiter oben). Den Schlüssel NICHT löschen." "The data is no longer the same after encrypting (see above). Rentalars stays stopped. To put the backup from before back: sudo rentalars restore FILE (the file is named further up). Do NOT delete the key.")"
        fi
    fi

    say "$(t "Sicherungen verschlüsseln" "Encrypting backups")"
    config_set "${CONFIG_FILE}" backup encrypt true
    encrypt_existing_backups

    if ${local_database}; then
        say "$(t "Starte Rentalars" "Starting Rentalars")"
        start_rentalars
        application_answers || fail "$(t "Rentalars antwortet nicht. Die Meldungen stehen in: journalctl -u rentalars" "Rentalars does not answer. The messages are in: journalctl -u rentalars")"
    fi
    say "$(t "Fertig. Die Verschlüsselung ist eingeschaltet." "Done. Encryption is switched on.")"
    note "$(t "Kopien früherer Sicherungen auf anderen Rechnern sind weiterhin unverschlüsselt:" "Copies of earlier backups on other computers are still not encrypted:")"
    note "$(t "dort durch neue ersetzen und die alten löschen." "replace them there with new ones and delete the old ones.")"
    present_recovery_key "${key}"
}

show_key() {
    [[ -f "${RECOVERY_KEY_FILE}" ]] || fail "$(t "Auf diesem Server gibt es keinen Wiederherstellungsschlüssel – die Verschlüsselung ist nicht eingeschaltet." "There is no recovery key on this server – encryption is not switched on.")"
    say "$(t "Wiederherstellungsschlüssel" "Recovery key")"
    note ""
    note "    $(head -n 1 "${RECOVERY_KEY_FILE}")"
    note ""
    note "$(t "Er entschlüsselt die Sicherungen und schließt den Schlüssel der Datenbank auf." "It decrypts the backups and unlocks the key of the database.")"
    note "$(t "Nicht weitergeben, nicht per E-Mail verschicken." "Do not pass it on, do not send it by e-mail.")"
}

decrypt_backup() {
    local file="" key_file="" output=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --key-file) key_file="${2:-}"; shift 2 ;;
            --output) output="${2:-}"; shift 2 ;;
            -*) fail "$(t "Unbekannte Option: $1" "Unknown option: $1")" ;;
            *) file="$1"; shift ;;
        esac
    done
    [[ -f "${file}" ]] || fail "$(t "Bitte die verschlüsselte Sicherung angeben: sudo rentalars encryption decrypt-backup DATEI.tar.gz.enc" "Please give the encrypted backup: sudo rentalars encryption decrypt-backup FILE.tar.gz.enc")"
    is_encrypted_file "${file}" || fail "$(t "${file} ist nicht verschlüsselt." "${file} is not encrypted.")"
    output="${output:-${file%.enc}}"
    [[ "${output}" != "${file}" && ! -e "${output}" ]] || fail "$(t "${output} gibt es schon." "${output} exists already.")"
    local key=""
    if [[ -n "${key_file}" ]]; then
        key="$(head -n 1 "${key_file}")"
    elif [[ -f "${RECOVERY_KEY_FILE}" ]]; then
        key="$(head -n 1 "${RECOVERY_KEY_FILE}")"
    else
        read -r -s -p "    $(t "Wiederherstellungsschlüssel: " "Recovery key: ")" key
        echo
    fi
    key="$(normalize_recovery_key "${key}")" || fail "$(t "Das ist kein Wiederherstellungsschlüssel (40 Zeichen 0–9 und a–f)." "That is no recovery key (40 characters 0–9 and a–f).")"
    local key_temp
    key_temp="$(mktemp)"
    printf '%s\n' "${key}" > "${key_temp}"
    if ! ( umask 077; decrypt_stream "${key_temp}" < "${file}" > "${output}.partial" 2> /dev/null ) \
        || ! gzip -t "${output}.partial" 2> /dev/null; then
        rm -f "${key_temp}" "${output}.partial"
        fail "$(t "Mit diesem Schlüssel lässt sich ${file} nicht entschlüsseln." "This key does not decrypt ${file}.")"
    fi
    rm -f "${key_temp}"
    mv "${output}.partial" "${output}"
    say "$(t "Entschlüsselt:" "Decrypted:") ${output}"
    note "$(t "Die Dateien darin sind unverschlüsselt (die Datenbank ist als database.sql.enc noch verschlüsselt; zum Einspielen braucht rentalars restore dann den Schlüssel). Nach Gebrauch löschen." "The files in it are unencrypted (the database is still encrypted as database.sql.enc; restoring it with rentalars restore needs the key). Delete it after use.")"
}

command="${1:-status}"
shift || true
case "${command}" in
    status) show_status ;;
    enable) enable "$@" ;;
    show-key) show_key ;;
    decrypt-backup) decrypt_backup "$@" ;;
    *) fail "$(t "Unbekannt: rentalars encryption ${command} (möglich: status, enable, show-key, decrypt-backup)" "Unknown: rentalars encryption ${command} (possible: status, enable, show-key, decrypt-backup)")" ;;
esac
