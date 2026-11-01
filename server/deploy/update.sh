#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – install a new version (NFA-034, NFA-054).
#
#   sudo rentalars update rentalars-1.0.0.tar.gz     from a downloaded package
#   sudo rentalars update /path/to/unpacked/folder    or from a folder
#   sudo rentalars rollback                            back to the version before
#
# What an update does, in this order:
#
#   1. Checks the prerequisites. If one is not met, nothing is changed.
#   2. Writes a backup of database and files. It is never deleted automatically.
#   3. Installs the new version NEXT TO the running one – program and Python
#      libraries, and the packages of the system the new version added
#      (lib.sh, added_packages: ffmpeg). Rentalars keeps running; if
#      this step fails, nothing happened.
#   4. Stops Rentalars, switches to the new version, brings the database to
#      its state (migration), adapts the NGINX configuration to the installed
#      NGINX, starts Rentalars and checks that it answers.
#   5. If step 4 fails, it goes back by itself: old program, backup restored.
#
# The interruption for the users is the duration of step 4, usually well
# under a minute.
#
# "rollback" undoes a completed update by hand: the previous program is
# switched back on and the backup from step 2 is restored. Everything entered
# AFTER the update is lost by that; a backup of that state is made first.
#
# After Ubuntu itself was upgraded (24.04 to 26.04, NFA-063) the installed
# program cannot run any more: its libraries belong to the Python of the old
# Ubuntu. An update – with the same package or a newer one – sets them up
# again. In that one situation there is no program to go back to: if step 4
# fails, program and data are put back as they were and Rentalars stays
# stopped; and "rollback" refuses afterwards.
#
# On a Raspberry Pi (NFA-070) the update also sets the number of worker
# processes and the memory of MariaDB by the memory of the Pi (lib.sh,
# install_units and refresh_server_configuration), and reminds of data that
# lies on the SD card. On every other computer nothing of this happens.
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "${RENTALARS_LIB:-$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh}"

require_root
[[ -f "${CONFIG_FILE}" && -L "${APP_DIR}" ]] \
    || fail "$(t "Rentalars ist auf diesem Server nicht installiert. Für eine neue Installation: deploy/install.sh" "Rentalars is not installed on this server. For a new installation: deploy/install.sh")"

# --- Going back -----------------------------------------------------------------

go_back() {
    # go_back PREVIOUS_RELEASE BACKUP_FILE [extra options for restore.sh]
    local previous="$1" backup="$2"
    shift 2
    systemctl stop "${SERVICE_NAME}" || true
    make_scripts_executable "${previous}/app"
    activate_release "${previous}"
    install_units
    refresh_server_configuration
    bash "${APP_DIR}/deploy/restore.sh" "${backup}" --yes "$@"
}

