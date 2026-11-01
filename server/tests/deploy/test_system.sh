#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Tests of how the server scripts recognise the system and the device
# (NFA-063, NFA-070, NFA-042) – and the packages a version adds with the update (NFA-076).
#
#     bash tests/deploy/test_system.sh
#
# Runs the functions of deploy/lib.sh that decide about the operating system,
# the Raspberry Pi, the packages, the memory settings and the SD card – with
# made-up files in place of /etc/os-release, /proc/device-tree/model,
# /proc/meminfo and /sys/dev/block. Prints one line per case and ends with a
# failing status if one fails. Needs bash and the usual tools, nothing of
# Rentalars installed, and changes nothing on this computer.
#
# Run by scripts/check.sh and by tests/unit/test_080_pi.py. The installation
# itself on a real Raspberry Pi cannot be tried here; see "Erprobung" in
# docs/betrieb/installation.md.
set -euo pipefail
# UIX-029: the messages are compared in German; the English ones are tried at the end.
export RENTALARS_LANG=de
here="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
deploy="$(dirname "$(dirname "${here}")")/deploy"
# shellcheck source=deploy/lib.sh
source "${deploy}/lib.sh"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
cases=0
failures=0

# Compare a result with what is expected: expect DESCRIPTION EXPECTED ACTUAL
expect() {
    cases=$((cases + 1))
    if [[ "$2" == "$3" ]]; then
        printf 'ok    %s\n' "$1"
    else
        failures=$((failures + 1))
        printf 'FAIL  %s\n        expected: %s\n        got:      %s\n' "$1" "$2" "$3"
    fi
}

# Succeeds if a text contains a part: expect_in DESCRIPTION PART TEXT
expect_in() {
    if [[ "$3" == *"$2"* ]]; then expect "$1" "found" "found"; else expect "$1" "…$2…" "$3"; fi
}

# --- Made-up systems -------------------------------------------------------------------------

# An os-release file as the systems write it: os_release NAME ID VERSION_ID PRETTY_NAME
os_release() {
    local file="${work}/os-release-$1"
    {
        echo "PRETTY_NAME=\"$4\""
        echo "NAME=\"$4\""
        [[ -n "$3" ]] && echo "VERSION_ID=\"$3\""
        echo "ID=$2"
        [[ "$2" != "debian" ]] && echo "ID_LIKE=debian"
        echo 'HOME_URL="https://example.org/"'
    } > "${file}"
    echo "${file}"
}
ubuntu_2404="$(os_release ubuntu-2404 ubuntu 24.04 "Ubuntu 24.04.3 LTS")"
ubuntu_2604="$(os_release ubuntu-2604 ubuntu 26.04 "Ubuntu 26.04 LTS")"
ubuntu_2510="$(os_release ubuntu-2510 ubuntu 25.10 "Ubuntu 25.10")"
ubuntu_2204="$(os_release ubuntu-2204 ubuntu 22.04 "Ubuntu 22.04.5 LTS")"
# Raspberry Pi OS calls itself Debian (64 bit) or Raspbian (32 bit).
debian_13="$(os_release debian-13 debian 13 "Debian GNU/Linux 13 (trixie)")"
debian_12="$(os_release debian-12 debian 12 "Debian GNU/Linux 12 (bookworm)")"
debian_14="$(os_release debian-14 debian 14 "Debian GNU/Linux 14 (forky)")"
debian_testing="$(os_release debian-testing debian "" "Debian GNU/Linux forky/sid")"
raspbian_13="$(os_release raspbian-13 raspbian 13 "Raspbian GNU/Linux 13 (trixie)")"
fedora="$(os_release fedora fedora 42 "Fedora Linux 42 (Server Edition)")"

