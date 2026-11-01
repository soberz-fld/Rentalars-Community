#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – back up database and uploaded files (NFA-015).
#
#   sudo rentalars backup            daily backup; old ones are tidied up
#   sudo rentalars backup --keep     a backup that the tidy-up never deletes
#                                    (made automatically before every update)
#
# A backup is one file:  /var/backups/rentalars/rentalars-2026-10-10_023000.tar.gz
# or, with encryption switched on (NFA-067), the same encrypted with the
# recovery key:           /var/backups/rentalars/rentalars-2026-10-10_023000.tar.gz.enc
# It contains
#   database.sql      everything in the database
#   media/            uploaded files (logo; later attachments)
#   rentalars.conf    the configuration, including the secret key
#   VERSION           the version of Rentalars that wrote the backup
#
# The file holds all company data and the access data of the database. It is
# readable by root only. Copy the backups to another machine regularly – a
# backup on the same disk does not survive the loss of that disk
# (docs/betrieb/sicherung.md).
#
# How many daily backups are kept is set in the configuration file:
#   [backup]
#   keep_days = 14
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

require_root
[[ -f "${CONFIG_FILE}" ]] || fail "$(t "${CONFIG_FILE} fehlt. Ist Rentalars installiert?" "${CONFIG_FILE} is missing. Is Rentalars installed?")"

keep_forever=false
[[ "${1:-}" == "--keep" ]] && keep_forever=true

backup_dir="$(config_get backup directory "${DEFAULT_BACKUP_DIR}")"
keep_days="$(config_get backup keep_days 14)"
data_dir="$(config_get rentalars data_dir "${DEFAULT_DATA_DIR}")"
database="$(config_get database name rentalars)"

timestamp="$(date +%Y-%m-%d_%H%M%S)"
suffix=""
${keep_forever} && suffix="-keep"
target="${backup_dir}/rentalars-${timestamp}${suffix}.tar.gz"
encrypted=false
if backups_encrypted; then
    [[ -f "${RECOVERY_KEY_FILE}" ]] \
        || fail "$(t "Die Sicherungen sollen verschlüsselt werden, aber ${RECOVERY_KEY_FILE} fehlt. Es wurde keine Sicherung geschrieben (docs/betrieb/verschluesselung.md)." "The backups are to be encrypted, but ${RECOVERY_KEY_FILE} is missing. No backup was written (docs/en/operations/encryption.md).")"
    encrypted=true
    target="${target}.enc"
fi

install -d -m 700 -o root -g root "${backup_dir}"
check_free_space "${backup_dir}" 200

work="$(mktemp -d "${backup_dir}/.in-progress.XXXXXX")"
trap 'rm -rf "${work}"' EXIT
write_database_credentials "${work}/client.cnf"

# --single-transaction: a consistent snapshot without locking out users.
# Encrypted backups: the dump goes through the cipher into database.sql.enc – it is never on the disk
# unencrypted, not even in the temporary folder. The archive is encrypted once more as a whole.
dump_name="database.sql"
if ${encrypted}; then
    dump_name="database.sql.enc"
    mariadb-dump --defaults-extra-file="${work}/client.cnf" \
        --single-transaction --routines --triggers --default-character-set=utf8mb4 \
        "${database}" | encrypt_stream "${RECOVERY_KEY_FILE}" > "${work}/${dump_name}"
    # A dump that ends without this line was cut off; such a backup is worthless. Read back through the cipher.
    decrypt_stream "${RECOVERY_KEY_FILE}" < "${work}/${dump_name}" | tail -n 1 | grep -q "Dump completed" \
        || fail "$(t "Die Datenbanksicherung ist unvollständig. Es wurde keine Sicherung geschrieben." "The database dump is incomplete. No backup was written.")"
else
    mariadb-dump --defaults-extra-file="${work}/client.cnf" \
        --single-transaction --routines --triggers --default-character-set=utf8mb4 \
        "${database}" > "${work}/${dump_name}"
    tail -n 1 "${work}/${dump_name}" | grep -q "Dump completed" \
        || fail "$(t "Die Datenbanksicherung ist unvollständig. Es wurde keine Sicherung geschrieben." "The database dump is incomplete. No backup was written.")"
fi
rm -f "${work}/client.cnf"

install -m 600 "${CONFIG_FILE}" "${work}/rentalars.conf"
version_of "${APP_DIR}" > "${work}/VERSION"
mkdir -p "${data_dir}/media"

# Backups made in the browser (ADM-010) wait in media/jobs/backups for their
# download; they are backups themselves and are left out, or every nightly
# backup would carry them along and double in size.
web_backups="media/jobs/backups"
# The same ones after they were deleted: the trash (media/.deleted/<day>/jobs/backups) keeps them for seven days.
trashed_web_backups="media/.deleted/*/jobs/backups"

# The archive is written under a temporary name first. A backup that was
# interrupted can then never be mistaken for a complete one. An encrypted
# backup goes straight through openssl: there is no unencrypted archive and no unencrypted dump on
# the disk, not even for a moment.
( umask 077
  if ${encrypted}; then
      tar -cz --exclude="${web_backups}" --exclude="${trashed_web_backups}" -C "${work}" "${dump_name}" rentalars.conf VERSION -C "${data_dir}" media \
          | encrypt_stream "${RECOVERY_KEY_FILE}" > "${target}.partial"
      # Read back: only a backup that decrypts is a backup.
      decrypt_stream "${RECOVERY_KEY_FILE}" < "${target}.partial" | gzip -t
  else
      tar -czf "${target}.partial" --exclude="${web_backups}" --exclude="${trashed_web_backups}" -C "${work}" "${dump_name}" rentalars.conf VERSION -C "${data_dir}" media
      gzip -t "${target}.partial"
  fi )
mv "${target}.partial" "${target}"

# Tidy up: daily backups older than keep_days go; "-keep" backups stay.
find "${backup_dir}" -maxdepth 1 -type f \( -name 'rentalars-*.tar.gz' -o -name 'rentalars-*.tar.gz.enc' \) \
    ! -name '*-keep.tar.gz' ! -name '*-keep.tar.gz.enc' -mtime "+${keep_days}" -delete

# For the self-check of the application (NFA-037): the backup folder is
# readable by root only, so the application learns from this file when the
# last backup was written, whether it is encrypted and how much space is left.
# The data folder belongs to the service user, who could lay a link in place of the file – as root, this
# script would then write wherever the link points. The file is written in the folder of the backups (root only) and
# put in place with install, which removes what is there first and creates the new file without following a link.
( umask 022
  printf '{"time": "%s", "file": "%s", "encrypted": %s, "size": %s, "free_mb": %s}\n' \
      "$(date --iso-8601=seconds)" "${target}" "${encrypted}" "$(stat -c %s "${target}")" \
      "$(df --output=avail -m "${backup_dir}" | tail -n 1 | tr -d ' ')" > "${work}/backup-status.json" )
place_file "${work}/backup-status.json" "${data_dir}/backup-status.json"

echo "${target}"
