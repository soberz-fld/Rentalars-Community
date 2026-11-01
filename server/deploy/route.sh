#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – the route service for kilometre suggestions (LOG-017, NFA-050).
#
#   sudo rentalars route install [--region germany|BUNDESLAND | --file FILE.osm.pbf] [--keep-file] [--dry-run]
#   sudo rentalars route update [--keep-file] [--dry-run]
#   sudo rentalars route register --url https://ROUTING-SERVER [--dry-run]
#   sudo rentalars route remove [--keep-data] [--dry-run]
#   rentalars route status
#
# Without a route service the planner types the kilometres of a vehicle on a
# trip in by hand. With one, the dialog of the vehicle offers "Geplante km aus
# der Route vorschlagen" – a suggestion that can always be changed. The
# positions of the addresses go to no service outside (NFA-050):
#
# "install" puts the router Routino on this server, with the map of
# OpenStreetMap for Germany or one Bundesland:
#
#   1. checks the system (Ubuntu 24.04/26.04, Raspberry Pi OS on Debian 13),
#      the memory and the free space. All of Germany is a download of about
#      4.5 GB; processing it needs several GB of memory, far more free disk
#      space for a while (the command says how much) and takes one to a few
#      hours – longer on a small server. A Bundesland is much smaller and
#      quicker: --region bayern, nordrhein-westfalen, baden-wuerttemberg …
#      Below 4 GB of memory the command asks for a Bundesland unless
#      "--region germany" is given, and processes in Routino's slim mode;
#   2. installs the package "routino" of the distribution (Ubuntu: universe;
#      Debian 13);
#   3. downloads the map from Geofabrik (download.geofabrik.de, Karlsruhe) and
#      checks it against the MD5 checksum published next to it – or takes a
#      file already on the server (--file, no internet needed);
#   4. processes it with planetsplitter for motor vehicles (tagging-drive.xml)
#      into /opt/rentalars/routes – a folder only root can change, as the
#      model of the local AI; the files are readable by everybody (the map is
#      public) and so by the service user. Progress: planetsplitter.log there;
#   5. deletes the download (unless --keep-file), runs a test route as the
#      service user and only then writes /etc/rentalars/route-local.conf –
#      Rentalars reads it at every use, nothing has to be restarted.
#
# "update" downloads and processes the same region again – roads change, and
# "status" and the settings page say how old the map is. The map in use stays
# until the new one has answered its test route.
#
# "register" names an OSRM-compatible routing server instead: one the operator
# runs himself or one hosted in Germany (NFA-050) – an address with https, or
# with http on this machine only. Rentalars sends it the positions of the
# places of a trip.
#
# "remove" undoes "install" or "register"; afterwards the kilometres are typed
# in by hand again. "--keep-data" keeps the processed map and the package.
# With "--dry-run" nothing is changed: the plan is shown – also without root.
#
# Root is needed only for this command; Rentalars itself never gets it.
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

# --- What is installed where -----------------------------------------------------------------------
# RENTALARS_ROUTE_TEST_ROOT puts the map folder below a folder, does not install packages and does not change
# users – only for the tests (tests/unit/test_090_routing.py); with it, root is not required.
readonly ROUTE_TEST_ROOT="${RENTALARS_ROUTE_TEST_ROOT:-}"
readonly ROUTE_HOME="${ROUTE_TEST_ROOT}${ROUTE_DIR}"
# Packages this command installed itself, to remove them again with "remove".
readonly ROUTE_PACKAGES_FILE="${ROUTE_HOME}/${INSTALLED_PACKAGES_NAME}"
readonly ROUTE_LOG="${ROUTE_HOME}/planetsplitter.log"
ROUTE_LOCAL_FILE="$(dirname "${CONFIG_FILE}")/route-local.conf"
readonly ROUTE_LOCAL_FILE
readonly ROUTE_PREFIX="rentalars"
readonly ROUTINO_PACKAGE="routino"
readonly ROUTINO_SHARE="/usr/share/routino"
readonly GEOFABRIK="https://download.geofabrik.de/europe"
# Below this much memory (MB): Routino's slim mode, and all of Germany only when asked for by name.
readonly ROUTE_FULL_MEMORY_MB=4000
# A map older than this (days) is worth an update.
readonly ROUTE_OLD_DAYS=180