# The model file of the device tree; the firmware ends the name with a zero byte.
model() {
    local file="${work}/model-${1// /-}"
    printf '%s\0' "$1" > "${file}"
    echo "${file}"
}
no_device_tree="${work}/no-device-tree"   # an x86 server has none
pi_4="$(model "Raspberry Pi 4 Model B Rev 1.5")"
pi_5="$(model "Raspberry Pi 5 Model B Rev 1.0")"
pi_400="$(model "Raspberry Pi 400 Rev 1.0")"
pi_500="$(model "Raspberry Pi 500 Rev 1.0")"
cm_4="$(model "Raspberry Pi Compute Module 4 Rev 1.0")"
cm_5="$(model "Raspberry Pi Compute Module 5 Rev 1.0")"
pi_3="$(model "Raspberry Pi 3 Model B Plus Rev 1.3")"
other_board="$(model "Pine64 RockPro64 v2.1")"

# Run check_system in a subshell; prints "status|ID|VERSION|NAME|ARCH|MODEL|NOTE|messages".
system() {
    local output status=0
    output="$( (check_system "$1" "$2" "$3" && printf '%s|%s|%s|%s|%s|%s' "${SYSTEM_ID}" "${SYSTEM_VERSION}" \
        "${SYSTEM_NAME}" "${SYSTEM_ARCHITECTURE}" "${SYSTEM_MODEL}" "${SYSTEM_NOTE}") 2>&1)" || status=$?
    # Without the colours of "fail".
    printf '%s|%s' "${status}" "$(printf '%s' "${output}" | sed 's/\x1b\[[0-9;]*m//g' | tr '\n' ' ' | sed 's/^ *//; s/ *$//')"
}

echo "== Ubuntu on an x86 server: exactly as before"
expect "Ubuntu 24.04, amd64" "0|ubuntu|24.04|Ubuntu 24.04.3 LTS|amd64||" "$(system "${ubuntu_2404}" "${no_device_tree}" amd64)"
expect "Ubuntu 26.04, amd64" "0|ubuntu|26.04|Ubuntu 26.04 LTS|amd64||" "$(system "${ubuntu_2604}" "${no_device_tree}" amd64)"
expect "Ubuntu 25.10: not refused, but not tried" \
    "0|ubuntu|25.10|Ubuntu 25.10|amd64||  – nicht erprobt; erprobt sind 24.04 LTS und 26.04 LTS" \
    "$(system "${ubuntu_2510}" "${no_device_tree}" amd64)"
expect "Ubuntu 22.04: refused" \
    "1|Fehler: Ubuntu 22.04 ist zu alt. Gebraucht wird Ubuntu Server 24.04 LTS oder 26.04 LTS." \
    "$(system "${ubuntu_2204}" "${no_device_tree}" amd64)"
expect "Debian on an x86 server: refused" \
    "1|Fehler: Dieses Skript ist für Ubuntu Server gemacht; Debian nur als Raspberry Pi OS auf einem Raspberry Pi (gefunden: Debian GNU/Linux 13 (trixie))." \
    "$(system "${debian_13}" "${no_device_tree}" amd64)"
expect "another system: refused, without a word about the Raspberry Pi" \
    "1|Fehler: Dieses Skript ist für Ubuntu Server gemacht (gefunden: Fedora Linux 42 (Server Edition))." \
    "$(system "${fedora}" "${no_device_tree}" amd64)"
expect "no os-release at all: refused" \
    "1|Fehler: Dieses Skript ist für Ubuntu Server gemacht (gefunden: unbekannt)." \
    "$(system "${work}/missing" "${no_device_tree}" amd64)"
expect "a board that is not a Raspberry Pi counts as any computer" \
    "0|ubuntu|24.04|Ubuntu 24.04.3 LTS|arm64||" "$(system "${ubuntu_2404}" "${other_board}" arm64)"

echo "== Raspberry Pi with Ubuntu Server for the Pi"
expect "Raspberry Pi 4, Ubuntu 24.04" \
    "0|ubuntu|24.04|Ubuntu 24.04.3 LTS|arm64|Raspberry Pi 4 Model B Rev 1.5|" "$(system "${ubuntu_2404}" "${pi_4}" arm64)"
