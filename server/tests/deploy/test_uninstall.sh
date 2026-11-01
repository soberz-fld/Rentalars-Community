#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Tests of "sudo rentalars uninstall" (deploy/uninstall.sh, uninstall).
#
#     bash tests/deploy/test_uninstall.sh
#
# Builds a made-up server in a temporary folder – the files the installer makes, below a test root – and runs the
# script against it. The commands that would change a real system (systemctl, mariadb, nginx, certbot, getent,
# userdel, groupdel, gpasswd) are stand-ins that write what they were asked to do into a log. So the tests can
# say exactly what was removed, what was kept, which commands ran and in which order. Prints one line per case and
# ends with a failing status if one fails. Needs bash, python3 and the usual tools; changes nothing outside its folder.
#
# The hooks in the script (RENTALARS_UNINSTALL_TEST_ROOT, _STUBS, _TEST_INTERACTIVE) are described at the top of
# deploy/uninstall.sh. Run by scripts/check.sh and by tests/unit/test_095_uninstall.py.
# The checks of the installer's text look for fixed pieces of shell code in single quotes.
# shellcheck disable=SC2016
set -euo pipefail
export RENTALARS_LANG=de
here="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
deploy="$(dirname "$(dirname "${here}")")/deploy"
script="${deploy}/uninstall.sh"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
cases=0
failures=0

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
expect_not_in() {
    if [[ "$3" != *"$2"* ]]; then expect "$1" "absent" "absent"; else expect "$1" "no …$2…" "$3"; fi
}

# --- The stand-ins -------------------------------------------------------------------------------------------------------

stubs="${work}/stubs"
mkdir -p "${stubs}"
write_stub() { # write_stub NAME – the body comes on standard input
    { echo '#!/usr/bin/env bash'; cat; } > "${stubs}/$1"
    chmod +x "${stubs}/$1"
}
write_stub systemctl <<'STUB'
echo "systemctl $*" >> "${STUB_LOG}"
unit="${!#}"
case "$1" in
    is-active)
        # NGINX: as the test says. A unit of Rentalars runs until it is stopped – unless it is one that does not stop (FAKE_STUCK_UNITS).
        if [[ "${unit}" == nginx ]]; then [[ "${FAKE_NGINX_ACTIVE:-0}" == 0 ]] && echo active || echo inactive; exit "${FAKE_NGINX_ACTIVE:-0}"; fi
        if [[ -e "${STUB_STATE}/stopped-${unit}" ]]; then echo inactive; exit 3; fi
        echo active; exit 0 ;;
    stop)
        case " ${FAKE_STUCK_UNITS:-} " in *" ${unit} "*) ;; *) touch "${STUB_STATE}/stopped-${unit}" ;; esac ;;
esac
exit 0
STUB
write_stub nginx <<'STUB'
echo "nginx $*" >> "${STUB_LOG}"
if [[ "${FAKE_NGINX_TEST:-0}" != 0 ]]; then echo "nginx: [emerg] test failed" >&2; exit "${FAKE_NGINX_TEST}"; fi
exit 0
STUB
write_stub certbot <<'STUB'
echo "certbot $*" >> "${STUB_LOG}"
exit "${FAKE_CERTBOT:-0}"
STUB
write_stub mariadb <<'STUB'
query=""
arguments=("$@")
for ((i = 0; i < ${#arguments[@]}; i++)); do
    [[ "${arguments[i]}" == "-e" ]] && query="${arguments[i + 1]}"
done
if [[ -z "${query}" ]]; then
    input="$(cat)"
    printf 'mariadb < %s\n' "$(tr '\n' ' ' <<<"${input}")" >> "${STUB_LOG}"
    # A slow statement, for the tests that send a signal while it runs.
    if [[ -n "${FAKE_MARIADB_SLOW:-}" ]]; then touch "${STUB_STATE}/in-statement"; sleep "${FAKE_MARIADB_SLOW}"; fi
    exit "${FAKE_MARIADB_WRITE:-0}"
fi
echo "mariadb -e ${query}" >> "${STUB_LOG}"
case "${query}" in
    "SELECT 1") echo 1; exit "${FAKE_MARIADB:-0}" ;;
    *SCHEMA_NAME*) tr ' ' '\n' <<<"${FAKE_SCHEMAS-rentalars}" ;;
    "SHOW GRANTS"*) printf '%s\n' "${FAKE_GRANTS-GRANT USAGE ON *.* TO \`rentalars\`@\`localhost\` IDENTIFIED BY PASSWORD '*X'
