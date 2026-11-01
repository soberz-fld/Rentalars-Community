#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – write the NGINX site anew from the template of the installed version.
#
#   sudo rentalars nginx-site            show what changes, ask, write, check, reload
#   sudo rentalars nginx-site --show     only show what would change
#   sudo rentalars nginx-site --yes      do not ask
#
# An update keeps the NGINX site as it is and only adapts the form of HTTP/2
# to the installed NGINX: an administrator may have changed it, and a working
# web server is never traded for a tidy one. New settings of the template
# therefore do not arrive by themselves; the self-check names the missing ones
# (the blocks that refuse requests for other names, NFA-049).
#
# This command takes the template of the installed version, fills in the host
# name of the configuration file, the certificate the site uses now and the
# data folder – the same as the installation does – and shows the difference.
# Changes made by hand to the site are overwritten; the old file is kept in
# /etc/rentalars/ and named in the output. NGINX is only reloaded if it
# accepts the new file; otherwise the old one is put back.
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

require_root
[[ -f "${CONFIG_FILE}" ]] || fail "$(t "${CONFIG_FILE} fehlt. Ist Rentalars installiert?" "${CONFIG_FILE} is missing. Is Rentalars installed?")"
[[ -f "${NGINX_SITE}" ]] || fail "$(t "${NGINX_SITE} fehlt. Ist Rentalars mit NGINX installiert?" "${NGINX_SITE} is missing. Is Rentalars installed with NGINX?")"

show_only=false assume_yes=false
for argument in "$@"; do
    case "${argument}" in
        --show) show_only=true ;;
        --yes) assume_yes=true ;;
        -h|--help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "$(t "Unbekannte Angabe: ${argument} (sudo rentalars nginx-site --help)" "Unknown argument: ${argument} (sudo rentalars nginx-site --help)")" ;;
    esac
done

domain="$(python3 -c 'import sys, urllib.parse; print(urllib.parse.urlparse(sys.argv[1]).hostname or "")' \
    "$(config_get rentalars url "")")"
[[ -n "${domain}" ]] || fail "$(t "In ${CONFIG_FILE} steht unter [rentalars] keine Adresse (url)." "${CONFIG_FILE} gives no address (url) under [rentalars].")"
data_dir="$(config_get rentalars data_dir "${DEFAULT_DATA_DIR}")"
# The certificate the site uses now: the first server with one is Rentalars' own.
certificate="$(sed -n -E 's/^[[:space:]]*ssl_certificate[[:space:]]+([^;]+);.*/\1/p' "${NGINX_SITE}" | head -n 1)"
private_key="$(sed -n -E 's/^[[:space:]]*ssl_certificate_key[[:space:]]+([^;]+);.*/\1/p' "${NGINX_SITE}" | head -n 1)"
[[ -n "${certificate}" && -n "${private_key}" ]] \
    || fail "$(t "In ${NGINX_SITE} steht kein Zertifikat (ssl_certificate, ssl_certificate_key). Ohne HTTPS lässt sich die Vorlage nicht übernehmen." "${NGINX_SITE} names no certificate (ssl_certificate, ssl_certificate_key). Without HTTPS the template cannot be taken over.")"
[[ -f "${certificate}" && -f "${private_key}" ]] \
    || fail "$(t "Das Zertifikat ${certificate} oder sein Schlüssel ${private_key} fehlt." "The certificate ${certificate} or its key ${private_key} is missing.")"

work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
render_nginx_site "${APP_DIR}/deploy/nginx/rentalars.conf" "${work}/site" \
    "${domain}" "${certificate}" "${private_key}" "${data_dir}"

say "$(t "NGINX-Konfiguration aus der Vorlage von Rentalars" "NGINX configuration from the template of Rentalars") $(version_of "${APP_DIR}")"
note "Name:        ${domain}"
note "$(t "Zertifikat:  " "Certificate: ")${certificate}"
note "$(t "Schlüssel:   " "Key:         ")${private_key}"
# The file of the addresses that may name the address of a visitor (trusted_proxies) belongs to the site (S8):
# a change of the setting is a change here as well, also when the site itself matches the template.
write_realip_snippet "${work}/realip" "$(config_get rentalars trusted_proxies "")"
site_same=false
realip_same=false
cmp -s "${work}/site" "${NGINX_SITE}" && site_same=true
cmp -s "${work}/realip" "${NGINX_REALIP_SNIPPET}" 2> /dev/null && realip_same=true
if ${site_same} && ${realip_same}; then
    note ""
    note "$(t "${NGINX_SITE} entspricht schon der Vorlage. Nichts zu tun." "${NGINX_SITE} matches the template already. Nothing to do.")"
    exit 0
fi
note ""
note "$(t "Was sich ändert (- bisher, + neu):" "What changes (- before, + new):")"
${site_same} || { diff -u --label "$(t bisher before)" --label "$(t neu new)" "${NGINX_SITE}" "${work}/site" | sed 's/^/    /' || true; }
${realip_same} || {
    note "$(t "Vorgeschaltete Server (trusted_proxies), ${NGINX_REALIP_SNIPPET}:" "Servers in front (trusted_proxies), ${NGINX_REALIP_SNIPPET}:")"
    diff -u --label "$(t bisher before)" --label "$(t neu new)" "${NGINX_REALIP_SNIPPET}" "${work}/realip" 2> /dev/null | sed 's/^/    /' || true
}
${show_only} && exit 0

if ! ${assume_yes}; then
    note ""
    note "$(t "Was in ${NGINX_SITE} von Hand geändert wurde, geht dabei verloren;" "What was changed by hand in ${NGINX_SITE} is lost by this;")"
    note "$(t "die bisherige Datei wird aufbewahrt." "the file before is kept.")"
    read -r -p "    $(t "Übernehmen? [j/N] " "Take it over? [y/N] ")" answer
    [[ "${answer}" =~ ^[JjYy] ]] || fail "$(t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed.")"
fi

kept="${CONFIG_DIR}/nginx-site.before-$(date +%Y%m%d-%H%M%S)"
cp -p "${NGINX_SITE}" "${kept}"
realip_had=false
if [[ -f "${NGINX_REALIP_SNIPPET}" ]]; then
    cp -p "${NGINX_REALIP_SNIPPET}" "${work}/realip.before"
    realip_had=true
fi
install_nginx_snippets
cat "${work}/site" > "${NGINX_SITE}"
if ! nginx -t -q 2> "${work}/messages"; then
    cat "${kept}" > "${NGINX_SITE}"
    # The file of the trusted addresses goes back as well: a wrong one would stop NGINX at its next start.
    if ${realip_had}; then cp -p "${work}/realip.before" "${NGINX_REALIP_SNIPPET}"; else rm -f "${NGINX_REALIP_SNIPPET}"; fi
    fail "$(t "NGINX nimmt die neue Datei nicht an; die bisherige gilt weiter. NGINX meldet:" "NGINX does not accept the new file; the one before stays in force. NGINX says:") $(head -n 3 "${work}/messages")"
fi
systemctl is-active --quiet nginx && systemctl reload nginx
say "$(t "Fertig. NGINX arbeitet mit der neuen Konfiguration." "Done. NGINX works with the new configuration.")"
note "$(t "Die bisherige Datei:" "The file before:") ${kept}"