expect "Raspberry Pi 5, Ubuntu 26.04" \
    "0|ubuntu|26.04|Ubuntu 26.04 LTS|arm64|Raspberry Pi 5 Model B Rev 1.0|" "$(system "${ubuntu_2604}" "${pi_5}" arm64)"
expect "Raspberry Pi 4, Ubuntu 22.04: refused like on a server" \
    "1|Fehler: Ubuntu 22.04 ist zu alt. Gebraucht wird Ubuntu Server 24.04 LTS oder 26.04 LTS." \
    "$(system "${ubuntu_2204}" "${pi_4}" arm64)"

echo "== Raspberry Pi with Raspberry Pi OS"
expect "Raspberry Pi 5, Raspberry Pi OS (Debian 13)" \
    "0|debian|13|Debian GNU/Linux 13 (trixie)|arm64|Raspberry Pi 5 Model B Rev 1.0|" "$(system "${debian_13}" "${pi_5}" arm64)"
expect "Raspberry Pi 4, Raspberry Pi OS (Debian 13)" \
    "0|debian|13|Debian GNU/Linux 13 (trixie)|arm64|Raspberry Pi 4 Model B Rev 1.5|" "$(system "${debian_13}" "${pi_4}" arm64)"
for board in "${pi_400}" "${pi_500}" "${cm_4}" "${cm_5}"; do
    result="$(system "${debian_13}" "${board}" arm64)"
    expect "$(tr -d '\0' < "${board}"): intended, no note" "" "${result##*|}"
done
expect "Raspberry Pi OS on Debian 12: refused" \
    "1|Fehler: Debian GNU/Linux 12 (bookworm) ist zu alt. Gebraucht wird Raspberry Pi OS auf Basis von Debian 13 (trixie), 64 Bit – oder Ubuntu Server ab 24.04 LTS für den Raspberry Pi." \
    "$(system "${debian_12}" "${pi_4}" arm64)"
expect "Debian 14: not refused, but not tried" \
    "0|debian|14|Debian GNU/Linux 14 (forky)|arm64|Raspberry Pi 5 Model B Rev 1.0|  – nicht erprobt; vorgesehen ist Raspberry Pi OS auf Basis von Debian 13" \
    "$(system "${debian_14}" "${pi_5}" arm64)"
expect "Debian testing (no version number): not refused, but not tried" \
    "0|debian||Debian GNU/Linux forky/sid|arm64|Raspberry Pi 5 Model B Rev 1.0|  – nicht erprobt; vorgesehen ist Raspberry Pi OS auf Basis von Debian 13" \
    "$(system "${debian_testing}" "${pi_5}" arm64)"
expect "Raspberry Pi 3: not refused, but not intended" \
    "0|debian|13|Debian GNU/Linux 13 (trixie)|arm64|Raspberry Pi 3 Model B Plus Rev 1.3|  – nicht erprobt; vorgesehen sind Raspberry Pi 4 und 5" \
    "$(system "${debian_13}" "${pi_3}" arm64)"
expect "another system on a Raspberry Pi: refused, with the hint" \
    "1|Fehler: Dieses Skript ist für Ubuntu Server gemacht (gefunden: Fedora Linux 42 (Server Edition)). Auf einem Raspberry Pi geht auch Raspberry Pi OS auf Basis von Debian 13, 64 Bit." \
    "$(system "${fedora}" "${pi_5}" arm64)"

echo "== 64 bit"
result="$(system "${raspbian_13}" "${pi_4}" armhf)"
expect_in "Raspberry Pi OS with 32 bit: refused" "1|Fehler: Rentalars braucht ein 64-Bit-System; hier läuft eines mit 32 Bit (armhf)." "${result}"
expect_in "  … and told what to install" '"Raspberry Pi OS Lite (64-bit)"' "${result}"
result="$(system "${debian_13}" "${pi_5}" armhf)"
expect_in "a 32-bit system on a 64-bit kernel: refused" "1|Fehler: Rentalars braucht ein 64-Bit-System" "${result}"
expect "32 bit on an x86 computer: refused, without a word about the Raspberry Pi" \
    "1|Fehler: Rentalars braucht ein 64-Bit-System; hier läuft eines mit 32 Bit (i386)." \
    "$(system "${ubuntu_2404}" "${no_device_tree}" i386)"