GRANT ALL PRIVILEGES ON \`rentalars\`.* TO \`rentalars\`@\`localhost\`}" ;;
    *information_schema.TABLES*) printf '%s\n' "${FAKE_TABLES-TABLE core_user
TABLE core_role
VIEW core_view}" ;;
esac
exit 0
STUB
write_stub getent <<'STUB'
echo "getent $*" >> "${STUB_LOG}"
case "$1" in
    passwd)
        [[ -e "${STUB_STATE}/user-removed" || "${FAKE_NO_USER:-0}" == 1 ]] && exit 2
        echo "${FAKE_PASSWD-rentalars:x:998:998::/var/lib/rentalars:/usr/sbin/nologin}" ;;
    group)
        [[ "${FAKE_GROUP_STAYS:-0}" == 1 && ! -e "${STUB_STATE}/group-removed" ]] && { echo "rentalars:x:998:www-data"; exit 0; }
        exit 2 ;;
esac
STUB
write_stub userdel <<'STUB'
echo "userdel $*" >> "${STUB_LOG}"
touch "${STUB_STATE}/user-removed"
STUB
write_stub groupdel <<'STUB'
echo "groupdel $*" >> "${STUB_LOG}"
touch "${STUB_STATE}/group-removed"
STUB
write_stub gpasswd <<'STUB'
echo "gpasswd $*" >> "${STUB_LOG}"
STUB

# --- A made-up server -----------------------------------------------------------------------------------------------------
# Everything the installer, the AI and the route service make, below a test root. build_system DIR [remote]

build_system() {
    local d="$1" release="$1/opt/rentalars/releases/0.9.5-20261018-120000"
    mkdir -p "${d}/etc/rentalars/tls" "${d}/etc/rentalars/address-backup" "${d}/etc/systemd/system/rentalars-ai.service.d" \
        "${d}/etc/systemd/system/timers.target.wants" "${d}/etc/nginx/sites-available" "${d}/etc/nginx/sites-enabled" \
        "${d}/etc/nginx/snippets" "${d}/etc/mysql/mariadb.conf.d" "${d}/etc/mysql/rentalars-encryption" \
        "${d}/etc/letsencrypt/live/rentalars.example.de" "${release}/app/deploy" "${release}/app/rentalars" "${release}/venv" \
        "${d}/opt/rentalars/ai/models" "${d}/opt/rentalars/routes" "${d}/usr/local/bin" "${d}/var/lib/rentalars/media" \
        "${d}/var/lib/rentalars/static" "${d}/var/backups/rentalars" "${d}/var/log/nginx" "${d}/var/log/mysql" \
        "${d}/var/www/rentalars-acme/.well-known" "${d}/run" "${d}/root" "${d}/elsewhere"
    {
        echo "[rentalars]"
        echo "url = https://rentalars.example.de"
        echo "secret_key = not-a-secret"
        echo "[database]"
        echo "name = rentalars"
        echo "user = rentalars"
        echo "password = pw"
        if [[ "${2:-}" == remote ]]; then echo "host = db.example.de"; echo "port = 3306"; fi
    } > "${d}/etc/rentalars/rentalars.conf"
    echo "recovery" > "${d}/etc/rentalars/recovery-key"
    echo "tls" > "${d}/etc/rentalars/tls/certificate.pem"
    echo "ai" > "${d}/etc/rentalars/ai-local.conf"
    echo "__version__ = \"0.9.5\"" > "${release}/app/rentalars/__init__.py"
    cat > "${release}/app/deploy/backup.sh" <<BACKUP
#!/usr/bin/env bash
echo "backup \$*" >> "${d}.log"
echo "the backup" > "${d}/var/backups/rentalars/rentalars-2026-10-18_120000-keep.tar.gz"
echo "/var/backups/rentalars/rentalars-2026-10-18_120000-keep.tar.gz"
BACKUP
    ln -s "${release}/app" "${d}/opt/rentalars/app"
    ln -s "${release}/venv" "${d}/opt/rentalars/venv"
    echo "last" > "${d}/opt/rentalars/last-update"
    printf 'llama.cpp-tools\n' > "${d}/opt/rentalars/ai/installed-packages"
    echo "model" > "${d}/opt/rentalars/ai/models/model.gguf"
    echo "map" > "${d}/opt/rentalars/routes/map.mem"
    printf '#!/bin/sh\nexec /bin/bash /opt/rentalars/app/deploy/rentalars "$@"\n' > "${d}/usr/local/bin/rentalars"
    local unit
    for unit in rentalars.service rentalars-ai.service rentalars-backup.service rentalars-backup.timer \
        rentalars-maintenance.timer rentalars-ai-refresh.timer; do
        echo "[Unit]" > "${d}/etc/systemd/system/${unit}"
    done
    echo "[Service]" > "${d}/etc/systemd/system/rentalars-ai.service.d/override.conf"
    ln -s /etc/systemd/system/rentalars-backup.timer "${d}/etc/systemd/system/timers.target.wants/rentalars-backup.timer"
    ln -s /etc/systemd/system/other.timer "${d}/etc/systemd/system/timers.target.wants/other.timer"
    echo "unrelated" > "${d}/etc/systemd/system/other.service"
    cat > "${d}/etc/nginx/sites-available/rentalars" <<'SITE'
server {
    listen 443 ssl;
    server_name rentalars.example.de;
    ssl_certificate /etc/letsencrypt/live/rentalars.example.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/rentalars.example.de/privkey.pem;
}
SITE
    echo "other site" > "${d}/etc/nginx/sites-available/other"
    ln -s ../sites-available/rentalars "${d}/etc/nginx/sites-enabled/rentalars"
    ln -s ../sites-available/other "${d}/etc/nginx/sites-enabled/other"
    echo "proxy" > "${d}/etc/nginx/snippets/rentalars-proxy.conf"
    echo "realip" > "${d}/etc/nginx/snippets/rentalars-realip.conf"
    echo "cert" > "${d}/etc/letsencrypt/live/rentalars.example.de/fullchain.pem"
    echo "acme" > "${d}/var/www/rentalars-acme/.well-known/token"
    echo "[mysqld]" > "${d}/etc/mysql/mariadb.conf.d/60-rentalars.cnf"
    echo "[mysqld]" > "${d}/etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf"
    echo "[mysqld]" > "${d}/etc/mysql/mariadb.conf.d/50-server.cnf"
    echo "[mariadbd]" > "${d}/etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf"
    echo "key" > "${d}/etc/mysql/rentalars-encryption/keys.enc"
    echo "file" > "${d}/var/lib/rentalars/media/logo.png"
    echo "{}" > "${d}/var/lib/rentalars/backup-status.json"
    echo "old backup" > "${d}/var/backups/rentalars/rentalars-2026-10-17_023000.tar.gz"
    echo "log" > "${d}/var/log/nginx/rentalars.access.log"
    echo "log" > "${d}/var/log/nginx/rentalars.error.log.1"
    echo "other log" > "${d}/var/log/nginx/access.log"
    echo "log" > "${d}/var/log/mysql/rentalars-slow.log"
    echo "lock" > "${d}/run/rentalars-ai-refresh.lock"
    echo "keep me" > "${d}/elsewhere/precious.txt"
}

# A picture of a whole tree: every file, folder and link with its content and target.
snapshot() {
    ( cd "$1" && find . -printf '%p %y %l\n' | sort | md5sum && find . -type f -print0 | sort -z | xargs -0 md5sum | md5sum ) | md5sum
}

# Runs the script against a system: run SYSTEM [ENVIRONMENT…] -- ARGUMENTS… ; sets output, status and log.
# Standard input is empty, as in a script; INPUT gives lines to type, with RENTALARS_UNINSTALL_TEST_INTERACTIVE=1.
INPUT=""
run() {
    local d="$1" environment=()
    shift
    while [[ "$1" != "--" ]]; do environment+=("$1"); shift; done
    shift
    rm -rf "${d}.state"
    mkdir -p "${d}.state"
    : > "${d}.log"
    status=0
    if [[ -n "${INPUT}" ]]; then
        output="$(printf '%b' "${INPUT}" | env "${environment[@]}" RENTALARS_UNINSTALL_TEST_INTERACTIVE=1 \
            RENTALARS_UNINSTALL_TEST_ROOT="${d}" RENTALARS_UNINSTALL_STUBS="${stubs}" RENTALARS_CONFIG="${d}/etc/rentalars/rentalars.conf" \
            STUB_LOG="${d}.log" STUB_STATE="${d}.state" bash "${script}" "$@" 2>&1)" || status=$?
    else
        output="$(env "${environment[@]}" RENTALARS_UNINSTALL_TEST_ROOT="${d}" RENTALARS_UNINSTALL_STUBS="${stubs}" \
            RENTALARS_CONFIG="${d}/etc/rentalars/rentalars.conf" STUB_LOG="${d}.log" STUB_STATE="${d}.state" \
            bash "${script}" "$@" 2>&1 < /dev/null)" || status=$?
    fi
    # shellcheck disable=SC2001  # a pattern with a class, not a plain replacement
    output="$(sed 's/\x1b\[[0-9;]*m//g' <<<"${output}")"
    log="$(cat "${d}.log")"
}
# The commands of the log that change something: everything but the questions the script only asks.
changing() { grep -vE '^(getent|mariadb -e)' <<<"${log}" || true; }
present() { if [[ -e "$1" || -L "$1" ]]; then echo present; else echo gone; fi; }
line_of() { grep -n -F -m1 -- "$2" <<<"$1" | cut -d: -f1; }

fresh() { # fresh NAME [remote] – a new system in the work folder; prints its folder
    local d="${work}/$1"
    rm -rf "${d}"
    mkdir -p "${d}"
    build_system "${d}" "${2:-}"
    echo "${d}"
}

# --- No choice, wrong use ------------------------------------------------------------------------------------------------

echo "== Without a choice nothing happens"
s="$(fresh usage)"
before="$(snapshot "${s}")"
run "${s}" --
expect "no option: status 2" "2" "${status}"
expect_in "  … the usage names --dry-run" "--dry-run" "${output}"
expect_in "  … --keep-data" "--keep-data" "${output}"
expect_in "  … --purge" "--purge" "${output}"
expect_in "  … and says that nothing happens" "Ohne Angabe passiert nichts" "${output}"
expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
expect "  … no command ran" "" "${log}"
run "${s}" RENTALARS_LANG=en --
expect_in "English usage" "Without a choice nothing happens" "${output}"
run "${s}" -- --keep-data --purge
expect "--keep-data with --purge: status 2" "2" "${status}"
expect_in "  … says they exclude each other" "schließen sich aus" "${output}"
run "${s}" -- --frobnicate
expect "unknown option: status 2" "2" "${status}"
run "${s}" -- --keep-data --yes-i-really-want-to-delete-everything
expect "the long option belongs to the purge: status 2" "2" "${status}"
run "${s}" -- --purge --backup-to /root --no-final-backup
expect "--backup-to with --no-final-backup: status 2" "2" "${status}"
run "${s}" -- --backup-to
expect "--backup-to without a folder: status 2" "2" "${status}"
expect "  … nothing changed by all of these" "${before}" "$(snapshot "${s}")"
run "${s}" -- --help
expect "--help: status 0" "0" "${status}"
expect_in "  … describes the three kinds" "--keep-data   the exact opposite of the installation, minus the data" "${output}"

echo "== The test hooks cannot reach a real system"
status=0
out="$(RENTALARS_UNINSTALL_TEST_ROOT="${s}" bash "${script}" --dry-run 2>&1 < /dev/null)" || status=$?
expect "a test root without stand-ins: refused" "1" "${status}"
expect_in "  … and says what is missing" "RENTALARS_UNINSTALL_STUBS" "${out}"
mkdir -p "${work}/incomplete"
cp "${stubs}/systemctl" "${work}/incomplete/"
status=0
out="$(RENTALARS_UNINSTALL_TEST_ROOT="${s}" RENTALARS_UNINSTALL_STUBS="${work}/incomplete" bash "${script}" --dry-run 2>&1 < /dev/null)" || status=$?
expect "  … one stand-in is not enough" "1" "${status}"

# --- --dry-run -----------------------------------------------------------------------------------------------------------------

echo "== --dry-run alone shows --keep-data and changes nothing"
s="$(fresh dry)"
before="$(snapshot "${s}")"
run "${s}" -- --dry-run
dry_alone="${output}"
expect "status 0" "0" "${status}"
expect "nothing changed" "${before}" "$(snapshot "${s}")"
expect_in "says it is a dry run" "Probelauf: nichts wurde verändert." "${output}"
expect_in "names the kind" "--keep-data" "${output}"
expect_in "stops the timers and the services" "anhalten und abschalten: rentalars-ai-refresh.timer rentalars-backup.timer rentalars-maintenance.timer rentalars-ai.service rentalars-backup.service rentalars.service" "${output}"
for item in /etc/systemd/system/rentalars.service /etc/systemd/system/rentalars-ai.service.d /etc/nginx/sites-available/rentalars \
    /etc/nginx/sites-enabled/rentalars /etc/nginx/snippets/rentalars-proxy.conf /etc/nginx/snippets/rentalars-realip.conf /var/www/rentalars-acme /opt/rentalars \
    /usr/local/bin/rentalars /run/rentalars-ai-refresh.lock; do
    expect_in "removes ${item}" "${item}" "${output%%Bleibt erhalten:*}"
done
kept="${output#*Bleibt erhalten:}"
kept="${kept%%Das fasst dieses Skript nie an*}"
for item in /var/lib/rentalars /var/backups/rentalars /etc/rentalars rentalars.conf "Datenbank" "rentalars (MariaDB auf diesem Server)" \
    /etc/mysql/rentalars-encryption /etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf /etc/mysql/mariadb.conf.d/60-rentalars.cnf \
    "/var/log/nginx/rentalars.*" "/etc/letsencrypt/live/rentalars.example.de" "Systemkonto"; do
    expect_in "keeps ${item}" "${item}" "${kept}"
done
expect_not_in "does not drop a database" "DROP DATABASE" "${output}"
expect_not_in "does not delete a certificate" "certbot delete --cert-name rentalars.example.de$" "${output%%Bleibt erhalten:*}"
expect_in "names the packages it never removes" "nginx" "${output}"
expect_in "  … also those of the local AI" "llama.cpp-tools" "${output}"
expect "no command that changes anything ran" "" "$(grep -E '^(systemctl|userdel|groupdel|gpasswd|certbot|nginx)|DROP|backup' <<<"${log}" || true)"
run "${s}" -- --dry-run --keep-data
expect "--dry-run --keep-data: the same plan" "${dry_alone}" "${output}"
run "${s}" -- --keep-data --dry-run
expect "--keep-data --dry-run: the same plan" "${dry_alone}" "${output}"
expect "  … still nothing changed" "${before}" "$(snapshot "${s}")"

echo "== --dry-run --purge shows the purge"
run "${s}" -- --dry-run --purge
removed="${output%%Bleibt erhalten:*}"
expect "status 0" "0" "${status}"
expect "nothing changed" "${before}" "$(snapshot "${s}")"
expect_in "names the purge" "--purge" "${output}"
for item in /var/lib/rentalars /var/backups/rentalars /etc/rentalars "DROP DATABASE auf dem MariaDB dieses Servers" \
    "Datenbankbenutzer rentalars@localhost" /var/log/nginx/rentalars.access.log /var/log/nginx/rentalars.error.log.1 \
    /var/log/mysql/rentalars-slow.log /etc/mysql/mariadb.conf.d/60-rentalars.cnf /etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf \
    "certbot delete --cert-name rentalars.example.de" "rentalars (und Gruppe)"; do
    expect_in "removes ${item}" "${item}" "${removed}"
done
expect_not_in "does not remove other logs" "/var/log/nginx/access.log" "${output}"
expect_not_in "does not remove other sites" "sites-available/other" "${output}"
expect_in "keeps the encryption key" "/etc/mysql/rentalars-encryption" "${output#*Bleibt erhalten:}"
expect_in "explains why" "MariaDB kann seine Dateien ohne sie nicht mehr lesen" "${output}"
expect_in "recommends a last backup and names the option" "--backup-to ORDNER" "${output}"
expect_in "  … and the by-hand way" "sudo rentalars backup --keep" "${output}"
expect_not_in "a dry run asks for nothing" "tippe genau" "${output}"
expect "no command that changes anything ran" "" "$(grep -E '^(systemctl|userdel|groupdel|gpasswd|certbot|nginx)|DROP|backup' <<<"${log}" || true)"

echo "== English"
run "${s}" RENTALARS_LANG=en -- --dry-run --purge
expect_in "headings" "Will be removed:" "${output}"
expect_in "  … what stays" "Stays:" "${output}"

echo "== Not on a server: a different shape of the installation"
s2="$(fresh dry-remote remote)"
run "${s2}" -- --dry-run --purge
expect_in "remote database: its tables, not the database" "alle Tabellen von rentalars auf db.example.de" "${output}"
expect_in "  … database and account stay" "gehören dem Administrator jenes Servers und bleiben" "${output}"
expect_not_in "  … no DROP DATABASE" "DROP DATABASE" "${output}"
expect_not_in "  … MariaDB settings are not touched (the database is elsewhere)" "62-rentalars-memory.cnf" "${output%%Bleibt erhalten:*}"
rm -rf "${s2}"

# --- --keep-data --------------------------------------------------------------------------------------------------------------

echo "== --keep-data without a terminal asks for --yes"
s="$(fresh keep-noyes)"
before="$(snapshot "${s}")"
run "${s}" -- --keep-data
expect "status 1" "1" "${status}"
expect_in "says why" "bitte --yes angeben" "${output}"
expect "nothing changed" "${before}" "$(snapshot "${s}")"
expect "no command that changes anything ran" "" "$(changing)"

echo "== --keep-data --yes"
s="$(fresh keep)"
run "${s}" -- --keep-data --yes
keep_output="${output}"
expect "status 0" "0" "${status}"
for item in /opt/rentalars /etc/systemd/system/rentalars.service /etc/systemd/system/rentalars-backup.timer \
    /etc/systemd/system/rentalars-ai.service /etc/systemd/system/rentalars-ai.service.d /etc/nginx/sites-available/rentalars \
    /etc/nginx/sites-enabled/rentalars /etc/nginx/snippets/rentalars-proxy.conf /etc/nginx/snippets/rentalars-realip.conf /var/www/rentalars-acme /usr/local/bin/rentalars \
    /run/rentalars-ai-refresh.lock /etc/systemd/system/timers.target.wants/rentalars-backup.timer; do
    expect "removed: ${item}" "gone" "$(present "${s}${item}")"
done
for item in /var/lib/rentalars/media/logo.png /var/lib/rentalars/backup-status.json /var/backups/rentalars/rentalars-2026-10-17_023000.tar.gz \
    /etc/rentalars/rentalars.conf /etc/rentalars/recovery-key /etc/rentalars/tls/certificate.pem /etc/rentalars/ai-local.conf \
    /etc/mysql/mariadb.conf.d/60-rentalars.cnf /etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf \
    /etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf /etc/mysql/rentalars-encryption/keys.enc \
    /etc/letsencrypt/live/rentalars.example.de/fullchain.pem /var/log/nginx/rentalars.access.log /var/log/mysql/rentalars-slow.log; do
    expect "kept: ${item}" "present" "$(present "${s}${item}")"
done
for item in /etc/systemd/system/other.service /etc/nginx/sites-available/other /etc/nginx/sites-enabled/other \
    /etc/systemd/system/timers.target.wants/other.timer /etc/mysql/mariadb.conf.d/50-server.cnf /var/log/nginx/access.log \
    /elsewhere/precious.txt; do
    expect "left alone: ${item}" "present" "$(present "${s}${item}")"
done
timer_line="$(line_of "${log}" "systemctl stop rentalars-backup.timer")"
service_line="$(line_of "${log}" "systemctl stop rentalars.service")"
test_line="$(line_of "${log}" "nginx -t")"
reload_line="$(line_of "${log}" "systemctl reload nginx")"
expect "the timers are stopped before the application" "yes" "$([[ -n "${timer_line}" && -n "${service_line}" && "${timer_line}" -lt "${service_line}" ]] && echo yes || echo no)"
expect "the application is stopped last of the units" "systemctl stop rentalars.service" "$(grep -F 'systemctl stop' <<<"${log}" | tail -n 1)"
expect "the units are disabled after all were stopped" "yes" "$([[ "$(line_of "${log}" "systemctl disable rentalars-ai-refresh.timer")" -gt "${service_line}" ]] && echo yes || echo no)"
expect "NGINX is reloaded after its test" "yes" "$([[ -n "${test_line}" && -n "${reload_line}" && "${test_line}" -lt "${reload_line}" ]] && echo yes || echo no)"
expect "systemd reads its units again" "1" "$(grep -c -F 'systemctl daemon-reload' <<<"${log}")"
expect "no database command that changes anything" "" "$(grep -E 'DROP|mariadb <' <<<"${log}" || true)"
expect "no account removed" "" "$(grep -E '^(userdel|groupdel|gpasswd)' <<<"${log}" || true)"
expect "no certificate deleted" "" "$(grep -E '^certbot' <<<"${log}" || true)"
expect "no backup written" "" "$(grep -E '^backup' <<<"${log}" || true)"
expect_in "the summary says the data is still there" "die Daten sind noch da" "${keep_output}"
expect_in "  … names the database" "rentalars (MariaDB auf diesem Server)" "${keep_output#*Zusammenfassung}"
expect_in "  … tells how to set it up again" "sudo ./deploy/install.sh --domain rentalars.example.de" "${keep_output}"
expect_in "  … and to put the configuration aside first" "sudo mv /etc/rentalars /etc/rentalars.behalten" "${keep_output}"
expect_in "  … and to restore" "sudo rentalars restore /var/backups/rentalars/DATEI" "${keep_output}"
expect_in "  … and that a purge comes from the package" "sudo ./deploy/uninstall.sh --purge" "${keep_output}"
expect_in "  … and that the certificate is not renewed any more" "certbot erneuert es nicht mehr" "${keep_output}"
after_keep="$(snapshot "${s}")"

echo "== running it again changes nothing (idempotent)"
run "${s}" -- --keep-data --yes
expect "status 0" "0" "${status}"
expect_in "says there is nothing to do" "nichts zu tun" "${output}"
expect "nothing changed" "${after_keep}" "$(snapshot "${s}")"
expect "no command that changes anything" "" "$(grep -E '^(systemctl|userdel|groupdel|gpasswd|certbot|nginx)|DROP' <<<"${log}" || true)"

echo "== a purge after --keep-data (the program is gone)"
before="$(snapshot "${s}")"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --backup-to /root
expect "a last backup is asked for but impossible: status 1" "1" "${status}"
expect_in "  … says so and names the way out" "--no-final-backup" "${output}"
expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
INPUT="x\n"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything
INPUT=""
expect "status 0" "0" "${status}"
expect_in "it says no last backup is possible" "eine letzte Sicherung ist nicht mehr möglich" "${output}"
for item in /var/lib/rentalars /var/backups/rentalars /etc/rentalars /var/log/nginx/rentalars.access.log /var/log/mysql/rentalars-slow.log; do
    expect "removed: ${item}" "gone" "$(present "${s}${item}")"
done
expect "the encryption key stays" "present" "$(present "${s}/etc/mysql/rentalars-encryption/keys.enc")"
expect "the database was dropped" "1" "$(grep -c 'DROP DATABASE IF EXISTS `rentalars`' <<<"${log}")"

echo "== NGINX that does not accept the result is not reloaded"
s="$(fresh keep-nginx)"
run "${s}" FAKE_NGINX_TEST=1 -- --keep-data --yes
expect "status 1 (a step went wrong)" "1" "${status}"
expect "NGINX tested" "1" "$(grep -c '^nginx -t' <<<"${log}")"
expect "NGINX not reloaded" "0" "$(grep -c 'systemctl reload nginx' <<<"${log}")"
expect_in "a warning with the reason" "nimmt seine Konfiguration ohne die Seite von Rentalars nicht an" "${output}"
expect "the rest was still removed" "gone" "$(present "${s}/opt/rentalars")"
s="$(fresh keep-nginx-off)"
run "${s}" FAKE_NGINX_ACTIVE=3 -- --keep-data --yes
expect "NGINX not running: tested, not reloaded, status 0" "0|0" "${status}|$(grep -c 'systemctl reload nginx' <<<"${log}")"

# --- --purge ---------------------------------------------------------------------------------------------------------------------

echo "== --purge needs an explicit confirmation"
s="$(fresh purge-refused)"
before="$(snapshot "${s}")"
run "${s}" -- --purge
expect "no terminal, no option: status 1" "1" "${status}"
expect_in "it refuses and names the option" "--yes-i-really-want-to-delete-everything" "${output}"
expect "nothing changed" "${before}" "$(snapshot "${s}")"
expect "no command that changes anything ran" "" "$(changing)"
run "${s}" -- --purge --yes
expect "--yes does not confirm a purge" "1" "${status}"
expect "  … nothing changed" "${before}" "$(snapshot "${s}")"

echo "== the confirmation at a terminal"
INPUT="nein\n"
run "${s}" -- --purge --no-final-backup
expect "a wrong word: status 1" "1" "${status}"
expect_in "  … it names the word it wants" "tippe genau: rentalars.example.de" "${output}"
expect_in "  … cancelled" "Abgebrochen. Es wurde nichts verändert." "${output}"
expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
INPUT="y\n"
run "${s}" -- --purge --no-final-backup
expect "y is not enough" "${before}" "$(snapshot "${s}")"
INPUT="RENTALARS.EXAMPLE.DE\n"
run "${s}" -- --purge --no-final-backup
expect "the word in other case is not enough" "${before}" "$(snapshot "${s}")"
INPUT="\n"
run "${s}" -- --purge --no-final-backup
expect "an empty answer is not enough" "${before}" "$(snapshot "${s}")"
INPUT="rentalars.example.de\n"
run "${s}" -- --purge --no-final-backup
expect "the host name: status 0" "0" "${status}"
expect "  … the data folder is gone" "gone" "$(present "${s}/var/lib/rentalars")"
INPUT=""

echo "== what --purge removes and keeps"
s="$(fresh purge)"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
purge_output="${output}"
expect "status 0" "0" "${status}"
for item in /opt/rentalars /etc/systemd/system/rentalars.service /etc/nginx/sites-available/rentalars /usr/local/bin/rentalars \
    /var/lib/rentalars /var/backups/rentalars /etc/rentalars /var/www/rentalars-acme /var/log/nginx/rentalars.access.log \
    /var/log/nginx/rentalars.error.log.1 /var/log/mysql/rentalars-slow.log /etc/mysql/mariadb.conf.d/60-rentalars.cnf \
    /etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf /run/rentalars-ai-refresh.lock; do
    expect "removed: ${item}" "gone" "$(present "${s}${item}")"
done
for item in /etc/mysql/rentalars-encryption/keys.enc /etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf \
    /etc/mysql/mariadb.conf.d/50-server.cnf /etc/nginx/sites-available/other /etc/systemd/system/other.service \
    /var/log/nginx/access.log /elsewhere/precious.txt; do
    expect "kept: ${item}" "present" "$(present "${s}${item}")"
done
expect "only Rentalars' own database is dropped" "mariadb < DROP DATABASE IF EXISTS \`rentalars\`; " "$(grep '^mariadb <.*DROP DATABASE' <<<"${log}")"
expect "only Rentalars' own user is dropped" "mariadb < DROP USER IF EXISTS 'rentalars'@'localhost'; FLUSH PRIVILEGES; " "$(grep '^mariadb <.*DROP USER' <<<"${log}")"
db_line="$(line_of "${log}" "DROP DATABASE")"
unit_line="$(line_of "${log}" "systemctl stop rentalars.service")"
disable_line="$(line_of "${log}" "systemctl disable rentalars.service")"
expect "the application is stopped before the database is dropped" "yes" "$([[ -n "${db_line}" && -n "${unit_line}" && "${unit_line}" -lt "${db_line}" ]] && echo yes || echo no)"
expect "the units are disabled only after the database is dropped" "yes" "$([[ -n "${disable_line}" && "${disable_line}" -gt "${db_line}" ]] && echo yes || echo no)"
expect "the certificate of the site is deleted" "certbot delete --non-interactive --cert-name rentalars.example.de" "$(grep '^certbot' <<<"${log}")"
expect "the account is removed after leaving www-data's group" "gpasswd -d www-data rentalars|userdel rentalars" "$(grep -E '^(gpasswd|userdel)' <<<"${log}" | paste -sd'|')"
expect "no group left to delete" "0" "$(grep -c '^groupdel' <<<"${log}")"
expect_in "the summary says what remains: the encryption key" "/etc/mysql/rentalars-encryption" "${purge_output#*Zusammenfassung}"
expect_in "  … and that packages stay" "Pakete des Betriebssystems werden nie entfernt" "${purge_output}"
expect_in "  … and the default NGINX site" "sites-enabled/default" "${purge_output}"
expect_in "  … and that no last backup was written" "Es wird keine letzte Sicherung geschrieben" "${purge_output}"

echo "== a group that userdel leaves is removed"
s="$(fresh purge-group)"
run "${s}" FAKE_GROUP_STAYS=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "groupdel ran" "1" "$(grep -c '^groupdel rentalars' <<<"${log}")"

echo "== a foreign account named rentalars is not removed"
s="$(fresh purge-foreign-user)"
run "${s}" "FAKE_PASSWD=rentalars:x:1001:1001:A person:/home/rentalars:/bin/bash" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "no userdel" "0" "$(grep -c '^userdel' <<<"${log}")"
expect_in "it says so" "ist kein Systemkonto des Installers" "${output}"

echo "== a shared MariaDB server"
s="$(fresh purge-shared)"
before="$(snapshot "${s}")"
run "${s}" "FAKE_SCHEMAS=rentalars wiki shop" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "status 0" "0" "${status}"
expect "the other databases are not dropped" "mariadb < DROP DATABASE IF EXISTS \`rentalars\`; " "$(grep '^mariadb <.*DROP DATABASE' <<<"${log}")"
expect "  … no other name appears in any statement" "0" "$(grep -E '^mariadb <' <<<"${log}" | grep -cE 'wiki|shop' || true)"
expect "the settings of the whole server stay" "present" "$(present "${s}/etc/mysql/mariadb.conf.d/60-rentalars.cnf")"
expect "  … also the memory settings" "present" "$(present "${s}/etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf")"
expect_in "  … and it names the other databases" "wiki shop" "${output}"
s="$(fresh purge-shared-user)"
run "${s}" "FAKE_GRANTS=GRANT USAGE ON *.* TO \`rentalars\`@\`localhost\`
GRANT ALL PRIVILEGES ON \`rentalars\`.* TO \`rentalars\`@\`localhost\`
GRANT SELECT ON \`wiki\`.* TO \`rentalars\`@\`localhost\`" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "a user with rights on another database is not dropped" "0" "$(grep -c 'DROP USER' <<<"${log}")"
expect "  … the database is" "1" "$(grep -c 'DROP DATABASE' <<<"${log}")"
s="$(fresh purge-nomaria)"
run "${s}" FAKE_MARIADB=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "MariaDB not answering: refused before anything changes" "1" "${status}"
expect_in "  … with the reason" "MariaDB auf diesem Server antwortet nicht" "${output}"
expect "  … nothing removed" "present" "$(present "${s}/var/lib/rentalars")"
expect "  … no unit stopped" "0" "$(grep -c -E 'disable|systemctl stop' <<<"${log}")"

echo "== a database on another server"
s="$(fresh purge-remote remote)"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "status 0" "0" "${status}"
expect "no DROP DATABASE, no DROP USER" "0" "$(grep -cE 'DROP (DATABASE|USER)' <<<"${log}")"
expect "its tables are dropped" "mariadb < SET FOREIGN_KEY_CHECKS = 0; DROP TABLE IF EXISTS \`core_user\`; DROP TABLE IF EXISTS \`core_role\`; DROP VIEW IF EXISTS \`core_view\`; " "$(grep '^mariadb <' <<<"${log}")"
expect "MariaDB settings of this server are not touched" "present" "$(present "${s}/etc/mysql/mariadb.conf.d/60-rentalars.cnf")"
s="$(fresh purge-remote-down remote)"
run "${s}" FAKE_MARIADB=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "a database that does not answer: refused, nothing changed" "1|present" "${status}|$(present "${s}/var/lib/rentalars")"
s="$(fresh purge-remote-fail remote)"
run "${s}" FAKE_MARIADB_WRITE=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "tables that cannot be dropped: stops, keeps the configuration" "1|present|present" "${status}|$(present "${s}/etc/rentalars/rentalars.conf")|$(present "${s}/var/lib/rentalars")"
expect_in "  … and says how to start Rentalars again" "sudo systemctl start rentalars" "${output}"

echo "== a failing drop of the local database stops the run"
s="$(fresh purge-dropfail)"
run "${s}" FAKE_MARIADB_WRITE=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "status 1, data folder and configuration still there" "1|present|present|present" "${status}|$(present "${s}/var/lib/rentalars")|$(present "${s}/etc/rentalars/rentalars.conf")|$(present "${s}/var/backups/rentalars")"

echo "== certificates"
s="$(fresh purge-cert-shared)"
echo "ssl_certificate /etc/letsencrypt/live/rentalars.example.de/fullchain.pem;" > "${s}/etc/nginx/sites-available/other"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "a certificate that another site uses is not deleted" "0" "$(grep -c '^certbot' <<<"${log}")"
expect_in "  … and it says so" "bleibt: " "${output}"
s="$(fresh purge-cert-own)"
sed -i 's|/etc/letsencrypt/live/rentalars.example.de/|/etc/rentalars/tls/|; s|fullchain.pem|certificate.pem|' "${s}/etc/nginx/sites-available/rentalars"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "an own certificate is no Let's Encrypt certificate: certbot not called" "0" "$(grep -c '^certbot' <<<"${log}")"
expect "  … it goes with /etc/rentalars" "gone" "$(present "${s}/etc/rentalars/tls/certificate.pem")"

echo "== the last backup"
s="$(fresh purge-backup)"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --backup-to /root
copy="${s}/root/rentalars-2026-10-18_120000-keep.tar.gz"
expect "status 0" "0" "${status}"
expect "the backup was written with --keep" "backup --keep" "$(grep '^backup' <<<"${log}")"
expect "a copy lies outside what is removed" "present" "$(present "${copy}")"
expect "  … with the content of the backup" "the backup" "$(cat "${copy}")"
expect "  … readable by root only" "600" "$(stat -c %a "${copy}")"
expect_in "the path is named" "/root/rentalars-2026-10-18_120000-keep.tar.gz" "${output}"
expect "the backup folder is gone" "gone" "$(present "${s}/var/backups/rentalars")"
backup_line="$(line_of "${log}" "backup --keep")"
unit_line="$(line_of "${log}" "systemctl stop")"
expect "the backup is written before anything is stopped" "yes" "$([[ -n "${backup_line}" && -n "${unit_line}" && "${backup_line}" -lt "${unit_line}" ]] && echo yes || echo no)"
s="$(fresh purge-backup-inside)"
before="$(snapshot "${s}")"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --backup-to /var/lib/rentalars/media
expect "a folder that would be removed is refused: status 1" "1" "${status}"
expect_in "  … with the reason" "liegt in" "${output}"
expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --backup-to /nonexistent
expect "a folder that does not exist: status 1" "1" "${status}"
expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
INPUT="j\nrentalars.example.de\n"
run "${s}" -- --purge
expect "at a terminal it offers a last backup (yes, then the word): status 0" "0" "${status}"
expect_in "  … asks" "eine letzte Sicherung schreiben und nach /root kopieren" "${output}"
expect "  … and made it" "present" "$(present "${s}/root/rentalars-2026-10-18_120000-keep.tar.gz")"
s="$(fresh purge-backup-no)"
INPUT="n\nrentalars.example.de\n"
run "${s}" -- --purge
expect "  … declined: no backup written" "0" "$(grep -c '^backup' <<<"${log}")"
INPUT=""
s="$(fresh purge-backup-none)"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "--no-final-backup writes none" "0" "$(grep -c '^backup' <<<"${log}")"
s="$(fresh purge-encrypted)"
printf '[backup]\nencrypt = true\n' >> "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect_in "encrypted backups: the plan warns that the recovery key goes too" "Der Wiederherstellungsschlüssel liegt in /etc/rentalars/recovery-key und wird mit gelöscht" "${output}"

# --- Safety --------------------------------------------------------------------------------------------------------------------------

echo "== configured elsewhere"
s="$(fresh purge-moved)"
sed -i 's|^\[rentalars\]|[rentalars]\ndata_dir = /elsewhere|' "${s}/etc/rentalars/rentalars.conf"
printf '[backup]\ndirectory = /elsewhere/backups\n' >> "${s}/etc/rentalars/rentalars.conf"
mkdir -p "${s}/elsewhere/backups"
echo "mine" > "${s}/elsewhere/backups/b.tar.gz"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "a data folder the configuration moved is not removed" "present" "$(present "${s}/elsewhere/precious.txt")"
expect "  … nor a moved backup folder" "present" "$(present "${s}/elsewhere/backups/b.tar.gz")"
expect "  … the installer's own folders are" "gone" "$(present "${s}/var/lib/rentalars")"
expect_in "  … and it names what stays" "Das hat der Installer nicht angelegt" "${output}"

echo "== links are never followed"
s="$(fresh purge-links)"
rm -rf "${s}/var/lib/rentalars"
ln -s "${s}/elsewhere" "${s}/var/lib/rentalars"
ln -s "${s}/elsewhere/precious.txt" "${s}/var/backups/rentalars/link-to-precious"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "the data folder was a link: the link is gone" "gone" "$(present "${s}/var/lib/rentalars")"
expect "  … its target is untouched" "keep me" "$(cat "${s}/elsewhere/precious.txt")"
expect "a link inside a removed folder is removed, not followed" "gone" "$(present "${s}/var/backups/rentalars")"
expect_in "the link is named" "ist ein Link" "${output}"

echo "== values that do not look right stop everything"
s="$(fresh purge-badname)"
sed -i 's|^name = rentalars|name = mysql|' "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect "the system database 'mysql' as the name: status 1" "1" "${status}"
expect_in "  … nothing changed" "Es wurde nichts verändert" "${output}"
sed -i 's|^name = mysql|name = a;DROP DATABASE mysql|' "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect "a name with SQL in it: status 1" "1" "${status}"
sed -i 's|^name = .*|name = rentalars|; s|^user = rentalars|user = root|' "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect "the user root: status 1" "1" "${status}"
sed -i 's|^user = root|user = rentalars|; s|^\[rentalars\]|[rentalars]\ndata_dir = /|' "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect "a data folder '/': status 1" "1" "${status}"
expect_in "  … and nothing is touched" "Es wurde nichts verändert" "${output}"
sed -i '/^data_dir = \/$/d; s|^\[rentalars\]|[rentalars]\ndata_dir = /var/lib/../../etc|' "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect "a data folder with '..': status 1" "1" "${status}"
sed -i '/^data_dir = /d' "${s}/etc/rentalars/rentalars.conf"
printf '[backup]\ndirectory = relative/path\n' >> "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect "a relative backup folder: status 1" "1" "${status}"
expect "  … in none of these cases did anything change" "present||present" "$(present "${s}/var/lib/rentalars")|$(changing)|$(present "${s}/opt/rentalars")"

echo "== no configuration: the database is not guessed"
s="$(fresh purge-noconfig)"
rm -f "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "status 0" "0" "${status}"
expect "no database statement at all" "0" "$(grep -c 'DROP' <<<"${log}")"
expect_in "it says the database is unknown" "Welche Datenbank zu Rentalars gehört, ist unbekannt" "${output}"
expect "the rest is removed" "gone" "$(present "${s}/var/lib/rentalars")"

echo "== nothing installed"
s="${work}/empty"
mkdir -p "${s}"
run "${s}" FAKE_NO_USER=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "an empty server: status 0" "0" "${status}"
expect_in "  … nothing to do" "nichts zu tun" "${output}"

echo "== an installation that is not in the usual state: a link that does not belong to Rentalars"
s="$(fresh keep-foreign-cli)"
printf '#!/bin/sh\necho another program\n' > "${s}/usr/local/bin/rentalars"
run "${s}" -- --keep-data --yes
expect "a command 'rentalars' that is not ours stays" "present" "$(present "${s}/usr/local/bin/rentalars")"
expect_in "  … and it says so" "gehört nicht zu Rentalars" "${output}"

# --- Findings of the independent review (uninstall; NFA-078) -----------------------------------------------------------------------

echo "== a folder that stays must not lie in a path that is removed (either kind, also the dry run)"
for args in "--keep-data --yes" "--purge --yes-i-really-want-to-delete-everything --no-final-backup" "--dry-run" "--dry-run --purge"; do
    s="$(fresh inside-backup)"
    mkdir -p "${s}/opt/rentalars/backups"
    echo "mine" > "${s}/opt/rentalars/backups/b.tar.gz"
    printf '[backup]\ndirectory = /opt/rentalars/backups\n' >> "${s}/etc/rentalars/rentalars.conf"
    before="$(snapshot "${s}")"
    # shellcheck disable=SC2086  # the arguments are meant to split
    run "${s}" -- ${args}
    expect "backup folder in /opt/rentalars (${args}): status 1" "1" "${status}"
    expect_in "  … it says the folder lies in a removed path" "liegt in /opt/rentalars" "${output}"
    expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
    expect "  … no command that changes anything" "" "$(changing)"
done
s="$(fresh inside-data)"
mkdir -p "${s}/opt/rentalars/data"
sed -i 's|^\[rentalars\]|[rentalars]\ndata_dir = /opt/rentalars/data|' "${s}/etc/rentalars/rentalars.conf"
before="$(snapshot "${s}")"
run "${s}" -- --keep-data --yes
expect "a data folder in /opt/rentalars: status 1, nothing changed" "1|${before}" "${status}|$(snapshot "${s}")"
s="$(fresh inside-link)"
mkdir -p "${s}/opt/rentalars/backups"
ln -s "${s}/opt/rentalars/backups" "${s}/elsewhere/linked"
printf '[backup]\ndirectory = /elsewhere/linked\n' >> "${s}/etc/rentalars/rentalars.conf"
before="$(snapshot "${s}")"
run "${s}" -- --keep-data --yes
expect "a folder that is a link into /opt/rentalars: status 1, nothing changed" "1|${before}" "${status}|$(snapshot "${s}")"
s="$(fresh inside-default)"
mkdir -p "${s}/var/lib/rentalars/backups"
printf '[backup]\ndirectory = /var/lib/rentalars/backups\n' >> "${s}/etc/rentalars/rentalars.conf"
before="$(snapshot "${s}")"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "a purge: a configured backup folder inside the data folder that goes: status 1" "1|${before}" "${status}|$(snapshot "${s}")"
expect_in "  … names the data folder" "liegt in /var/lib/rentalars" "${output}"
run "${s}" -- --keep-data --yes
expect "the same folder with --keep-data is fine (nothing of it is removed)" "0|present" "${status}|$(present "${s}/var/lib/rentalars/backups")"

echo "== the notes about the backups follow what is really removed"
s="$(fresh notes-default)"
run "${s}" -- --dry-run --purge
expect_in "the installer's backup folder: deleted as well" "Die Sicherungen unter /var/backups/rentalars werden mit gelöscht;" "${output}"
run "${s}" -- --dry-run --purge --no-final-backup
expect_in "  … also without a last backup" "die Sicherungen unter /var/backups/rentalars werden mit gelöscht." "${output}"
s="$(fresh notes-moved)"
mkdir -p "${s}/elsewhere/backups"
printf '[backup]\ndirectory = /elsewhere/backups\n' >> "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --dry-run --purge
expect_in "a backup folder the configuration moved: it stays" "Die Sicherungen unter /elsewhere/backups bleiben unberührt;" "${output}"
expect_not_in "  … and is not said to be deleted" "/elsewhere/backups werden mit gelöscht" "${output}"
run "${s}" -- --dry-run --purge --no-final-backup
expect_in "  … also without a last backup" "die Sicherungen unter /elsewhere/backups bleiben unberührt." "${output}"
s="$(fresh notes-after-keep)"
rm -rf "${s}/opt/rentalars"
printf '[backup]\ndirectory = /elsewhere/backups\n' >> "${s}/etc/rentalars/rentalars.conf"
mkdir -p "${s}/elsewhere/backups"
INPUT="x\n"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything
INPUT=""
expect_in "no program any more: the warning does not say the moved backups are deleted" "unter /elsewhere/backups bleiben unberührt." "${output}"
expect "  … and they are still there" "present" "$(present "${s}/elsewhere/backups")"

echo "== a failed database step leaves the units enabled, and says so"
s="$(fresh purge-dropfail-state)"
run "${s}" FAKE_MARIADB_WRITE=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "local DROP fails: the units were stopped" "yes" "$([[ "$(grep -c '^systemctl stop' <<<"${log}")" -ge 6 ]] && echo yes || echo no)"
expect "  … and none was disabled" "0" "$(grep -c '^systemctl disable' <<<"${log}")"
expect_in "  … the message says what state is left" "angehalten, aber noch eingeschaltet" "${output}"
expect_in "  … and what to run" "sudo systemctl start rentalars.service" "${output}"
expect_in "  … and the timers come last" "rentalars-backup.timer rentalars-ai-refresh.timer" "${output}"
s="$(fresh purge-remote-partial remote)"
run "${s}" FAKE_MARIADB_WRITE=1 -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "remote tables fail: no unit was disabled" "0" "$(grep -c '^systemctl disable' <<<"${log}")"
expect_in "  … it says the database may be incomplete" "unvollständig" "${output}"
expect_in "  … names the existing backups" "die vorhandenen Sicherungen unter /var/backups/rentalars" "${output}"
expect_not_in "  … and does not claim that nothing was changed" "sonst ist nichts verändert" "${output}"
run "${s}" FAKE_MARIADB_WRITE=1 -- --purge --yes-i-really-want-to-delete-everything --backup-to /root
expect_in "  … with a last backup it names that one" "die letzte Sicherung /root/rentalars-2026-10-18_120000-keep.tar.gz" "${output}"
expect "  … configuration and data are untouched" "present|present" "$(present "${s}/etc/rentalars/rentalars.conf")|$(present "${s}/var/lib/rentalars")"
s="$(fresh purge-remote-down2 remote)"
run "${s}" FAKE_MARIADB=1 -- --keep-data --yes
expect "remote database: --keep-data never touches it, whatever it answers" "0" "${status}"

echo "== signals in the destructive phase"
# run_signal SYSTEM SIGNAL: starts a purge whose DROP statement takes two seconds, sends the signal meanwhile.
run_signal() {
    local d="$1" signal="$2" pid waited=0
    rm -rf "${d}.state"
    mkdir -p "${d}.state"
    : > "${d}.log"
    env FAKE_MARIADB_SLOW=2 RENTALARS_UNINSTALL_TEST_ROOT="${d}" RENTALARS_UNINSTALL_STUBS="${stubs}" \
        RENTALARS_CONFIG="${d}/etc/rentalars/rentalars.conf" STUB_LOG="${d}.log" STUB_STATE="${d}.state" \
        bash "${script}" --purge --yes-i-really-want-to-delete-everything --no-final-backup > "${d}.out" 2>&1 < /dev/null &
    pid=$!
    while [[ ! -e "${d}.state/in-statement" && "${waited}" -lt 100 ]]; do sleep 0.1; waited=$((waited + 1)); done
    kill "-${signal}" "${pid}"
    status=0
    wait "${pid}" || status=$?
    output="$(sed 's/\x1b\[[0-9;]*m//g' "${d}.out")"
    log="$(cat "${d}.log")"
}
s="$(fresh signal-hup)"
run_signal "${s}" HUP
expect "SIGHUP during DROP DATABASE: the run goes on to the end, status 0" "0" "${status}"
expect "  … the database was dropped" "1" "$(grep -c 'DROP DATABASE' <<<"${log}")"
expect "  … and everything removed" "gone|gone" "$(present "${s}/var/lib/rentalars")|$(present "${s}/etc/rentalars")"
s="$(fresh signal-term)"
run_signal "${s}" TERM
expect "SIGTERM during DROP DATABASE: status 1" "1" "${status}"
expect_in "  … with the text that says to start the command again" "Abgebrochen mitten in der Entfernung" "${output}"
expect_in "  … and to start it again" "starte den Befehl erneut" "${output}"
expect "  … nothing further was removed" "present|present" "$(present "${s}/var/lib/rentalars")|$(present "${s}/etc/rentalars/rentalars.conf")"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "  … and running it again finishes the job" "0|gone|gone" "${status}|$(present "${s}/var/lib/rentalars")|$(present "${s}/etc/rentalars")"

echo "== a link to a folder is removed, its target stays – and the summary does not claim otherwise"
s="$(fresh purge-link-summary)"
rm -rf "${s}/var/lib/rentalars"
ln -s "${s}/elsewhere" "${s}/var/lib/rentalars"
run "${s}" -- --dry-run --purge
expect_in "the plan names the target" "/var/lib/rentalars ist ein Link auf ${s}/elsewhere" "${output}"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
summary="${output#*Zusammenfassung}"
expect "status 0" "0" "${status}"
expect_in "the summary says not all data is gone" "NICHT alle Daten sind weg" "${summary}"
expect_in "  … and names the target" "/var/lib/rentalars ist ein Link auf ${s}/elsewhere" "${summary}"
expect_not_in "  … and does not say it is removed with its data" "entfernt, mit seinen Daten" "${summary}"
expect "  … the target is untouched" "keep me" "$(cat "${s}/elsewhere/precious.txt")"
s="$(fresh purge-link-backups)"
mkdir -p "${s}/elsewhere/saved"
echo "b" > "${s}/elsewhere/saved/b.tar.gz"
rm -rf "${s}/var/backups/rentalars"
ln -s "${s}/elsewhere/saved" "${s}/var/backups/rentalars"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect_in "a linked backup folder: named in the summary" "/var/backups/rentalars ist ein Link auf ${s}/elsewhere/saved" "${output#*Zusammenfassung}"
expect "  … its content is untouched" "b" "$(cat "${s}/elsewhere/saved/b.tar.gz")"
s="$(fresh keep-link-summary)"
rm -rf "${s}/var/lib/rentalars"
run "${s}" -- --keep-data --yes
expect_not_in "--keep-data: nothing about links when nothing is removed through one" "ist ein Link auf" "${output}"

echo "== a configuration that cannot be read"
for breakage in duplicate header; do
    s="$(fresh broken-${breakage})"
    if [[ "${breakage}" == duplicate ]]; then
        sed -i 's|^name = rentalars|name = rentalars\nname = rentalars|' "${s}/etc/rentalars/rentalars.conf"
    else
        { echo "orphan = 1"; cat "${s}/etc/rentalars/rentalars.conf"; } > "${s}/conf.new"
        mv "${s}/conf.new" "${s}/etc/rentalars/rentalars.conf"
    fi
    before="$(snapshot "${s}")"
    run "${s}" -- --dry-run
    expect "${breakage}: --dry-run goes on with the defaults, status 0" "0" "${status}"
    expect_in "  … with a warning" "lässt sich nicht lesen" "${output}"
    expect_not_in "  … no traceback" "Traceback" "${output}"
    expect_not_in "  … no shell error" "unbound variable" "${output}"
    expect_in "  … the data folders of the installer are kept" "/var/lib/rentalars" "${output#*Bleibt erhalten:}"
    expect_in "  … the database is not touched" "Die Datenbank wird nicht angefasst" "${output}"
    expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
    for args in "--dry-run --purge" "--purge --yes-i-really-want-to-delete-everything --no-final-backup"; do
        # shellcheck disable=SC2086  # the arguments are meant to split
        run "${s}" -- ${args}
        expect "${breakage}: ${args} refuses, status 1" "1" "${status}"
        expect_in "  … with a readable reason" "lässt sich nicht lesen" "${output}"
        expect_not_in "  … no traceback or shell error" "Traceback" "${output}"
        expect_not_in "  … no shell error" "unbound variable" "${output}"
        expect "  … nothing changed" "${before}" "$(snapshot "${s}")"
    done
    run "${s}" -- --keep-data --yes
    expect "${breakage}: --keep-data removes the application, status 0" "0|gone" "${status}|$(present "${s}/opt/rentalars")"
    expect "  … and keeps data, configuration and the database" "present|present|0" "$(present "${s}/var/lib/rentalars")|$(present "${s}/etc/rentalars/rentalars.conf")|$(grep -c 'DROP' <<<"${log}")"
done

echo "== units that do not stop"
s="$(fresh purge-stuck)"
before="$(snapshot "${s}")"
run "${s}" FAKE_STUCK_UNITS=rentalars-ai.service -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "--purge: a unit still active after stop: status 1" "1" "${status}"
expect_in "  … names it" "laufen noch: rentalars-ai.service" "${output}"
expect "  … the database was not touched" "0" "$(grep -c 'DROP' <<<"${log}")"
expect "  … nothing was removed" "present|present|present" "$(present "${s}/var/lib/rentalars")|$(present "${s}/etc/rentalars")|$(present "${s}/opt/rentalars")"
expect "  … nothing was disabled" "0" "$(grep -c '^systemctl disable' <<<"${log}")"
expect "  … it was checked after stopping" "yes" "$([[ "$(line_of "${log}" "systemctl is-active rentalars-ai.service")" -ge 1 ]] && echo yes || echo no)"
s="$(fresh keep-stuck)"
run "${s}" FAKE_STUCK_UNITS=rentalars-ai.service -- --keep-data --yes
expect "--keep-data: reported as a problem, status 1" "1" "${status}"
expect_in "  … names the unit and how to stop it" "sudo systemctl stop rentalars-ai.service" "${output}"
expect "  … the rest is removed" "gone|present" "$(present "${s}/opt/rentalars")|$(present "${s}/var/lib/rentalars")"

echo "== without a terminal a purge must say what happens to the last backup"
s="$(fresh purge-nobackup-decision)"
before="$(snapshot "${s}")"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything
expect "neither --backup-to nor --no-final-backup: status 2" "2" "${status}"
expect_in "  … names --backup-to" "--backup-to ORDNER" "${output}"
expect_in "  … and --no-final-backup" "--no-final-backup" "${output}"
expect "  … nothing changed, no command ran" "${before}|" "$(snapshot "${s}")|$(changing)"
run "${s}" -- --dry-run --purge --yes-i-really-want-to-delete-everything
expect "a dry run is not refused" "0" "${status}"

echo "== slow log and MariaDB settings"
s="$(fresh purge-slowlog)"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "the settings are removed with the slow log" "gone|gone" "$(present "${s}/etc/mysql/mariadb.conf.d/60-rentalars.cnf")|$(present "${s}/var/log/mysql/rentalars-slow.log")"
expect_in "  … and the operator is told that MariaDB applies it after a restart" "sudo systemctl restart mariadb" "${output}"
s="$(fresh purge-slowlog-shared)"
run "${s}" "FAKE_SCHEMAS=rentalars wiki" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "settings that stay keep their slow log" "present|present" "$(present "${s}/etc/mysql/mariadb.conf.d/60-rentalars.cnf")|$(present "${s}/var/log/mysql/rentalars-slow.log")"
expect_in "  … and it is listed as staying" "/var/log/mysql/rentalars-slow.log*" "${output#*Geblieben ist:}"
expect_not_in "  … no restart is needed, nothing was removed" "sudo systemctl restart mariadb" "${output}"
s="$(fresh purge-slowlog-remote remote)"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "a database elsewhere: the settings and the slow log stay" "present|present" "$(present "${s}/etc/mysql/mariadb.conf.d/60-rentalars.cnf")|$(present "${s}/var/log/mysql/rentalars-slow.log")"

echo "== a port other than the default makes a database remote"
for variant in "127.0.0.1|3307|remote" "127.0.0.1|3306|local" "127.0.0.1||local" "localhost||local" "localhost|3307|remote" "::1|3307|remote"; do
    IFS='|' read -r host port expected <<<"${variant}"
    s="$(fresh port-check)"
    sed -i "s|^password = pw|password = pw\\nhost = ${host}${port:+\\nport = ${port}}|" "${s}/etc/rentalars/rentalars.conf"
    run "${s}" -- --dry-run --purge
    if [[ "${expected}" == remote ]]; then
        expect_in "host ${host} port ${port:-none}: only the tables" "alle Tabellen von rentalars auf ${host}${port:+:${port}}" "${output}"
        expect_not_in "  … no DROP DATABASE" "DROP DATABASE" "${output}"
        expect_not_in "  … MariaDB settings of this server are not touched" "62-rentalars-memory.cnf" "${output%%Bleibt erhalten:*}"
    else
        expect_in "host ${host} port ${port:-none}: the MariaDB of this server" "DROP DATABASE auf dem MariaDB dieses Servers" "${output}"
    fi
done
s="$(fresh port-tunnel)"
sed -i 's|^password = pw|password = pw\nhost = 127.0.0.1\nport = 3307|' "${s}/etc/rentalars/rentalars.conf"
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --no-final-backup
expect "a tunnel to another server in a real run: tables only, no DROP DATABASE" "0|0" "${status}|$(grep -cE 'DROP (DATABASE|USER)' <<<"${log}")"
expect "  … the tables were dropped" "1" "$(grep -c 'DROP TABLE IF EXISTS `core_user`' <<<"${log}")"

echo "== a relative --backup-to is named with its absolute path"
s="$(fresh backup-relative)"
mkdir -p "${s}/root/rel"
pushd "${s}/root" > /dev/null
run "${s}" -- --purge --yes-i-really-want-to-delete-everything --backup-to rel
popd > /dev/null
expect "status 0" "0" "${status}"
expect_in "the plan names the absolute folder" "kopiert sie nach /root/rel." "${output}"
expect_in "the result names the absolute path" "/root/rel/rentalars-2026-10-18_120000-keep.tar.gz" "${output}"
expect_not_in "no relative path is printed" " rel/rentalars-2026" "${output}"
expect "the copy is there" "present" "$(present "${s}/root/rel/rentalars-2026-10-18_120000-keep.tar.gz")"

# --- The places agree with the installer -------------------------------------------------------------------------------------------------------

echo "== uninstall.sh and the installer name the same places"
matches() { # matches TEXT PATTERN – a glob pattern, as the uninstaller uses it
    # shellcheck disable=SC2254  # the pattern is meant to be one
    case "$1" in $2) return 0 ;; esac
    return 1
}
drift="the log patterns do not match"
# shellcheck source=deploy/lib.sh
if ( source "${deploy}/lib.sh"
     matches /var/log/nginx/rentalars.access.log "${NGINX_LOG_PATTERN}" \
         && matches /var/log/nginx/rentalars.error.log.1 "${NGINX_LOG_PATTERN}" \
         && matches /var/log/mysql/rentalars-slow.log.1 "${MARIADB_SLOW_LOG_PATTERN}" ); then drift="ok"; fi
expect "the log patterns match what is written" "ok" "${drift}"
expect "NGINX's template writes its logs where the pattern says" "ok" \
    "$(grep -E '^\s*(access_log|error_log)' "${deploy}/nginx/rentalars.conf" | grep -c '/var/log/nginx/rentalars\.' | grep -qx 2 && echo ok || echo no)"
expect "MariaDB's settings write the slow log where the pattern says" "ok" \
    "$(grep -q '^slow_query_log_file *= /var/log/mysql/rentalars-slow.log$' "${deploy}/mariadb/60-rentalars.cnf" && echo ok || echo no)"
expect "no script spells the default folders out any more" "" \
    "$(grep -nE 'config_get (rentalars data_dir|backup directory) [^"]' "${deploy}"/*.sh "${deploy}/rentalars" | grep -v '^[^:]*:[0-9]*:#' || true)"
expect "the installer makes the folders from the constants" "ok" \
    "$(grep -q '^data_dir="${DEFAULT_DATA_DIR}"$' "${deploy}/install.sh" && grep -q 'install -d -m 700 -o root -g root "${DEFAULT_BACKUP_DIR}"' "${deploy}/install.sh" && echo ok || echo no)"
expect "every unit of the package is one the uninstaller finds" "" \
    "$(for unit in "${deploy}"/systemd/*; do basename "${unit}" | grep -vE '^rentalars.*\.(service|timer)$' || true; done)"
unused_places=""
for name in RENTALARS_HOME CONFIG_DIR DEFAULT_DATA_DIR DEFAULT_BACKUP_DIR NGINX_SITE NGINX_SITE_LINK NGINX_PROXY_SNIPPET ACME_ROOT \
    MARIADB_SETTINGS MARIADB_MEMORY_SETTINGS MARIADB_ENCRYPTION_SETTINGS MARIADB_KEY_DIR CLI_LINK SYSTEMD_UNIT_DIR SERVICE_USER \
    LETSENCRYPT_LIVE_DIR NGINX_LOG_PATTERN MARIADB_SLOW_LOG_PATTERN AI_DIR ROUTE_DIR INSTALLED_PACKAGES_NAME; do
    grep -q "\${${name}}" "${script}" || unused_places+="${name} "
done
expect "the uninstaller uses every place of lib.sh" "" "${unused_places}"
expect "ai.sh and route.sh take their folders from lib.sh" "ok" \
    "$(grep -q '^readonly AI_HOME="${AI_TEST_ROOT}${AI_DIR}"$' "${deploy}/ai.sh" && grep -q '^readonly ROUTE_HOME="${ROUTE_TEST_ROOT}${ROUTE_DIR}"$' "${deploy}/route.sh" && echo ok || echo no)"
expect "the installer creates what the uninstaller removes: the service user's home is the data folder" "ok" \
    "$(grep -q 'useradd --system --home-dir "${data_dir}"' "${deploy}/install.sh" && echo ok || echo no)"

echo
echo "${cases} cases, ${failures} failed."
[[ "${failures}" -eq 0 ]]