# The regions: slug | name | download in MB (about, autumn 2026) | test route from one town to another:
# latitude longitude latitude longitude. Geofabrik's extracts of Germany and its Länder.
readonly REGIONS=(
    "germany|Deutschland|4500|50.1109 8.6821 49.7913 9.9534"                       # Frankfurt am Main → Würzburg
    "baden-wuerttemberg|Baden-Württemberg|600|48.7758 9.1829 49.0069 8.4037"       # Stuttgart → Karlsruhe
    "bayern|Bayern|800|48.1374 11.5755 48.3705 10.8978"                            # München → Augsburg
    "berlin|Berlin|90|52.5219 13.4132 52.5357 13.2000"                             # Alexanderplatz → Spandau
    "brandenburg|Brandenburg|180|52.3906 13.0645 51.7563 14.3329"                  # Potsdam → Cottbus
    "bremen|Bremen|20|53.0793 8.8017 53.5396 8.5809"                               # Bremen → Bremerhaven
    "hamburg|Hamburg|45|53.5503 9.9920 53.4605 9.9836"                             # Rathaus → Harburg
    "hessen|Hessen|310|50.0782 8.2398 51.3127 9.4797"                              # Wiesbaden → Kassel
    "mecklenburg-vorpommern|Mecklenburg-Vorpommern|110|53.6355 11.4012 54.0924 12.0991"  # Schwerin → Rostock
    "niedersachsen|Niedersachsen|620|52.3759 9.7320 52.2689 10.5268"               # Hannover → Braunschweig
    "nordrhein-westfalen|Nordrhein-Westfalen|780|51.2277 6.7735 50.9375 6.9603"    # Düsseldorf → Köln
    "rheinland-pfalz|Rheinland-Pfalz|240|49.9929 8.2473 50.3569 7.5890"            # Mainz → Koblenz
    "saarland|Saarland|40|49.2402 6.9969 49.3448 7.1797"                           # Saarbrücken → Neunkirchen
    "sachsen|Sachsen|270|51.0504 13.7373 51.3397 12.3731"                          # Dresden → Leipzig
    "sachsen-anhalt|Sachsen-Anhalt|130|52.1205 11.6276 51.4970 11.9688"            # Magdeburg → Halle
    "schleswig-holstein|Schleswig-Holstein|160|54.3233 10.1228 53.8655 10.6866"    # Kiel → Lübeck
    "thueringen|Thüringen|140|50.9848 11.0299 50.9272 11.5892"                     # Erfurt → Jena
)

# One field of the table: region_field SLUG 2|3|4 (name, MB, test route); fails for an unknown region.
region_field() {
    local entry
    for entry in "${REGIONS[@]}"; do
        if [[ "${entry%%|*}" == "$1" ]]; then
            cut -d'|' -f"$2" <<<"${entry}"
            return 0
        fi
    done
    return 1
}

# The region as the operator reads it: region_name SLUG
region_name() {
    if [[ "$1" == germany ]]; then t "Deutschland" "Germany"; return 0; fi
    region_field "$1" 2 || printf '%s' "$1"
}

# Every region but Germany, as a list: "baden-wuerttemberg, bayern, …"
region_list() {
    local entry list=""
    for entry in "${REGIONS[@]:1}"; do
        list+="${list:+, }${entry%%|*}"
    done
    printf '%s' "${list}"
}

# Where Geofabrik offers a region: region_url SLUG
region_url() {
    if [[ "$1" == germany ]]; then
        echo "${GEOFABRIK}/germany-latest.osm.pbf"
    else
        echo "${GEOFABRIK}/germany/$1-latest.osm.pbf"
    fi
}

# How long processing takes, as words – estimates: region_duration SIZE_MB
region_duration() {
    if (( $1 >= 2000 )); then
        t "etwa 1 bis 3 Stunden, auf einem kleinen Server oder Raspberry Pi länger" "about 1 to 3 hours, longer on a small server or a Raspberry Pi"
    elif (( $1 >= 300 )); then
        t "etwa 10 bis 45 Minuten" "about 10 to 45 minutes"
    else
        t "einige Minuten" "a few minutes"
    fi
}

# Free space (MB) needed while processing a download of SIZE_MB: the download, Routino's temporary files
# (several times the download) and the result – an estimate on the safe side: needed_space SIZE_MB
needed_space() {
    echo $(( $1 * 5 + 500 ))
}

# Kilometres with a decimal comma in German: local_km 12.3
local_km() {
    if [[ "$(operator_language)" == de ]]; then tr . , <<<"$1"; else printf '%s\n' "$1"; fi
}

# One value of route-local.conf: local_value KEY
local_value() {
    sed -n "s/^$1 = //p" "${ROUTE_LOCAL_FILE}" 2> /dev/null | tail -n 1
}