echo "== Packages"
# The list for Ubuntu, in its order: an x86 server gets exactly these – with ffmpeg (NFA-076)
# for the videos in the chat.
base="python3 python3-venv python3-dev build-essential pkg-config libmariadb-dev mariadb-client nginx libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 openssl curl rsync ca-certificates ffmpeg"
packages() { system_packages "$@" | tr '\n' ' ' | sed 's/ $//'; }
expect "Ubuntu, MariaDB here, Let's Encrypt" "${base} mariadb-server certbot" "$(packages ubuntu true letsencrypt "")"
expect "Raspberry Pi OS: the same names" "${base} mariadb-server certbot" "$(packages debian true letsencrypt "")"
expect "database elsewhere, own certificate: no MariaDB server, no certbot" "${base}" "$(packages debian false own "")"
expect "selfsigned: no certbot" "${base} mariadb-server" "$(packages ubuntu true selfsigned "")"
expect "DNS proof with a plugin" "${base} mariadb-server certbot python3-certbot-dns-cloudflare" "$(packages debian true dns cloudflare)"
status=0
( system_packages fedora true letsencrypt "" ) > /dev/null 2>&1 || status=$?
expect "an unknown system has no package list" "1" "${status}"
# NFA-076: what a later version added comes with the update – from the list of the new version.
expect "added since the first installation: ffmpeg" "ffmpeg" "$(added_packages | tr '\n' ' ' | sed 's/ $//')"
for package in $(added_packages); do
    expect_in "  … $package is in the list of the installation as well" " ${package}" " $(packages ubuntu false own "")"
done
expect "the list of the new version is read from its lib.sh" "ffmpeg" "$(packages_added_by "${deploy}/lib.sh")"
printf '#!/usr/bin/env bash\nnew_thing() { :; }\n' > "${work}/old-lib.sh"
expect "a version without such a list adds nothing" "" "$(packages_added_by "${work}/old-lib.sh")"
# shellcheck disable=SC2317  # called through missing_packages
fake_dpkg_query() { [[ "${*: -1}" == ffmpeg ]] && return 1; echo "install ok installed"; }
expect "only missing packages are installed" "ffmpeg" "$(missing_packages fake_dpkg_query nginx ffmpeg)"
# shellcheck disable=SC2317  # called through missing_packages
fake_dpkg_query() { echo "install ok installed"; }
expect "nothing missing: nothing to install" "" "$(missing_packages fake_dpkg_query nginx ffmpeg)"

echo "== Packages with the update: ai.sh refresh installs them"
# The update.sh runs only one script of the new version: "ai.sh refresh". dpkg-query and apt-get are
# made up here; installed is what FAKE_INSTALLED names.
tools="${work}/tools"
mkdir -p "${tools}" "${work}/ai-root"
cat > "${tools}/dpkg-query" <<'FAKE'
#!/usr/bin/env bash
for package in ${FAKE_INSTALLED:-}; do
    if [[ "${*: -1}" == "${package}" ]]; then echo "install ok installed"; exit 0; fi