if [[ "${1:-}" == "--rollback" ]]; then
    [[ -f "${LAST_UPDATE_FILE}" ]] || fail "$(t "Es gibt keine Aktualisierung, die sich zurücknehmen ließe." "There is no update that could be taken back.")"
    # shellcheck disable=SC1090  # written by this script, see below
    source "${LAST_UPDATE_FILE}"
    [[ -d "${PREVIOUS_RELEASE:-}" ]] || fail "$(t "Die vorige Version (${PREVIOUS_RELEASE:-?}) ist nicht mehr vorhanden." "The previous version (${PREVIOUS_RELEASE:-?}) is no longer there.")"
    [[ -f "${BACKUP_FILE:-}" ]] || fail "$(t "Die Sicherung von vor der Aktualisierung (${BACKUP_FILE:-?}) fehlt." "The backup from before the update (${BACKUP_FILE:-?}) is missing.")"
    release_runs "${PREVIOUS_RELEASE}" \
        || fail "$(t "Die vorige Version läuft auf diesem Server nicht mehr: Ihre Python-Bibliotheken gehören zu einem anderen Python. So ist es, nachdem Ubuntu selbst auf eine neue Version gehoben wurde. Zurückgehen ist deshalb nicht möglich; es wurde nichts verändert. Die Daten von vor der Aktualisierung liegen in ${BACKUP_FILE}." "The previous version no longer runs on this server: its Python libraries belong to another Python. That is so after Ubuntu itself was upgraded to a new version. Going back is therefore not possible; nothing was changed. The data from before the update is in ${BACKUP_FILE}.")"
    say "$(t "Zurück zur vorigen Version" "Back to the previous version")"
    note "$(t "jetzt in Betrieb:   " "running now:        ")Rentalars $(version_of "${APP_DIR}")"
    note "$(t "vorige Version:     " "previous version:   ")Rentalars $(version_of "${PREVIOUS_RELEASE}/app")"
    note "$(t "Stand der Daten:    " "state of the data:  ")${BACKUP_FILE}"
    note ""
    note "$(t "Alles, was seit der Aktualisierung eingegeben wurde, geht verloren." "Everything entered since the update is lost.")"
    if [[ "${2:-}" != "--yes" ]]; then
        read -r -p "    $(t "Wirklich zurückgehen? [ja/NEIN] " "Really go back? [yes/NO] ")" answer
        [[ "${answer,,}" == "ja" || "${answer,,}" == "yes" ]] || fail "$(t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed.")"
    fi
    say "$(t "Sichere zuerst den jetzigen Stand" "Backing up the current state first")"
    note "$(bash "${APP_DIR}/deploy/backup.sh" --keep)"
    go_back "${PREVIOUS_RELEASE}" "${BACKUP_FILE}" --no-safety-backup
    rm -f "${LAST_UPDATE_FILE}"
    say "$(t "Fertig. Rentalars $(version_of "${APP_DIR}") läuft wieder mit dem Stand von vor der Aktualisierung." "Done. Rentalars $(version_of "${APP_DIR}") runs again with the state from before the update.")"
    exit 0
fi

# --- Step 1: prerequisites ---------------------------------------------------------

package="${1:-}"
[[ -n "${package}" ]] || fail "$(t "Bitte das neue Paket angeben: sudo rentalars update rentalars-X.Y.Z.tar.gz" "Please give the new package: sudo rentalars update rentalars-X.Y.Z.tar.gz")"
[[ -e "${package}" ]] || fail "$(t "${package} gibt es nicht." "${package} does not exist.")"

unpacked=""
cleanup() { [[ -n "${unpacked}" ]] && rm -rf "${unpacked}"; return 0; }
trap cleanup EXIT

if [[ -d "${package}" ]]; then
    source_tree="$(readlink -f "${package}")"
else
    # Not in /tmp: since Ubuntu 24.10 that is main memory, and a package that
    # brings its libraries along is large.
    unpacked="$(mktemp -d "${RENTALARS_HOME}/.unpacked.XXXXXX")"
    tar -xf "${package}" -C "${unpacked}" || fail "$(t "${package} lässt sich nicht entpacken." "${package} cannot be unpacked.")"
    # The package contains one folder, e.g. rentalars-1.0.0/.
    source_tree="$(dirname "$(find "${unpacked}" -maxdepth 2 -name manage.py | head -n 1)")"
fi
[[ -f "${source_tree}/manage.py" && -f "${source_tree}/requirements.txt" ]] \
    || fail "$(t "${package} enthält kein Rentalars." "${package} contains no Rentalars.")"

old_version="$(version_of "${APP_DIR}")"
new_version="$(version_of "${source_tree}")"
previous_release="$(current_release)"

say "$(t "Aktualisierung von Rentalars ${old_version} auf ${new_version}" "Update of Rentalars ${old_version} to ${new_version}")"
# The new version names the oldest version it can update (NFA-077: lib.sh OLDEST_UPDATABLE_VERSION). An update
# from an older version would stop at the migration and go back; it is refused here, before anything is changed.
# (An update run by an older version does not know this; the new version's migration then refuses with the
# same advice, rentalars/core/checks.py, and the update goes back by itself.)
oldest_updatable="$(oldest_updatable_of "${source_tree}")"
if [[ -n "${oldest_updatable}" ]] && version_older "${old_version}" "${oldest_updatable}"; then
    fail "$(t "Rentalars ${new_version} aktualisiert nur Installationen ab Version ${oldest_updatable}; installiert ist ${old_version}. Bitte zuerst auf ${oldest_updatable} oder eine neuere Version vor ${new_version} aktualisieren, dann auf ${new_version}. Es wurde nichts verändert." "Rentalars ${new_version} only updates installations of version ${oldest_updatable} or later; installed is ${old_version}. Please update to ${oldest_updatable} or a later version before ${new_version} first, then to ${new_version}. Nothing was changed.")"