# Succeeds if nobody but root can change PATH: it and every folder above it belong to root, and nobody else may
# write to them (the group root aside) – as in deploy/ai.sh. Root downloads, processes and deletes there; nothing
# the service user could have put or swapped may lie in the way. Not checked in the tests: root_only PATH
root_only() {
    local path owner group mode
    [[ -z "${ROUTE_TEST_ROOT}" ]] || return 0
    path="$(readlink -f -- "$1")" || return 1
    [[ -n "${path}" && -e "${path}" ]] || return 1
    while :; do
        read -r owner group mode < <(stat -c '%u %g %a' -- "${path}") || return 1
        (( owner == 0 )) || return 1
        (( (8#${mode} & 8#002) == 0 )) || return 1
        (( (8#${mode} & 8#020) == 0 || group == 0 )) || return 1
        [[ "${path}" == "/" ]] && return 0
        path="$(dirname -- "${path}")"
    done
}

# Run a program as the service user – so that a test shows what Rentalars itself can read: as_service_user …
as_service_user() {
    if [[ -n "${ROUTE_TEST_ROOT}" || ${EUID} -ne 0 ]] || ! id "${SERVICE_USER}" > /dev/null 2>&1; then
        "$@"
    else
        runuser -u "${SERVICE_USER}" -- "$@"
    fi
}

# The router of the package (or the one the tests put on PATH).
router_path() {
    command -v routino-router 2> /dev/null || true
}

# A test route; prints the kilometres: test_route ROUTER DATA_DIR LAT1 LON1 LAT2 LON2
test_route() {
    local router="$1" dir="$2" output
    output="$(as_service_user "${router}" --dir="${dir}" --prefix="${ROUTE_PREFIX}" \
        --profiles="${ROUTINO_SHARE}/profiles.xml" --translations="${ROUTINO_SHARE}/translations.xml" \
        --transport=motorcar --quickest --lat1="$3" --lon1="$4" --lat2="$5" --lon2="$6" \
        --output-text --output-stdout --quiet 2>&1)" || { tail -n 1 <<<"${output}" >&2; return 1; }
    # The sections of the text output (third column, "6.852 km") add up to the route.
    awk '!/^#/ && $4 == "km" { sum += $3; seen = 1 } END { if (!seen) exit 1; printf "%.1f\n", sum }' <<<"${output}"
}

# Two points of the map for a test route of a file of unknown region: nodes at a third and two thirds of the
# database – "LAT LON LAT LON", or nothing: points_of_data DATA_DIR
points_of_data() {
    local dir="$1" count first second
    command -v filedumper > /dev/null || return 0
    count="$(filedumper --dir="${dir}" --prefix="${ROUTE_PREFIX}" --statistics 2> /dev/null \
        | awk '/^Nodes/ { nodes = 1 } nodes && /^Number *=/ { print $3; exit }')"
    [[ "${count}" =~ ^[0-9]+$ ]] && (( count >= 3 )) || return 0
    first="$(filedumper --dir="${dir}" --prefix="${ROUTE_PREFIX}" --dump --node=$(( count / 3 )) 2> /dev/null \
        | sed -n 's/.*(latitude=\([-0-9.]*\) longitude=\([-0-9.]*\)).*/\1 \2/p' | head -n 1)"
    second="$(filedumper --dir="${dir}" --prefix="${ROUTE_PREFIX}" --dump --node=$(( count * 2 / 3 )) 2> /dev/null \
        | sed -n 's/.*(latitude=\([-0-9.]*\) longitude=\([-0-9.]*\)).*/\1 \2/p' | head -n 1)"
    [[ -n "${first}" && -n "${second}" ]] && echo "${first} ${second}"
    return 0
}

# Succeeds for an address an OSRM server may have: https, or http on this machine (NFA-050).
is_route_server_url() {
    [[ "$1" =~ ^https://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$ ]] \
        || [[ "$1" =~ ^http://(127\.[0-9]+\.[0-9]+\.[0-9]+|localhost|\[::1\])(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$ ]]
}

# Write the file Rentalars reads (route-local.conf), with KEY=VALUE pairs after the kind:
#   write_local_file KIND KEY=VALUE…
write_local_file() {
    local kind="$1" pair temporary
    shift
    for pair in "$@"; do
        [[ "${pair}" != *$'\n'* && "${pair}" != *$'\r'* ]] || fail "$(t "Ein Wert enthält einen Zeilenumbruch." "A value contains a line break.")"
    done
    mkdir -p "$(dirname "${ROUTE_LOCAL_FILE}")"
    temporary="$(mktemp "${ROUTE_LOCAL_FILE}.XXXXXX")"
    {
        echo "# Written by \"rentalars route ${command}\" on $(date -Iseconds)."
        echo "# Rentalars reads it at every use of the route service (LOG-017). Removed by \"rentalars route remove\"."
        echo "[route]"
        echo "kind = ${kind}"
        for pair in "$@"; do
            echo "${pair%%=*} = ${pair#*=}"
        done
        echo "installed_at = $(date -Iseconds)"
    } > "${temporary}"
    chmod 644 "${temporary}"
    mv "${temporary}" "${ROUTE_LOCAL_FILE}"
}

# One install or update at a time: either may run for hours.
take_lock() {
    local lock="${ROUTE_TEST_ROOT}/run/rentalars-route.lock"
    mkdir -p "$(dirname "${lock}")"
    root_only "$(dirname "${lock}")" || fail "$(t "$(dirname "${lock}") gehört nicht allein root." "$(dirname "${lock}") does not belong to root alone.")"
    exec 9> "${lock}"
    flock -n 9 || fail "$(t 'Ein anderes „rentalars route install“ oder „update“ läuft schon.' 'Another “rentalars route install” or “update” is running already.')"
}

# --- The commands ---------------------------------------------------------------------------------------

usage() {
    sed -n '3,8p' "$(readlink -f "${BASH_SOURCE[0]}")" | sed 's/^# \{0,1\}//'
    echo
    note "$(t "Regionen: germany (ganz Deutschland, groß) oder ein Bundesland: $(region_list)" "Regions: germany (all of Germany, large) or a Bundesland: $(region_list)")"
    note "$(t "register: ein OSRM-kompatibler Routenserver, den der Betreiber selbst betreibt oder der in Deutschland steht (NFA-050) – https, oder http nur auf diesem Rechner." "register: an OSRM-compatible routing server the operator runs himself or one hosted in Germany (NFA-050) – https, or http on this machine only.")"
}

command="${1:-}"
shift || true
dry_run=false region="" file="" keep_file=false keep_data=false url="" updating=false
while (( $# > 0 )); do
    case "$1" in
        --dry-run)   dry_run=true ;;
        --region)    region="${2:?}"; shift ;;
        --file)      file="${2:?}"; shift ;;
        --keep-file) keep_file=true ;;
        --keep-data) keep_data=true ;;
        --url)       url="${2:?}"; shift ;;
        -h|--help)   usage; exit 0 ;;
        *) fail "$(t "Unbekannte Angabe: $1" "Unknown option: $1")" ;;
    esac
    shift
done

do_install() {
    local os_release="${RENTALARS_ROUTE_OS_RELEASE:-${OS_RELEASE_FILE}}" model_file="${RENTALARS_ROUTE_DEVICE_MODEL:-${DEVICE_MODEL_FILE}}"
    local meminfo="${RENTALARS_ROUTE_MEMINFO:-${MEMORY_INFO_FILE}}" architecture="${RENTALARS_ROUTE_ARCH:-}"
    local memory cores threads splitter sort_ram size_mb source_file="" source download="" name test_points=""
    local free_mb needed_mb tagging
    [[ -n "${architecture}" ]] || architecture="$(dpkg --print-architecture 2> /dev/null || uname -m)"
    ${dry_run} || require_root_unless_test
    check_system "${os_release}" "${model_file}" "${architecture}"
    memory="$(memory_mb "${meminfo}")"
    cores="$(nproc 2> /dev/null || echo 1)"

    # What to process: a file on the server, or a region of Geofabrik.
    if [[ -n "${file}" ]]; then
        [[ -z "${region}" ]] || fail "$(t "Entweder --region oder --file." "Either --region or --file.")"
        source_file="$(readlink -f -- "${file}")" || true
        [[ -n "${source_file}" && -f "${source_file}" ]] || fail "$(t "${file} gibt es nicht." "${file} does not exist.")"
        [[ "${source_file}" =~ \.(osm\.pbf|pbf|osm|osm\.bz2|osm\.gz)$ ]] \
            || fail "$(t "--file braucht eine Karte von OpenStreetMap: *.osm.pbf (oder *.osm)." "--file needs a map of OpenStreetMap: *.osm.pbf (or *.osm).")"
        size_mb=$(( $(stat -c %s "${source_file}") / 1048576 + 1 ))
        # A file of Geofabrik keeps its region: test route and "update" know it.
        name="$(basename "${source_file}")"
        if [[ "${name}" =~ ^([a-z-]+)-latest\.osm\.pbf$ ]] && region_field "${BASH_REMATCH[1]}" 2 > /dev/null; then
            region="${BASH_REMATCH[1]}"
        fi
        source="${source_file}"
    else
        if [[ -z "${region}" ]]; then
            (( memory >= ROUTE_FULL_MEMORY_MB )) \
                || fail "$(t "Für ganz Deutschland ist dieser Server mit $(memory_text "${memory}") Arbeitsspeicher knapp. Bitte ein Bundesland wählen, z. B. --region bayern ($(region_list)) – oder ausdrücklich --region germany." "With $(memory_text "${memory}") of memory, all of Germany is a lot for this server. Please choose a Bundesland, e.g. --region bayern ($(region_list)) – or ask for --region germany explicitly.")"
            region="germany"
        fi
        region_field "${region}" 2 > /dev/null \
            || fail "$(t "Unbekannte Region: ${region}. Möglich: germany oder ein Bundesland: $(region_list)" "Unknown region: ${region}. Possible: germany or a Bundesland: $(region_list)")"
        size_mb="$(region_field "${region}" 3)"
        download="$(region_url "${region}")"
        source="${download}"
    fi
    [[ -n "${region}" ]] && test_points="$(region_field "${region}" 4)"

    # Routino's normal mode keeps more in memory; below 4 GB the slim mode works through files.
    threads=$(( cores > 4 ? 4 : cores ))
    if (( memory >= ROUTE_FULL_MEMORY_MB )); then
        splitter="planetsplitter"
        sort_ram=$(( memory / 4 ))
        (( sort_ram > 2048 )) && sort_ram=2048
    else
        splitter="planetsplitter-slim"
        sort_ram=$(( memory / 8 ))
        (( sort_ram < 64 )) && sort_ram=64
        (( sort_ram > 256 )) && sort_ram=256
    fi
    needed_mb="$(needed_space "${size_mb}")"
    local free_place="${ROUTE_HOME}"
    while [[ ! -d "${free_place}" ]]; do free_place="$(dirname "${free_place}")"; done
    free_mb="$(df --output=avail -m "${free_place}" | tail -n 1 | tr -d ' ')"

    if ${updating}; then
        say "$(t "Routendienst aktualisieren" "Updating the route service")"
    else
        say "$(t "Routendienst für Rentalars" "Route service for Rentalars")"
    fi
    row 24 "$(t "System" "System")" "${SYSTEM_NAME:-?} (${SYSTEM_ARCHITECTURE})${SYSTEM_NOTE}"
    [[ -n "${SYSTEM_MODEL}" ]] && row 24 "$(t "Gerät" "Device")" "${SYSTEM_MODEL}"
    row 24 "$(t "Arbeitsspeicher" "Memory")" "$(memory_text "${memory}"), $(t "${cores} Kerne" "${cores} cores")"
    if [[ -n "${region}" ]]; then
        row 24 "$(t "Region" "Region")" "$(region_name "${region}")"
    fi
    if [[ -n "${source_file}" ]]; then
        row 24 "$(t "Karte" "Map")" "${source_file} (${size_mb} MB)"
    else
        row 24 "$(t "Herunterladen" "Download")" "${download} ($(t "etwa" "about") ${size_mb} MB)"
        row 24 "$(t "Prüfung" "Check")" "$(t "MD5-Prüfsumme von Geofabrik" "MD5 checksum of Geofabrik") (${download}.md5)"
    fi
    row 24 "$(t "Programm" "Program")" "$(t "Paket ${ROUTINO_PACKAGE} der Distribution (Routino, AGPL-3.0)" "package ${ROUTINO_PACKAGE} of the distribution (Routino, AGPL-3.0)")"
    row 24 "$(t "Verarbeitung" "Processing")" "${splitter} --sort-ram-size=${sort_ram} --sort-threads=${threads}, $(t "für Kraftfahrzeuge" "for motor vehicles")"
    row 24 "$(t "Dauer" "Duration")" "$(region_duration "${size_mb}") ($(t "Schätzung" "estimate"))"
    row 24 "$(t "Platz" "Space")" "$(t "${needed_mb} MB frei nötig, frei sind ${free_mb} MB" "${needed_mb} MB free needed, ${free_mb} MB are free") (${free_place})"
    row 24 "$(t "Kartendaten" "Map data")" "${ROUTE_HOME}"
    row 24 "$(t "Für Rentalars" "For Rentalars")" "${ROUTE_LOCAL_FILE}"
    if [[ "${region}" == germany ]] && (( memory < ROUTE_FULL_MEMORY_MB )); then
        warn "$(t "Ganz Deutschland mit $(memory_text "${memory}") Arbeitsspeicher: Die Verarbeitung läuft im Sparmodus und kann viele Stunden dauern. Für kleine Server besser ein Bundesland, z. B. --region bayern." "All of Germany with $(memory_text "${memory}") of memory: processing runs in the slim mode and can take many hours. For small servers a Bundesland is better, e.g. --region bayern.")"
    fi
    if (( free_mb < needed_mb )); then
        warn "$(t "Zu wenig freier Platz: ${needed_mb} MB werden gebraucht, frei sind ${free_mb} MB. Ein Bundesland braucht weniger." "Not enough free space: ${needed_mb} MB are needed, ${free_mb} MB are free. A Bundesland needs less.")"
    fi
    if ${dry_run}; then
        note ""
        note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
        return 0
    fi
    (( free_mb >= needed_mb )) || fail "$(t "Abgebrochen: zu wenig freier Platz auf ${free_place}." "Stopped: not enough free space on ${free_place}.")"
    [[ -f "${CONFIG_FILE}" ]] || fail "$(t "${CONFIG_FILE} fehlt. Ist Rentalars installiert?" "${CONFIG_FILE} is missing. Is Rentalars installed?")"
    take_lock
    # Root downloads, processes and deletes here: only in folders nobody else can change.
    root_only "$(dirname "${ROUTE_HOME}")" \
        || fail "$(t "$(dirname "${ROUTE_HOME}") gehört nicht allein root. Abgebrochen – prüfen: ls -ld $(dirname "${ROUTE_HOME}")" "$(dirname "${ROUTE_HOME}") does not belong to root alone. Stopped – check: ls -ld $(dirname "${ROUTE_HOME}")")"
    mkdir -p "${ROUTE_HOME}"
    root_only "${ROUTE_HOME}" \
        || fail "$(t "${ROUTE_HOME} gehört nicht allein root. Abgebrochen – prüfen: ls -ld ${ROUTE_HOME}" "${ROUTE_HOME} does not belong to root alone. Stopped – check: ls -ld ${ROUTE_HOME}")"
    chmod 755 "${ROUTE_HOME}"

    # 1. Routino
    say "$(t "Routino installieren" "Installing Routino")"
    if [[ -z "${ROUTE_TEST_ROOT}" ]] && ! dpkg -s "${ROUTINO_PACKAGE}" > /dev/null 2>&1; then
        apt-get update -q
        DEBIAN_FRONTEND=noninteractive apt-get install -y -q "${ROUTINO_PACKAGE}" \
            || fail "$(t 'Das Paket routino ließ sich nicht installieren. Unter Ubuntu liegt es in der Paketquelle „universe“: sudo add-apt-repository universe' 'The package routino could not be installed. On Ubuntu it is in the “universe” repository: sudo add-apt-repository universe')"
        echo "${ROUTINO_PACKAGE}" >> "${ROUTE_PACKAGES_FILE}"
    fi
    local router splitter_path
    router="$(router_path)"
    splitter_path="$(command -v "${splitter}" 2> /dev/null || true)"
    [[ -n "${router}" && -n "${splitter_path}" ]] || fail "$(t "Routino ist nicht vollständig installiert (routino-router, ${splitter})." "Routino is not installed completely (routino-router, ${splitter}).")"
    if [[ -f "${ROUTINO_SHARE}/tagging-drive.xml" ]]; then tagging="${ROUTINO_SHARE}/tagging-drive.xml"; else tagging="${ROUTINO_SHARE}/tagging.xml"; fi
    note "$("${router}" --version 2>&1 | head -n 1 || true)"  # Routino prints its version on stderr

    # 2. The map
    local work data_date
    work="$(mktemp -d "${ROUTE_HOME}/work.XXXXXX")"
    # shellcheck disable=SC2064  # the folder is known now
    trap "rm -rf '${work}'" EXIT
    if [[ -n "${download}" ]]; then
        say "$(t "Karte herunterladen" "Downloading the map"): $(region_name "${region}")"
        local expected actual
        expected="$(curl -fsSL --proto '=https' --tlsv1.2 --max-time 60 "${download}.md5" | awk '{ print $1; exit }')" \
            || fail "$(t "Die Prüfsumme ${download}.md5 ließ sich nicht laden." "The checksum ${download}.md5 could not be loaded.")"
        [[ "${expected}" =~ ^[0-9a-f]{32}$ ]] || fail "$(t "${download}.md5 enthält keine MD5-Prüfsumme." "${download}.md5 holds no MD5 checksum.")"
        source_file="${work}/$(basename "${download}")"
        curl -fL --proto '=https' --tlsv1.2 --retry 3 -R -o "${source_file}" "${download}" \
            || fail "$(t "Die Karte ließ sich nicht herunterladen. Ohne Internet: Datei von Geofabrik auf den Server kopieren und --file DATEI angeben." "The map could not be downloaded. Without internet: copy the file of Geofabrik to the server and use --file FILE.")"
        actual="$(md5sum "${source_file}" | cut -d' ' -f1)"
        [[ "${actual}" == "${expected}" ]] \
            || fail "$(t "Die Prüfsumme der Karte stimmt nicht (erwartet ${expected}, erhalten ${actual}). Die Datei wurde gelöscht." "The checksum of the map does not match (expected ${expected}, got ${actual}). The file was deleted.")"
        row 24 "MD5" "${actual} $(t "geprüft" "checked")"
    fi
    # Geofabrik's file carries the time of its data (curl -R); a file of the operator's its own.
    data_date="$(date -r "${source_file}" +%F)"
    row 24 "$(t "Kartenstand" "Map data of")" "${data_date}"

    # 3. Processing
    say "$(t "Karte verarbeiten" "Processing the map") – $(region_duration "${size_mb}")"
    note "$(t "Fortschritt: tail -f ${ROUTE_LOG}" "Progress: tail -f ${ROUTE_LOG}")"
    local new_dir started seconds
    new_dir="$(mktemp -d "${ROUTE_HOME}/data-$(date +%Y%m%d)-XXXX")"
    started="$(date +%s)"
    if ! "${splitter_path}" --dir="${new_dir}" --prefix="${ROUTE_PREFIX}" --tagging="${tagging}" --tmpdir="${work}" \
            --sort-ram-size="${sort_ram}" --sort-threads="${threads}" --loggable --logtime "${source_file}" \
            > "${ROUTE_LOG}" 2>&1; then
        rm -rf "${new_dir}"
        tail -n 5 "${ROUTE_LOG}" >&2 || true
        fail "$(t "Die Verarbeitung der Karte schlug fehl; siehe ${ROUTE_LOG}. Die bisherige Karte bleibt in Gebrauch." "Processing the map failed; see ${ROUTE_LOG}. The map in use so far stays.")"
    fi
    seconds=$(( $(date +%s) - started ))
    chmod 755 "${new_dir}"
    find "${new_dir}" -type f -exec chmod 644 {} +
    chmod 644 "${ROUTE_LOG}"
    row 24 "$(t "Verarbeitet in" "Processed in")" "$(( seconds / 60 )) min $(( seconds % 60 )) s"
    row 24 "$(t "Kartendaten" "Map data")" "${new_dir} ($(du -sh "${new_dir}" | cut -f1))"

    # 4. A test route, as the service user – before Rentalars is told about the new map.
    say "$(t "Probefahrt" "Test route")"
    local km points
    points="${test_points:-$(points_of_data "${new_dir}")}"
    read -r -a points <<<"${points}"
    if (( ${#points[@]} != 4 )); then
        warn "$(t "Für diese Karte ist keine Probefahrt bekannt; sie wird ungeprüft verwendet." "No test route is known for this map; it is used unchecked.")"
    elif km="$(test_route "${router}" "${new_dir}" "${points[@]}")"; then
        row 24 "$(t "Probefahrt" "Test route")" "$(local_km "${km}") km"
    elif [[ -n "${test_points}" ]]; then
        rm -rf "${new_dir}"
        fail "$(t "Die Probefahrt mit der neuen Karte schlug fehl; die bisherige bleibt in Gebrauch. Siehe ${ROUTE_LOG}." "The test route with the new map failed; the map in use so far stays. See ${ROUTE_LOG}.")"
    else
        warn "$(t "Die Probefahrt zwischen zwei Punkten der Karte schlug fehl; die Karte wird trotzdem verwendet." "The test route between two points of the map failed; the map is used all the same.")"
    fi

    # 5. Rentalars uses the new map from now on; the old one goes.
    write_local_file routino "router=${router}" "data_dir=${new_dir}" "prefix=${ROUTE_PREFIX}" \
        "profiles=${ROUTINO_SHARE}/profiles.xml" "translations=${ROUTINO_SHARE}/translations.xml" \
        "region=${region}" "source=${source}" "data_date=${data_date}"
    local old
    for old in "${ROUTE_HOME}"/data-*; do
        [[ -d "${old}" && "${old}" != "${new_dir}" ]] || continue
        rm -rf "${old}"
        note "$(t "Bisherige Karte gelöscht: ${old}" "Map used before deleted: ${old}")"
    done
    if [[ -n "${download}" ]]; then
        if ${keep_file}; then
            mv "${source_file}" "${ROUTE_HOME}/"
            note "$(t "Download aufbewahrt: ${ROUTE_HOME}/$(basename "${source_file}")" "Download kept: ${ROUTE_HOME}/$(basename "${source_file}")")"
        fi
        # Otherwise it goes with the working folder.
    fi
    rm -rf "${work}"
    trap - EXIT
    say "$(t "Fertig." "Done.")"
    note "$(t 'Rentalars schlägt ab jetzt im Dialog eines Fahrzeugs auf einer Fahrt die geplanten Kilometer vor („Geplante km aus der Route vorschlagen“).' 'From now on Rentalars suggests the planned kilometres in the dialog of a vehicle on a trip (“Suggest planned km from the route”).')"
    note "$(t 'Die Straßen ändern sich: ab und zu aktualisieren mit „sudo rentalars route update“.' 'Roads change: update now and then with “sudo rentalars route update”.')"
}

# Root, except in the tests.
require_root_unless_test() {
    [[ -n "${ROUTE_TEST_ROOT}" ]] || require_root
}

do_update() {
    [[ -f "${ROUTE_LOCAL_FILE}" ]] || fail "$(t "Es ist kein Routendienst eingerichtet: sudo rentalars route install --region BUNDESLAND" "No route service is set up: sudo rentalars route install --region BUNDESLAND")"
    [[ -z "${region}" && -z "${file}" ]] || fail "$(t "update nimmt die eingerichtete Region; eine andere: sudo rentalars route install --region …" "update takes the region set up; another one: sudo rentalars route install --region …")"
    if [[ "$(local_value kind)" == "osrm" ]]; then
        say "$(t "Nichts zu aktualisieren: Die Karte des Routenservers $(local_value url) hält sein Betreiber aktuell." "Nothing to update: the operator of the routing server $(local_value url) keeps its map up to date.")"
        return 0
    fi
    region="$(local_value region)"
    [[ -n "${region}" ]] || fail "$(t "Der Routendienst wurde aus einer Datei eingerichtet ($(local_value source)). Neue Karte: sudo rentalars route install --file DATEI" "The route service was set up from a file ($(local_value source)). New map: sudo rentalars route install --file FILE")"
    updating=true
    do_install
}

do_register() {
    ${dry_run} || require_root_unless_test
    [[ -n "${url}" ]] || fail "$(t "register braucht --url." "register needs --url.")"
    url="${url%/}"
    is_route_server_url "${url}" \
        || fail "$(t "--url: eine Adresse mit https – oder mit http nur auf diesem Rechner (http://127.0.0.1:PORT)." "--url: an address with https – or with http on this machine only (http://127.0.0.1:PORT).")"
    say "$(t "Routenserver eintragen (OSRM)" "Registering a routing server (OSRM)")"
    row 24 "URL" "${url}"
    row 24 "$(t "Für Rentalars" "For Rentalars")" "${ROUTE_LOCAL_FILE}"
    note "$(t "Nur einen Server, den der Betreiber selbst betreibt oder der in Deutschland steht (NFA-050): Rentalars schickt ihm die Positionen der Orte einer Fahrt." "Only a server the operator runs himself or one hosted in Germany (NFA-050): Rentalars sends it the positions of the places of a trip.")"
    if ${dry_run}; then
        note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
        return 0
    fi
    # Frankfurt am Main → Würzburg; a server whose map lacks them still answers like OSRM ("NoSegment").
    local answer code km
    answer="$(curl -sS --max-time 20 --noproxy 127.0.0.1,localhost,::1 "${url}/route/v1/driving/8.682100,50.110900;9.953400,49.791300?overview=false" 2> /dev/null || true)"
    read -r code km < <(python3 -c 'import json, sys
try:
    answer = json.load(sys.stdin)
    print(answer.get("code", "?"), round(answer["routes"][0]["distance"] / 1000, 1) if answer.get("code") == "Ok" else "-")
except Exception:
    print("? -")' <<<"${answer}") || true
    case "${code}" in
        Ok) row 24 "$(t "Probefahrt" "Test route")" "Frankfurt am Main → Würzburg: $(local_km "${km}") km" ;;
        NoSegment|NoRoute) warn "$(t "Der Server antwortet, kennt aber keine Straßen bei Frankfurt am Main und Würzburg – richtig, wenn seine Karte eine andere Gegend zeigt." "The server answers, but knows no roads near Frankfurt am Main and Würzburg – right if its map shows another area.")" ;;
        *) fail "$(t "${url} antwortet nicht wie ein OSRM-Server (GET /route/v1/driving/…)." "${url} does not answer like an OSRM server (GET /route/v1/driving/…).")" ;;
    esac
    write_local_file osrm "url=${url}"
    say "$(t "Fertig." "Done.")"
}

do_remove() {
    ${dry_run} || require_root_unless_test
    say "$(t "Routendienst entfernen" "Removing the route service")"
    row 24 "$(t "Datei" "File")" "${ROUTE_LOCAL_FILE}"
    if ${keep_data}; then
        row 24 "$(t "Kartendaten" "Map data")" "${ROUTE_HOME} ($(t "bleiben" "stay"))"
    else
        row 24 "$(t "Kartendaten" "Map data")" "${ROUTE_HOME}"
        [[ -f "${ROUTE_PACKAGES_FILE}" ]] && row 24 "$(t "Pakete" "Packages")" "$(tr '\n' ' ' < "${ROUTE_PACKAGES_FILE}")"
    fi
    if ${dry_run}; then
        note "$(t "Probelauf: nichts wurde verändert." "Dry run: nothing was changed.")"
        return 0
    fi
    # First Rentalars stops using it, then the data go.
    rm -f "${ROUTE_LOCAL_FILE}"
    if ! ${keep_data} && [[ -d "${ROUTE_HOME}" ]]; then
        take_lock
        if [[ -f "${ROUTE_PACKAGES_FILE}" && -z "${ROUTE_TEST_ROOT}" ]]; then
            mapfile -t packages < "${ROUTE_PACKAGES_FILE}"
            DEBIAN_FRONTEND=noninteractive apt-get remove -y -q "${packages[@]}" \
                || warn "$(t "Pakete ließen sich nicht entfernen: ${packages[*]}" "Packages could not be removed: ${packages[*]}")"
        fi
        root_only "$(dirname "${ROUTE_HOME}")" && rm -rf "${ROUTE_HOME}"
    fi
    say "$(t "Fertig. Die Kilometer werden ab jetzt wieder von Hand eingetragen." "Done. From now on the kilometres are typed in by hand again.")"
}

do_status() {
    say "$(t "Routendienst" "Route service")"
    # /etc/rentalars is for root and the service; without access only root can tell.
    if [[ ! -x "$(dirname "${ROUTE_LOCAL_FILE}")" || ( -e "${ROUTE_LOCAL_FILE}" && ! -r "${ROUTE_LOCAL_FILE}" ) ]]; then
        require_root
    fi
    if [[ ! -f "${ROUTE_LOCAL_FILE}" ]]; then
        note "$(t "nicht eingerichtet – die Kilometer werden von Hand eingetragen." "not set up – the kilometres are typed in by hand.")"
        note "$(t "Einrichten: sudo rentalars route install --region BUNDESLAND ($(region_list)) oder --region germany" "Set up: sudo rentalars route install --region BUNDESLAND ($(region_list)) or --region germany")"
        return 0
    fi
    local kind
    kind="$(local_value kind)"
    if [[ "${kind}" == "osrm" ]]; then
        local server code
        server="$(local_value url)"
        row 24 "$(t "Art" "Kind")" "$(t "OSRM-Routenserver" "OSRM routing server")"
        row 24 "URL" "${server}"
        code="$(curl -sS --max-time 20 --noproxy 127.0.0.1,localhost,::1 "${server}/route/v1/driving/8.682100,50.110900;9.953400,49.791300?overview=false" 2> /dev/null \
            | python3 -c 'import json, sys
try:
    print(json.load(sys.stdin).get("code", "?"))
except Exception:
    print("?")' || true)"
        if [[ "${code}" == "Ok" || "${code}" == "NoSegment" || "${code}" == "NoRoute" ]]; then
            row 24 "$(t "antwortet" "answers")" "$(t "ja" "yes")"
        else
            row 24 "$(t "antwortet" "answers")" "$(t "NEIN" "NO")"
        fi
        return 0
    fi
    local region data_dir data_date age router points km
    region="$(local_value region)" data_dir="$(local_value data_dir)" data_date="$(local_value data_date)"
    router="$(local_value router)"
    row 24 "$(t "Art" "Kind")" "$(t "Routino auf diesem Server" "Routino on this server")"
    if [[ -n "${region}" ]]; then
        row 24 "$(t "Region" "Region")" "$(region_name "${region}")"
    else
        row 24 "$(t "Karte" "Map")" "$(local_value source)"
    fi
    if [[ -n "${data_date}" ]]; then
        # Calendar days, both dates read as UTC midnights: seconds since local midnight are wrong on the day the clocks
        # change (25 hours; "1 days old" for a map written that day).
        age=$(( ( $(date -u -d "$(date +%F)" +%s) - $(date -u -d "${data_date}" +%s) ) / 86400 ))
        if [[ "${age}" == 1 ]]; then
            old_text="$(t "1 Tag alt" "1 day old")"
        else
            old_text="$(t "${age} Tage alt" "${age} days old")"
        fi
        row 24 "$(t "Kartenstand" "Map data of")" "${data_date} (${old_text})"
    fi
    if [[ -d "${data_dir}" ]]; then
        row 24 "$(t "Kartendaten" "Map data")" "${data_dir} ($(du -sh "${data_dir}" 2> /dev/null | cut -f1))"
    else
        row 24 "$(t "Kartendaten" "Map data")" "${data_dir} – $(t "FEHLEN" "MISSING")"
    fi
    if [[ -x "${router}" ]]; then
        row 24 "Router" "${router} ($("${router}" --version 2>&1 | head -n 1 || true))"
    else
        row 24 "Router" "${router} – $(t "FEHLT" "MISSING")"
    fi
    points=()
    [[ -n "${region}" ]] && read -r -a points <<<"$(region_field "${region}" 4)"
    if (( ${#points[@]} == 4 )) && [[ -x "${router}" && -d "${data_dir}" ]]; then
        if km="$(test_route "${router}" "${data_dir}" "${points[@]}" 2> /dev/null)"; then
            row 24 "$(t "antwortet" "answers")" "$(t "ja" "yes") ($(t "Probefahrt" "test route") $(local_km "${km}") km)"
        else
            row 24 "$(t "antwortet" "answers")" "$(t "NEIN" "NO")"
        fi
    fi
    if [[ -n "${age:-}" ]] && (( age >= ROUTE_OLD_DAYS )); then
        note "$(t "Die Karte ist über ein halbes Jahr alt. Aktualisieren: sudo rentalars route update" "The map is more than half a year old. Update: sudo rentalars route update")"
    fi
}

case "${command}" in
    install)  do_install ;;
    update)   do_update ;;
    register) do_register ;;
    remove)   do_remove ;;
    status)   do_status ;;
    ""|help)  usage ;;
    *)        fail "$(t "Unbekannter Befehl: route ${command}. Möglich: install, update, register, remove, status." "Unknown command: route ${command}. Possible: install, update, register, remove, status.")" ;;
esac