done
exit 1
FAKE
cat > "${tools}/apt-get" <<FAKE
#!/usr/bin/env bash
echo "\$*" >> "${work}/apt.log"
exit \${FAKE_APT_STATUS:-0}
FAKE
chmod +x "${tools}/dpkg-query" "${tools}/apt-get"
ai_refresh() {
    RENTALARS_AI_TEST_ROOT="${work}/ai-root" RENTALARS_CONFIG="${work}/ai-root/rentalars.conf" \
        RENTALARS_DPKG_QUERY="${tools}/dpkg-query" RENTALARS_APT_GET="${tools}/apt-get" FAKE_INSTALLED="$1" \
        FAKE_APT_STATUS="${2:-0}" bash "${deploy}/ai.sh" refresh 2>&1
    echo "|$?"
}
result="$(ai_refresh "nginx")"
expect_in "ffmpeg missing: refresh installs it" "Installiere fehlende Pakete: ffmpeg" "${result}"
expect_in "  … and ends well" "|0" "${result}"
expect "  … with apt-get, waiting up to two minutes for an apt running at the same time" \
    "-o DPkg::Lock::Timeout=120 update -qq|-o DPkg::Lock::Timeout=120 install -y -qq --no-install-recommends ffmpeg" \
    "$(paste -sd '|' "${work}/apt.log")"
rm -f "${work}/apt.log"
expect "nothing missing: nothing said, apt not called" "|0 apt.log absent" \
    "$(ai_refresh "nginx ffmpeg") apt.log $([[ -e "${work}/apt.log" ]] && echo present || echo absent)"
result="$(ai_refresh "nginx" 100)"
expect_in "apt fails: a warning" "Die Pakete ffmpeg ließen sich nicht installieren; Rentalars läuft trotzdem." "${result}"
expect_in "  … and the update goes on" "|0" "${result}"

echo "== Memory and its settings"
meminfo() {
    local file="${work}/meminfo-$1"
    printf 'MemTotal:       %s kB\nMemFree:          812344 kB\nMemAvailable:    2901212 kB\n' "$1" > "${file}"
    echo "${file}"
}
expect "memory of a Raspberry Pi 4 with 4 GB" "3793" "$(memory_mb "$(meminfo 3884292)")"
expect "no meminfo" "0" "$(memory_mb "${work}/missing")"
expect "as people say it" "3,7 GB" "$(memory_text 3793)"
expect "8 GB: the settings of the reference system" "" "$(sizing_for_memory 7820)"
expect "4 GB: the settings of the reference system" "" "$(sizing_for_memory 3793)"
expect "just under 4 GB" "3 512M" "$(sizing_for_memory 3499)"
expect "2 GB" "3 512M" "$(sizing_for_memory 1849)"
expect "1 GB" "2 256M" "$(sizing_for_memory 906)"
expect "unknown memory: keep the settings" "" "$(sizing_for_memory 0)"

unit="${work}/rentalars.service"
original="${deploy}/systemd/rentalars.service"
for case in "x86 server with 1 GB||906" "Raspberry Pi 5 with 8 GB|Raspberry Pi 5 Model B Rev 1.0|7820" "Raspberry Pi 4 with 4 GB|Raspberry Pi 4 Model B Rev 1.5|3793"; do
    IFS='|' read -r description board memory <<<"${case}"
    cp "${original}" "${unit}"
    adapt_workers "${unit}" "${board}" "${memory}"
    if cmp -s "${original}" "${unit}"; then same="unchanged"; else same="changed"; fi
    expect "workers: ${description}" "unchanged" "${same}"
done
cp "${original}" "${unit}"
adapt_workers "${unit}" "Raspberry Pi 4 Model B Rev 1.5" 1849
expect "workers: Raspberry Pi 4 with 2 GB" "--workers 3 --preload \\" "$(grep -o -- '--workers.*' "${unit}")"
expect "  … and nothing else of the unit changed" "1" "$(diff "${original}" "${unit}" | grep -c '^>')"

settings="${work}/62-rentalars-memory.cnf"
write_database_memory_settings "${settings}" "" 906
expect "MariaDB: no file on an x86 server" "absent" "$([[ -e "${settings}" ]] && echo present || echo absent)"
echo "kept" > "${settings}"
write_database_memory_settings "${settings}" "" 906
expect "MariaDB: an x86 server keeps whatever is there" "kept" "$(cat "${settings}")"
write_database_memory_settings "${settings}" "Raspberry Pi 4 Model B Rev 1.5" 1849
expect "MariaDB: Raspberry Pi with 2 GB" "innodb_buffer_pool_size = 512M" "$(grep '^innodb' "${settings}")"
expect_in "  … in the section of the server" "[mysqld]" "$(cat "${settings}")"
write_database_memory_settings "${settings}" "Raspberry Pi 4 Model B Rev 1.5" 3793
expect "MariaDB: Raspberry Pi with 4 GB needs no file" "absent" "$([[ -e "${settings}" ]] && echo present || echo absent)"