fi
check_python_version
check_free_space "${RENTALARS_HOME}" 1024
check_free_space "$(config_get backup directory "${DEFAULT_BACKUP_DIR}")" 500
if database_is_local; then
    systemctl is-active --quiet mariadb || fail "$(t "MariaDB läuft nicht. Bitte zuerst starten: sudo systemctl start mariadb" "MariaDB is not running. Please start it first: sudo systemctl start mariadb")"
else
    database_answers || fail "$(t "Die Datenbank auf $(config_get database host) antwortet nicht. Es wurde nichts verändert." "The database on $(config_get database host) does not answer. Nothing was changed.")"
fi
systemctl is-active --quiet "${SERVICE_NAME}" \
    || note "$(t "Hinweis: Rentalars läuft gerade nicht. Die Aktualisierung startet es am Ende." "Note: Rentalars is not running at the moment. The update starts it at the end.")"
previous_runs=true
if ! release_runs "${previous_release}"; then
    previous_runs=false
    if [[ "$(operator_language)" == de ]]; then
        note "Hinweis: Die installierte Version kann auf diesem Server nicht mehr laufen – ihre"
        note "Python-Bibliotheken gehören zu einem anderen Python (so ist es nach einem Wechsel der"
        note "Ubuntu-Version). Die Aktualisierung richtet sie neu ein. Schlägt sie fehl, werden"
        note "Programm und Daten zurückgesetzt wie immer; Rentalars bleibt dann aber angehalten."
    else
        note "Note: the installed version can no longer run on this server – its Python"
        note "libraries belong to another Python (so it is after a change of the Ubuntu"
        note "version). The update sets them up again. Should it fail, program and data are"
        note "put back as always; Rentalars then stays stopped, though."
    fi