echo "== SD card"
sd_card() { if names_include_sd_card "$@"; then echo yes; else echo no; fi; }
expect "a partition of the SD card" "yes" "$(sd_card mmcblk0p2)"
expect "the eMMC of a Compute Module" "yes" "$(sd_card dm-0 mmcblk0p3)"
expect "SSD on USB, NVMe, nothing" "no" "$(sd_card sda2 nvme0n1p2 dm-1)"
expect "no names at all" "no" "$(sd_card)"

# A made-up /sys/dev/block: the SD card, an encrypted volume on it, a USB SSD.
sys="${work}/sys"
mkdir -p "${sys}/dev/block" \
    "${sys}/devices/platform/emmc2bus/mmc0/block/mmcblk0/mmcblk0p2" \
    "${sys}/devices/platform/emmc2bus/mmc0/block/mmcblk0/mmcblk0p3" \
    "${sys}/devices/virtual/block/dm-0/slaves" \
    "${sys}/devices/platform/usb/block/sda/sda2"
ln -s ../../devices/platform/emmc2bus/mmc0/block/mmcblk0/mmcblk0p2 "${sys}/dev/block/179:2"
ln -s ../../devices/virtual/block/dm-0 "${sys}/dev/block/254:0"
ln -s ../../../../platform/emmc2bus/mmc0/block/mmcblk0/mmcblk0p3 "${sys}/devices/virtual/block/dm-0/slaves/mmcblk0p3"
ln -s ../../devices/platform/usb/block/sda/sda2 "${sys}/dev/block/8:2"
names() { block_device_names "$1" | tr '\n' ' ' | sed 's/ $//'; }
expect "partition of the SD card" "mmcblk0p2" "$(names "${sys}/dev/block/179:2")"
expect "encrypted volume on the SD card" "dm-0 mmcblk0p3" "$(names "${sys}/dev/block/254:0")"
expect "SSD on USB" "sda2" "$(names "${sys}/dev/block/8:2")"
expect "unknown device number" "" "$(names "${sys}/dev/block/0:31")"

# storage_devices asks findmnt for the device number of the folder.
expect "a folder on the SD card" "mmcblk0p2" "$(findmnt() { echo " 179:2"; }; storage_devices /var/lib "${sys}/dev/block")"
expect "a folder that does not exist yet: its parent counts" "dm-0 mmcblk0p3" \
    "$(findmnt() { [[ "$5" == "${work}" ]] && echo "254:0"; }; storage_devices "${work}/not/yet" "${sys}/dev/block" | tr '\n' ' ' | sed 's/ $//')"
expect "findmnt does not know: nothing" "" "$(findmnt() { return 1; }; storage_devices /var/lib "${sys}/dev/block")"
status=0
storage_devices / > /dev/null 2>&1 || status=$?
expect "the real root folder of this computer can be asked" "0" "${status}"

on_sd() {
    storage_devices() { case "$1" in /var/lib|/var/lib/mysql) echo mmcblk0p2 ;; /var/backups*) echo sda1 ;; esac; }
    places_on_sd_card "$@" | tr '\n' ' ' | sed 's/ $//'
}
expect "database and files on the SD card, backups on an SSD" "/var/lib" "$(on_sd /var/lib /var/backups)"
expect "of an installation on a Raspberry Pi" "/var/lib/mysql" "$(
    device_model() { echo "Raspberry Pi 5 Model B Rev 1.0"; }
    config_get() { echo "$3"; }
    database_is_local() { return 0; }
    storage_devices() { case "$1" in /var/lib/mysql) echo mmcblk0p2 ;; *) echo nvme0n1p2 ;; esac; }
    installation_places_on_sd_card
)"
expect "of an installation on any other computer: nothing is even asked" "" "$(
    device_model() { :; }
    storage_devices() { echo mmcblk0p2; }
    installation_places_on_sd_card
)"

echo "== Configuration file and files that root puts into the data folder (S5, S6)"
# protect_configuration: the file belongs to the service account, no group may read it, and nothing else is touched.
expect "the configuration file: owner and mode" "chown rentalars:root ${work}/rentalars.conf|chmod 400 ${work}/rentalars.conf|" "$(
    : > "${work}/rentalars.conf"
    log="${work}/protect.log"; : > "${log}"
    chown() { printf 'chown %s|' "$*" >> "${log}"; }
    chmod() { printf 'chmod %s|' "$*" >> "${log}"; }
    protect_configuration "${work}/rentalars.conf"
    cat "${log}"
)"
expect "no configuration file: nothing is done" "" "$(
    log="${work}/protect2.log"; : > "${log}"
    chown() { printf 'chown %s|' "$*" >> "${log}"; }
    chmod() { printf 'chmod %s|' "$*" >> "${log}"; }
    protect_configuration "${work}/missing.conf"
    cat "${log}"
)"
# NGINX stays in the group of the service account: without it it cannot reach the socket of the application (502).
# shellcheck disable=SC2016  # the text searched for contains ${...} on purpose
expect_in "the installer keeps www-data in the group of the service account" 'usermod -a -G "${SERVICE_USER}" www-data' "$(cat "${deploy}/install.sh")"
expect_in "the socket of the application is open for that group" "--umask 007" "$(cat "${deploy}/systemd/rentalars.service")"
# place_file: a link laid at the name by the service account is replaced, not followed.
expect "a link at the name of the status file is not followed" "unchanged|file|content" "$(
    victim="${work}/victim"; echo unchanged > "${victim}"
    folder="${work}/datafolder"; mkdir -p "${folder}"
    ln -s "${victim}" "${folder}/backup-status.json"
    echo content > "${work}/new-status.json"
    place_file "${work}/new-status.json" "${folder}/backup-status.json"
    kind="file"; [[ -L "${folder}/backup-status.json" ]] && kind="link"
    echo "$(cat "${victim}")|${kind}|$(cat "${folder}/backup-status.json")"
)"

# restore.sh: the working folder is root's, and the files are put in place without following a link.
# shellcheck disable=SC2016  # the text searched for contains ${...} on purpose
expect_in "the restore unpacks in the folder of the backups" 'mktemp -d "${backup_dir}/.restore.XXXXXX"' "$(cat "${deploy}/restore.sh")"
# shellcheck disable=SC2016  # the text searched for contains ${...} on purpose
expect_in "the restore replaces the media folder without following a link" 'mv -T "${work}/media" "${data_dir}/media"' "$(cat "${deploy}/restore.sh")"
# shellcheck disable=SC2016  # the text searched for contains ${...} on purpose
expect_in "the backup puts its status file in place without following a link" 'place_file "${work}/backup-status.json"' "$(cat "${deploy}/backup.sh")"