fi
# On a Raspberry Pi, a reminder while data lies on the SD card (NFA-070).
mapfile -t on_sd_card < <(installation_places_on_sd_card)
if (( ${#on_sd_card[@]} > 0 )); then
    note "$(t "Hinweis: Auf der SD-Karte liegen ${on_sd_card[*]}. Eine SSD wäre sicherer" "Note: ${on_sd_card[*]} lie on the SD card. An SSD would be safer")"
    note "$(t "(docs/betrieb/installation.md, Abschnitt Raspberry Pi)." "(docs/en/operations/installation.md, section Raspberry Pi).")"
fi
note "$(t "Voraussetzungen erfüllt." "Prerequisites met.")"

# --- Step 2: backup ----------------------------------------------------------------------

say "$(t "Sichere Datenbank und Dateien" "Backing up database and files")"
# Through bash: the scripts of the installed version may have lost their execute bit (NFA-069).
# They get it back as well – they are the ones that run after going back to this version.
make_scripts_executable "$(readlink -f "${APP_DIR}")"
backup_file="$(bash "${APP_DIR}/deploy/backup.sh" --keep)"
note "${backup_file}"

# --- Step 3: the new version next to the old one -----------------------------------------------

say "$(t "Installiere die neue Version neben der laufenden" "Installing the new version next to the running one")"
new_release="$(build_release "${source_tree}")"
note "${new_release}"
# Packages of the system the new version needs and this server lacks (NFA-076: ffmpeg for the videos in the
# chat) – from the list of the new version; a failure is warned about and the update goes on.
install_added_packages "${source_tree}/deploy/lib.sh"

# --- Step 4: switch --------------------------------------------------------------------------

say "$(t "Schalte um" "Switching over")"
systemctl stop "${SERVICE_NAME}"
activate_release "${new_release}"
cat > "${LAST_UPDATE_FILE}" <<STATE
# Written by "rentalars update"; read by "rentalars rollback".
PREVIOUS_RELEASE="${previous_release}"
BACKUP_FILE="${backup_file}"
STATE

switched=true
manage migrate --noinput || switched=false
if ${switched}; then
    manage collectstatic --noinput --clear > /dev/null || switched=false
fi
if ${switched}; then
    install_units
    # NGINX and MariaDB may be newer than at the last update – for instance
    # after Ubuntu itself was upgraded (NFA-063).
    refresh_server_configuration
    systemctl start "${SERVICE_NAME}" || switched=false
    # A timer that came with this version (0.4: the mail fetch) is switched on.
    ${switched} && { enable_timers || switched=false; }
fi
if ${switched} && ! application_answers; then
    switched=false
fi

# --- Step 5: go back if anything failed --------------------------------------------------------

if ! ${switched}; then
    say "$(t "Die neue Version läuft nicht. Gehe zurück zu Rentalars ${old_version}." "The new version does not run. Going back to Rentalars ${old_version}.")"
    if ${previous_runs}; then
        go_back "${previous_release}" "${backup_file}" --no-safety-backup
        rm -rf "${new_release}"
        rm -f "${LAST_UPDATE_FILE}"
        fail "$(t "Die Aktualisierung ist fehlgeschlagen und wurde zurückgenommen. Rentalars ${old_version} läuft wieder; es sind keine Daten verloren gegangen. Die Fehlermeldung steht weiter oben und in: journalctl -u rentalars" "The update failed and was taken back. Rentalars ${old_version} runs again; no data was lost. The error message is further up and in: journalctl -u rentalars")"
    fi
    # The program from before cannot run here either (see the top of this
    # file). Put program and data back as they were, and say so plainly.
    go_back "${previous_release}" "${backup_file}" --no-safety-backup --data-only
    rm -rf "${new_release}"
    rm -f "${LAST_UPDATE_FILE}"
    fail "$(t "Die Aktualisierung ist fehlgeschlagen und wurde zurückgenommen: Programm und Daten sind wie vorher, es sind keine Daten verloren gegangen. Rentalars bleibt angehalten, weil die installierte Version ${old_version} auf diesem Server nicht mehr laufen kann. Die Fehlermeldung der neuen Version steht weiter oben und in: journalctl -u rentalars. Danach noch einmal: sudo rentalars update PAKET" "The update failed and was taken back: program and data are as before, no data was lost. Rentalars stays stopped, because the installed version ${old_version} can no longer run on this server. The error message of the new version is further up and in: journalctl -u rentalars. Then once more: sudo rentalars update PACKAGE")"
fi

# Keep the running and the previous release; older ones are no longer needed.
for release in "${RELEASES_DIR}"/*/; do
    release="${release%/}"
    [[ "${release}" == "${new_release}" || "${release}" == "${previous_release}" ]] || rm -rf "${release}"
done

# EML-040: the local AI takes over what the new version sets for it (threads, thinking off, limits) –
# with the script of the NEW version, never changing the model, never failing the update. Not on rollback:
# the options there are checked against "llama-server --help" and stay valid for the version gone back to.
bash "${APP_DIR}/deploy/ai.sh" refresh || true

say "$(t "Fertig. Rentalars ${new_version} läuft." "Done. Rentalars ${new_version} is running.")"
note "$(t "Sicherung von vorher:  " "Backup from before:    ")${backup_file}"
if ${previous_runs}; then
    note "$(t "Zurück zur alten Version, falls nötig:  sudo rentalars rollback" "Back to the old version, if need be:  sudo rentalars rollback")"
else
    note "$(t "Ein Zurück zur vorigen Version gibt es diesmal nicht: Sie kann auf diesem Server" "There is no going back to the previous version this time: it can no longer run on")"
    note "$(t "nicht mehr laufen (docs/betrieb/aktualisierung.md: Von Ubuntu 24.04 auf 26.04 wechseln)." "this server (docs/en/operations/updating.md: moving from Ubuntu 24.04 to 26.04).")"
fi