# S8: the address of a visitor behind a server that is put in front of this one.
expect "no trusted proxy: no address is taken from a header" "no|no" "$(
    write_realip_snippet "${work}/realip.conf" ""
    grep -q set_real_ip_from "${work}/realip.conf" && a=yes || a=no
    grep -q real_ip_header "${work}/realip.conf" && b=yes || b=no
    echo "${a}|${b}"
)"
expect "trusted proxies: one line each, then the header" "set_real_ip_from 10.0.0.1;|set_real_ip_from 192.168.0.0/24;|set_real_ip_from 2001:db8::/32;|real_ip_header X-Forwarded-For;|real_ip_recursive on;|" "$(
    write_realip_snippet "${work}/realip.conf" "10.0.0.1, 192.168.0.0/24,2001:db8::/32"
    grep -v '^#' "${work}/realip.conf" | tr '\n' '|'
)"
expect "something that is no address is not written into the configuration" "set_real_ip_from 10.0.0.1;|real_ip_header X-Forwarded-For;|real_ip_recursive on;|" "$(
    write_realip_snippet "${work}/realip.conf" "10.0.0.1, evil;rm, 1.2.3.4/xx, \$host" 2> /dev/null
    grep -v '^#' "${work}/realip.conf" | tr '\n' '|'
)"
expect "only real addresses, no network of everything, no comment, no file names" "set_real_ip_from 10.0.0.1;|set_real_ip_from 2001:db8::1;|real_ip_header X-Forwarded-For;|real_ip_recursive on;|" "$(
    (cd "${work}" && : > somefile && write_realip_snippet "${work}/realip.conf" "bad, 1.2.3.4.5, 0.0.0.0/0, ::/0, *, 256.0.0.1, 10.0.0.1, 2001:db8::1 # 8.8.8.8" 2> /dev/null)
    grep -v '^#' "${work}/realip.conf" | tr '\n' '|'
)"
# shellcheck disable=SC2016  # the text searched for contains ${...} on purpose
expect_in "nginx-site sees a changed trusted_proxies also when the site matches the template" 'cmp -s "${work}/realip" "${NGINX_REALIP_SNIPPET}"' "$(cat "${deploy}/nginx-site.sh")"
# shellcheck disable=SC2016  # the text searched for contains ${...} on purpose
expect_in "nginx-site puts the file of the trusted addresses back when NGINX refuses the new configuration" 'cp -p "${work}/realip.before" "${NGINX_REALIP_SNIPPET}"' "$(cat "${deploy}/nginx-site.sh")"
site_before='server {
    listen 443 ssl;
    ssl_certificate     /etc/c.pem;
    ssl_certificate_key /etc/k.pem;
}
server {
    ssl_certificate /etc/other.pem;
}'
expect "an older site gets the line in front of its first certificate – once" "1|3" "$(
    printf '%s\n' "${site_before}" > "${work}/site.conf"
    ensure_realip_include "${work}/site.conf"
    ensure_realip_include "${work}/site.conf"
    first="$(grep -c 'include snippets/rentalars-realip.conf;' "${work}/site.conf")"
    line="$(grep -n 'include snippets/rentalars-realip.conf;' "${work}/site.conf" | head -n 1 | cut -d: -f1)"
    echo "${first}|${line}"
)"

echo "== German or English (UIX-029)"
expect "English: refused in English" \
    "1|Error: Rentalars needs a 64-bit system; this one runs 32 bit (i386)." \
    "$(RENTALARS_LANG=en system "${ubuntu_2404}" "${no_device_tree}" i386)"
expect "English: the note on an untried version" \
    "0|ubuntu|25.10|Ubuntu 25.10|amd64||  – not tried; tried are 24.04 LTS and 26.04 LTS" \
    "$(RENTALARS_LANG=en system "${ubuntu_2510}" "${no_device_tree}" amd64)"
expect "English: memory with a decimal point" "3.7 GB" "$(RENTALARS_LANG=en memory_text 3793)"
expect "the locale decides without RENTALARS_LANG: German" "de" "$(unset RENTALARS_LANG; LC_ALL="" LC_MESSAGES="" LANG=de_DE.UTF-8 operator_language)"
expect "the locale decides without RENTALARS_LANG: English" "en" "$(unset RENTALARS_LANG; LC_ALL="" LC_MESSAGES="" LANG=C.UTF-8 operator_language)"
expect "LC_ALL comes before LANG" "en" "$(unset RENTALARS_LANG; LC_ALL=C.UTF-8 LANG=de_DE.UTF-8 operator_language)"

echo
echo "${cases} cases, ${failures} failed."
[[ "${failures}" -eq 0 ]]
