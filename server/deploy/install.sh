#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – installation on a fresh Ubuntu Server 24.04 LTS or 26.04 LTS
# (NFA-027, NFA-031, NFA-063) – also on a Raspberry Pi 4 or 5, with Ubuntu
# Server for the Raspberry Pi or with Raspberry Pi OS based on Debian 13,
# 64 bit each (NFA-070).
#
# Run it from the unpacked package:
#
#     sudo ./deploy/install.sh
#
# Started like this at a terminal, the script asks for the host name and for
# where the certificate comes from. For an unattended run pass the options:
#
#     sudo ./deploy/install.sh --domain rentalars.example.de --email you@example.de --yes
#
# At the end the script prints the address of the first-run setup. Open it in
# the browser, enter your company and the first administrator – done.
#
# The script sets up everything on this one server (NFA-028):
#   packages (Python, NGINX, MariaDB), a service user, the program with its
#   Python libraries, database and database user, the configuration file,
#   the application service, NGINX with HTTPS, daily backup and clean-up.
#
# Instead of a MariaDB on this server, Rentalars can use one that exists
# already (NFA-066). Database and user must be created there beforehand; the
# user needs all rights on that one database and NO others – the
# administrator "root", or any user with rights on the whole server or on
# further databases, is refused. The script checks that before it changes
# anything on this server.
#
# Database and backups can be encrypted (NFA-067); the script then shows a
# recovery key, which has to be written down (docs/betrieb/verschluesselung.md).
#
# Options
#   --domain NAME     the host name people will use, e.g. rentalars.example.de
#   --tls MODE        where the certificate comes from (NFA-035):
#                       letsencrypt  from Let's Encrypt, renewed automatically. The server
#                                    must be reachable from the internet on port 80. (default)
#                       dns          from Let's Encrypt with a DNS record as proof; for
#                                    servers that are only reachable by VPN. Asks you to
#                                    create a TXT record, or works unattended with
#                                    --dns-plugin (then it also renews automatically).
#                       own          a certificate you already have: --cert and --key
#                       selfsigned   made here, for trying things out. Browsers warn.
#   --email ADDRESS   for Let's Encrypt (expiry notices); needed for letsencrypt and dns
#   --cert FILE       with --tls own: the certificate including its chain (PEM)
#   --key FILE        with --tls own: the private key (PEM)
#   --dns-plugin NAME with --tls dns: a certbot DNS plugin, e.g. cloudflare, hetzner, rfc2136
#   --dns-credentials FILE   the access data for that plugin (see the plugin's documentation)
#
#   Database on another server (NFA-066):
#   --db-host HOST    the MariaDB server (DNS name or IP address); without it, MariaDB is
#                     installed on this server
#   --db-port PORT    its port (default 3306)
#   --db-name NAME    the database; it must exist and be empty
#   --db-user USER    the user with all rights on this database and no others; never root
#   --db-password-file FILE   a file with the password in its first line. Without it the
#                     password is asked for, or taken from the variable RENTALARS_DB_PASSWORD.
#                     (Not as an option: it would show in the process list.)
#   --db-tls-ca FILE  check the server's certificate (and name) against this CA certificate
#   --db-no-tls       do not encrypt the connection (only within a trusted network)
#
#   Encryption (NFA-067):
#   --encrypt         encrypt database and backups; the recovery key is shown at the end
#   --no-encrypt      do not (the default)
#
#   --yes             do not ask for confirmation
#
# The script does not change an existing installation. To install a new
# version use:  sudo rentalars update PACKAGE
set -euo pipefail
SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
SOURCE_TREE="$(dirname "${SCRIPT_DIR}")"
# shellcheck source=deploy/lib.sh
source "${SCRIPT_DIR}/lib.sh"

# --- Options ---------------------------------------------------------------------

domain="" tls_mode="" email="" own_certificate="" own_key=""
dns_plugin="" dns_credentials="" assume_yes=false
db_host="" db_port="" db_name="" db_user="" db_password_file="" db_tls="" db_tls_ca=""
encrypt=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain) domain="${2:-}"; shift 2 ;;
        --tls) tls_mode="${2:-}"; shift 2 ;;
        --email) email="${2:-}"; shift 2 ;;
        --cert) own_certificate="${2:-}"; shift 2 ;;
        --key) own_key="${2:-}"; shift 2 ;;
        --dns-plugin) dns_plugin="${2:-}"; shift 2 ;;
        --dns-credentials) dns_credentials="${2:-}"; shift 2 ;;
        --db-host) db_host="${2:-}"; shift 2 ;;
        --db-port) db_port="${2:-}"; shift 2 ;;
        --db-name) db_name="${2:-}"; shift 2 ;;
        --db-user) db_user="${2:-}"; shift 2 ;;
        --db-password-file) db_password_file="${2:-}"; shift 2 ;;
        --db-tls-ca) db_tls_ca="${2:-}"; db_tls=true; shift 2 ;;
        --db-no-tls) db_tls=false; shift ;;
        --encrypt) encrypt=true; shift ;;
        --no-encrypt) encrypt=false; shift ;;
        --yes) assume_yes=true; shift ;;
        -h|--help) sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "$(t "Unbekannte Option: $1 (Hilfe: $0 --help)" "Unknown option: $1 (help: $0 --help)")" ;;
    esac
done

# --- Questions for whatever was not given as an option ----------------------------------
# Only at a terminal. An unattended run gets the defaults and must name the domain.
# UIX-029: the questions in German or English, as the operator reads (lib.sh, t).

require_root
if [[ -t 0 ]]; then
    if [[ -z "${domain}" ]]; then
        t "Unter welchem Namen werden die Nutzer Rentalars im Browser öffnen?" "Under which name will the users open Rentalars in the browser?"; echo
        read -r -p "$(t "Hostname (z. B. rentalars.example.de): " "Host name (e.g. rentalars.example.de): ")" domain
    fi
    if [[ -z "${tls_mode}" ]]; then
        echo
        if [[ "$(operator_language)" == de ]]; then
            echo "Woher kommt das Zertifikat für HTTPS?"
            echo "  1) Let's Encrypt – der Server ist aus dem Internet auf Port 80 erreichbar"
            echo "  2) Let's Encrypt mit DNS-Eintrag – der Server ist nur intern oder per VPN erreichbar"
            echo "  3) Eigenes Zertifikat – die Dateien liegen schon auf diesem Server"
            echo "  4) Selbst erstelltes Zertifikat – nur zum Ausprobieren, Browser warnen"
        else
            echo "Where does the certificate for HTTPS come from?"
            echo "  1) Let's Encrypt – the server can be reached from the internet on port 80"
            echo "  2) Let's Encrypt with a DNS record – the server can only be reached internally or by VPN"
            echo "  3) Own certificate – the files are on this server already"
            echo "  4) Self-signed certificate – only for trying things out, browsers warn"
        fi
        read -r -p "$(t "Auswahl [1]: " "Choice [1]: ")" answer
        case "${answer:-1}" in
            1) tls_mode="letsencrypt" ;;
            2) tls_mode="dns" ;;
            3) tls_mode="own" ;;
            4) tls_mode="selfsigned" ;;
            *) fail "$(t "Bitte 1, 2, 3 oder 4 eingeben." "Please enter 1, 2, 3 or 4.")" ;;
        esac
    fi
    if [[ "${tls_mode}" =~ ^(letsencrypt|dns)$ && -z "${email}" ]]; then
        echo
        t "Let's Encrypt schickt Hinweise zum Ablauf des Zertifikats an eine E-Mail-Adresse." "Let's Encrypt sends notices about the expiry of the certificate to an e-mail address."; echo
        read -r -p "$(t "E-Mail-Adresse: " "E-mail address: ")" email
    fi
    if [[ "${tls_mode}" == "own" && -z "${own_certificate}" ]]; then
        echo
        read -r -p "$(t "Datei mit dem Zertifikat samt Kette (PEM): " "File with the certificate and its chain (PEM): ")" own_certificate
        read -r -p "$(t "Datei mit dem privaten Schlüssel (PEM): " "File with the private key (PEM): ")" own_key
    fi
    if [[ -z "${db_host}" && -z "${db_name}${db_user}" ]]; then
        echo
        if [[ "$(operator_language)" == de ]]; then
            echo "Wo liegt die Datenbank?"
            echo "  1) Auf diesem Server – das Skript richtet MariaDB ein"
            echo "  2) Auf einem vorhandenen MariaDB-Server – Datenbank und Benutzer sind dort angelegt"
        else
            echo "Where is the database?"
            echo "  1) On this server – the script sets up MariaDB"
            echo "  2) On an existing MariaDB server – database and user are created there already"
        fi
        read -r -p "$(t "Auswahl [1]: " "Choice [1]: ")" answer
        case "${answer:-1}" in
            1) ;;
            2) read -r -p "$(t "Host (DNS-Name oder IP-Adresse): " "Host (DNS name or IP address): ")" db_host
               read -r -p "Port [3306]: " db_port
               read -r -p "$(t "Name der Datenbank: " "Name of the database: ")" db_name
               read -r -p "$(t "Benutzer (nicht root): " "User (not root): ")" db_user ;;
            *) fail "$(t "Bitte 1 oder 2 eingeben." "Please enter 1 or 2.")" ;;
        esac
    fi
    if [[ -n "${db_host}" && -z "${db_password_file}" && -z "${RENTALARS_DB_PASSWORD:-}" ]]; then
        read -r -s -p "$(t "Passwort von ${db_user:-?}: " "Password of ${db_user:-?}: ")" RENTALARS_DB_PASSWORD
        echo
    fi
    if [[ -n "${db_host}" && -z "${db_tls}" ]]; then
        read -r -p "$(t "Verbindung zur Datenbank mit TLS verschlüsseln? [J/n] " "Encrypt the connection to the database with TLS? [Y/n] ")" answer
        if [[ -z "${answer}" || "${answer}" =~ ^[JjYy] ]]; then
            db_tls=true
            t "Mit dem CA-Zertifikat des Datenbankservers prüft Rentalars, dass es wirklich mit" "With the CA certificate of the database server, Rentalars checks that it really talks to"; echo
            t "diesem Server spricht. Ohne wird nur verschlüsselt." "that server. Without it, the connection is only encrypted."; echo
            read -r -p "$(t "Datei mit dem CA-Zertifikat (PEM, leer: nicht prüfen): " "File with the CA certificate (PEM, empty: do not check): ")" db_tls_ca
        else
            db_tls=false
        fi
    fi
    if [[ -z "${encrypt}" ]]; then
        echo
        if [[ "$(operator_language)" == de ]]; then
            if [[ -z "${db_host}" ]]; then
                echo "Datenbank und Sicherungen verschlüsseln? Dann zeigt das Skript am Ende einen"
                echo "Wiederherstellungsschlüssel, der aufgeschrieben werden muss."
            else
                echo "Sicherungen verschlüsseln? Die Datenbank selbst verschlüsselt der Datenbankserver"
                echo "– oder nicht; das Skript sagt, was es dort vorfindet. Bei Ja zeigt es am Ende einen"
                echo "Wiederherstellungsschlüssel, der aufgeschrieben werden muss."
            fi
        else
            if [[ -z "${db_host}" ]]; then
                echo "Encrypt database and backups? Then the script shows a recovery key at the end,"
                echo "which has to be written down."
            else
                echo "Encrypt the backups? The database itself is encrypted by the database server – or"
                echo "not; the script says what it finds there. With yes, it shows a recovery key at the"
                echo "end, which has to be written down."
            fi
        fi
        read -r -p "$(t "Verschlüsseln? [j/N] " "Encrypt? [y/N] ")" answer
        if [[ "${answer}" =~ ^[JjYy] ]]; then encrypt=true; else encrypt=false; fi
    fi
    echo
fi
tls_mode="${tls_mode:-letsencrypt}"
encrypt="${encrypt:-false}"

# --- Checks before anything is changed -------------------------------------------------

[[ -n "${domain}" ]] || fail "$(t "Bitte den Hostnamen angeben: --domain rentalars.example.de" "Please give the host name: --domain rentalars.example.de")"
[[ "${domain}" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || fail "$(t "'${domain}' ist kein gültiger Hostname." "'${domain}' is no valid host name.")"
case "${tls_mode}" in
    letsencrypt|dns)
        [[ -n "${email}" ]] || fail "$(t "Für ein Zertifikat von Let's Encrypt wird eine E-Mail-Adresse gebraucht: --email du@example.de" "A certificate from Let's Encrypt needs an e-mail address: --email you@example.com")" ;;
    own)
        [[ -f "${own_certificate}" && -f "${own_key}" ]] \
            || fail "$(t "Mit --tls own werden --cert DATEI und --key DATEI gebraucht (beide im PEM-Format)." "With --tls own, --cert FILE and --key FILE are needed (both in PEM format).")" ;;
    selfsigned) ;;
    *) fail "$(t "Unbekannte Angabe für --tls: ${tls_mode} (möglich: letsencrypt, dns, own, selfsigned)" "Unknown value for --tls: ${tls_mode} (possible: letsencrypt, dns, own, selfsigned)")" ;;
esac
if [[ -n "${dns_plugin}" ]]; then
    [[ "${tls_mode}" == "dns" ]] || fail "$(t "--dns-plugin gehört zu --tls dns." "--dns-plugin belongs to --tls dns.")"
    [[ -f "${dns_credentials}" ]] || fail "$(t "Für --dns-plugin wird --dns-credentials DATEI gebraucht." "--dns-plugin needs --dns-credentials FILE.")"
fi
db_password=""
if [[ -n "${db_host}" ]]; then
    [[ "${db_host}" =~ ^[A-Za-z0-9]([A-Za-z0-9.:-]*[A-Za-z0-9])?$ ]] || fail "$(t "'${db_host}' ist kein gültiger Hostname und keine IP-Adresse." "'${db_host}' is neither a valid host name nor an IP address.")"
    db_port="${db_port:-3306}"
    [[ "${db_port}" =~ ^[0-9]+$ && "${db_port}" -ge 1 && "${db_port}" -le 65535 ]] || fail "$(t "'${db_port}' ist kein gültiger Port." "'${db_port}' is no valid port.")"
    [[ -n "${db_name}" ]] || fail "$(t "Bitte den Namen der Datenbank angeben: --db-name NAME" "Please give the name of the database: --db-name NAME")"
    [[ -n "${db_user}" ]] || fail "$(t "Bitte den Benutzer der Datenbank angeben: --db-user BENUTZER" "Please give the user of the database: --db-user USER")"
    # The administrator of the database server is never stored (NFA-066).
    # Other accounts with too many rights are found by the check further down.
    [[ "${db_user,,}" != "root" ]] \
        || fail "$(t "Der Benutzer root wird nicht hinterlegt. Bitte auf dem Datenbankserver einen Benutzer anlegen, der nur Rechte auf die Datenbank ${db_name} hat (docs/betrieb/installation.md, Abschnitt Vorhandener Datenbankserver)." "The user root is not stored. Please create a user on the database server that has rights on the database ${db_name} only (docs/en/operations/installation.md, section Existing database server).")"
    if [[ -n "${db_password_file}" ]]; then
        [[ -f "${db_password_file}" ]] || fail "$(t "Die Passwortdatei ${db_password_file} gibt es nicht." "The password file ${db_password_file} does not exist.")"
        db_password="$(head -n 1 "${db_password_file}")"
    else
        db_password="${RENTALARS_DB_PASSWORD:-}"
    fi
    [[ -n "${db_password}" ]] || fail "$(t "Bitte das Passwort des Datenbankbenutzers angeben: --db-password-file DATEI" "Please give the password of the database user: --db-password-file FILE")"
    [[ "${db_password}" != " "* && "${db_password}" != *" " ]] || fail "$(t "Das Passwort darf nicht mit einem Leerzeichen beginnen oder enden." "The password must not begin or end with a space.")"
    db_tls="${db_tls:-true}"
    if [[ -n "${db_tls_ca}" ]]; then
        [[ -f "${db_tls_ca}" ]] || fail "$(t "Das CA-Zertifikat ${db_tls_ca} gibt es nicht." "The CA certificate ${db_tls_ca} does not exist.")"
        openssl x509 -in "${db_tls_ca}" -noout > /dev/null 2>&1 || fail "$(t "${db_tls_ca} ist kein Zertifikat im PEM-Format." "${db_tls_ca} is no certificate in PEM format.")"
    fi
else
    [[ -z "${db_name}${db_user}${db_password_file}${db_tls_ca}${db_port}" ]] \
        || fail "$(t "Die Angaben --db-… gehören zu einem vorhandenen Datenbankserver: Bitte auch --db-host angeben." "The options --db-… belong to an existing database server: please give --db-host as well.")"
    db_name="rentalars" db_user="rentalars"
fi
[[ -f "${SOURCE_TREE}/manage.py" ]] || fail "$(t "Bitte das Skript aus dem entpackten Paket starten: sudo ./deploy/install.sh …" "Please start the script from the unpacked package: sudo ./deploy/install.sh …")"
[[ ! -e "${CONFIG_FILE}" && ! -e "${APP_DIR}" ]] \
    || fail "$(t "Rentalars ist hier schon installiert. Eine neue Version einspielen: sudo rentalars update PAKET" "Rentalars is installed here already. To install a new version: sudo rentalars update PACKAGE")"

# Ubuntu Server 24.04 or newer; on a Raspberry Pi also Raspberry Pi OS based
# on Debian 13; always 64 bit (NFA-063, NFA-070). Fails here otherwise.
check_system "${OS_RELEASE_FILE}" "${DEVICE_MODEL_FILE}" "$(dpkg --print-architecture 2> /dev/null || true)"
check_free_space / 3000

# A Raspberry Pi: what it brings, and what deserves a warning before anything
# is changed (NFA-070). Nothing of this on other computers.
pi_warnings=()
if [[ -n "${SYSTEM_MODEL}" ]]; then
    memory="$(memory_mb "${MEMORY_INFO_FILE}")"
    if (( memory > 0 && memory < FOUR_GB_IN_MB )); then
        pi_warnings+=("$(t "Dieser Raspberry Pi hat $(memory_text "${memory}") Arbeitsspeicher; vorgesehen sind mindestens 4 GB. Rentalars stellt sich darauf ein – weniger Arbeitsprozesse, weniger Zwischenspeicher für die Datenbank. Für eine Person, die gerade arbeitet, reicht das; PDF-Erzeugung, Import und Sicherung dauern länger, und mehrere Personen gleichzeitig warten aufeinander." "This Raspberry Pi has $(memory_text "${memory}") of memory; at least 4 GB are meant. Rentalars adapts to it – fewer worker processes, less cache for the database. That is enough for one person working at a time; making PDFs, imports and backups take longer, and several people at once wait for each other.")")
    fi
    # The database and the files go to /var/lib, the backups to /var/backups.
    mapfile -t on_sd_card < <(places_on_sd_card /var/lib /var/backups)
    case "${on_sd_card[*]}" in
        "/var/lib /var/backups") what="$(t "Datenbank, Dateien und Sicherungen lägen" "Database, files and backups would lie")" ;;
        "/var/lib") what="$(t "Datenbank und Dateien lägen" "Database and files would lie")" ;;
        "/var/backups") what="$(t "Die Sicherungen lägen" "The backups would lie")" ;;
        *) what="" ;;
    esac
    if [[ -n "${what}" ]]; then
        pi_warnings+=("${what} $(t "auf der SD-Karte. SD-Karten nutzen sich durch die vielen kleinen Schreibvorgänge einer Datenbank ab und fallen dann ohne Vorwarnung aus – mit allem, was darauf liegt. Empfohlen: den Raspberry Pi von einer SSD starten (per USB, beim Raspberry Pi 5 auch NVMe); siehe docs/betrieb/installation.md, Abschnitt Raspberry Pi. Wenn du trotzdem weitermachst: Hol die Sicherungen jeden Tag vom Gerät." "on the SD card. SD cards wear out from the many small writes of a database and then fail without warning – with everything on them. Recommended: start the Raspberry Pi from an SSD (by USB, on the Raspberry Pi 5 also NVMe); see docs/en/operations/installation.md, section Raspberry Pi. If you go on all the same: take the backups off the device every day.")")
    fi
fi

version="$(version_of "${SOURCE_TREE}")"
say "$(t "Rentalars ${version} wird installiert" "Installing Rentalars ${version}")"
if [[ -n "${db_host}" ]]; then
    tls_text="$(t "unverschlüsselt" "not encrypted")"
    [[ "${db_tls}" == "true" ]] && tls_text="$(t "TLS, Zertifikat ungeprüft" "TLS, certificate not checked")"
    [[ -n "${db_tls_ca}" ]] && tls_text="$(t "TLS, Zertifikat geprüft" "TLS, certificate checked")"
fi
if [[ "$(operator_language)" == de ]]; then
    note "Adresse:      https://${domain}"
    note "Zertifikat:   ${tls_mode}"
    if [[ -n "${db_host}" ]]; then
        note "Datenbank:    ${db_name} auf ${db_host}:${db_port} als ${db_user} (${tls_text})"
    else
        note "Datenbank:    MariaDB auf diesem Server"
    fi
    if [[ "${encrypt}" == "true" ]]; then
        if [[ -n "${db_host}" ]]; then note "Verschlüsselt: Sicherungen"; else note "Verschlüsselt: Datenbank und Sicherungen"; fi
    else
        note "Verschlüsselt: nein"
    fi
    note "System:       ${SYSTEM_NAME}${SYSTEM_NOTE}"
    if [[ -n "${SYSTEM_MODEL}" ]]; then
        note "Gerät:        ${SYSTEM_MODEL}, $(memory_text "$(memory_mb "${MEMORY_INFO_FILE}")") Arbeitsspeicher, ${SYSTEM_ARCHITECTURE}"
    fi
else
    note "Address:      https://${domain}"
    note "Certificate:  ${tls_mode}"
    if [[ -n "${db_host}" ]]; then
        note "Database:     ${db_name} on ${db_host}:${db_port} as ${db_user} (${tls_text})"
    else
        note "Database:     MariaDB on this server"
    fi
    if [[ "${encrypt}" == "true" ]]; then
        if [[ -n "${db_host}" ]]; then note "Encrypted:    backups"; else note "Encrypted:    database and backups"; fi
    else
        note "Encrypted:    no"
    fi
    note "System:       ${SYSTEM_NAME}${SYSTEM_NOTE}"
    if [[ -n "${SYSTEM_MODEL}" ]]; then
        note "Device:       ${SYSTEM_MODEL}, $(memory_text "$(memory_mb "${MEMORY_INFO_FILE}")") of memory, ${SYSTEM_ARCHITECTURE}"
    fi
fi
for pi_warning in "${pi_warnings[@]}"; do
    warn "${pi_warning}"
done
if ! ${assume_yes}; then
    read -r -p "    $(t "Installation starten? [J/n] " "Start the installation? [Y/n] ")" answer
    [[ -z "${answer}" || "${answer}" =~ ^[JjYy] ]] || fail "$(t "Abgebrochen. Es wurde nichts verändert." "Cancelled. Nothing was changed.")"
fi

# --- 1. Packages (NFA-029) -----------------------------------------------------------

say "$(t "1/9  Pakete des Betriebssystems" "1/9  Packages of the operating system")"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# Python, NGINX, MariaDB (unless it is elsewhere), the tools to build the
# MariaDB connector, the libraries for PDF creation, certbot – under the
# names of this system (lib.sh, system_packages).
local_database=false
[[ -z "${db_host}" ]] && local_database=true
mapfile -t packages < <(system_packages "${SYSTEM_ID}" "${local_database}" "${tls_mode}" "${dns_plugin}")
(( ${#packages[@]} > 0 )) || fail "$(t "Für ${SYSTEM_NAME} kennt das Skript keine Pakete." "The script knows no packages for ${SYSTEM_NAME}.")"
apt-get install -y -qq --no-install-recommends "${packages[@]}" > /dev/null
check_python_version

# --- 2. Database (NFA-042, NFA-066, NFA-067) ---------------------------------------------------
# Before anything of Rentalars is written: if the database on the other
# server is not fit, the installation stops here and can simply be repeated.

say "$(t "2/9  Datenbank" "2/9  Database")"
work="$(mktemp -d)"
trap 'rm -rf "${work}"' EXIT
recovery_key=""
if [[ "${encrypt}" == "true" ]]; then
    # A second attempt keeps the key of the first one: MariaDB may already
    # have encrypted files with it.
    recovery_key="$(existing_recovery_key)"
    [[ -n "${recovery_key}" ]] || recovery_key="$(new_recovery_key)"
    store_recovery_key "${recovery_key}"
fi

if [[ -n "${db_host}" ]]; then
    db_tls_flags=()
    [[ "${db_tls}" == "true" ]] && db_tls_flags+=(--expect-tls)
    [[ -n "${db_tls_ca}" ]] && db_tls_flags+=(--tls-verified)
    if [[ -n "${db_tls_ca}" ]]; then
        # Kept with the configuration: the application reads it at every start.
        install -d -m 750 -o root -g root "${CONFIG_DIR}"
        install -m 644 "${db_tls_ca}" "${CONFIG_DIR}/database-ca.pem"
        db_tls_ca="${CONFIG_DIR}/database-ca.pem"
    fi
    write_client_file "${work}/client.cnf" "${db_user}" "${db_password}" "${db_host}" "${db_port}" "${db_tls}" "${db_tls_ca}"
    note "$(t "Prüfe ${db_user} auf ${db_host}:${db_port} …" "Checking ${db_user} on ${db_host}:${db_port} …")"
    check_status=0
    check_database_account "${SOURCE_TREE}" "${work}/client.cnf" "${db_name}" \
        --require-empty --fix-charset --try-tables "${db_tls_flags[@]}" | sed 's/^/    /' || check_status=${PIPESTATUS[0]}
    if [[ "${check_status}" -ne 0 ]]; then
        fail "$(t "Diese Datenbank kann Rentalars nicht verwenden (siehe oben). Auf diesem Server wurden nur Pakete installiert; nach der Korrektur das Skript einfach noch einmal starten." "Rentalars cannot use this database (see above). Only packages were installed on this server; once it is corrected, simply start the script once more.")"
    fi
    rm -f "${work}/client.cnf"
    database_password="${db_password}"
else
    install -m 644 "${SOURCE_TREE}/deploy/mariadb/60-rentalars.cnf" "${MARIADB_SETTINGS}"
    # Less memory for MariaDB on a Raspberry Pi with less than 4 GB (NFA-042, NFA-070).
    write_database_memory_settings "${MARIADB_MEMORY_SETTINGS}" "${SYSTEM_MODEL}" "$(memory_mb "${MEMORY_INFO_FILE}")"
    if [[ "${encrypt}" == "true" ]]; then
        # Before the database is created: then every table is encrypted from the start.
        write_mariadb_encryption "${RECOVERY_KEY_FILE}" "${SOURCE_TREE}"
    fi
    systemctl enable --quiet mariadb
    systemctl restart mariadb
    if [[ "${encrypt}" == "true" ]]; then
        mariadb_encryption_active || fail "$(t "MariaDB verschlüsselt nicht – die Schlüsselverwaltung ließ sich nicht laden. Die Meldungen stehen in: journalctl -u mariadb" "MariaDB does not encrypt – its key management could not be loaded. The messages are in: journalctl -u mariadb")"
        note "$(t "MariaDB verschlüsselt seine Dateien." "MariaDB encrypts its files.")"
    fi
    database_password="$(openssl rand -hex 24)"
    # On Ubuntu and Debian, root reaches MariaDB through the local socket without a password.
    mariadb <<SQL
CREATE DATABASE IF NOT EXISTS rentalars CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'rentalars'@'localhost' IDENTIFIED BY '${database_password}';
ALTER USER 'rentalars'@'localhost' IDENTIFIED BY '${database_password}';
GRANT ALL PRIVILEGES ON rentalars.* TO 'rentalars'@'localhost';
FLUSH PRIVILEGES;
SQL
fi

# --- 3. Service user and folders ---------------------------------------------------------

say "$(t "3/9  Dienstkonto und Verzeichnisse" "3/9  Service account and folders")"
data_dir="${DEFAULT_DATA_DIR}"
if ! id "${SERVICE_USER}" > /dev/null 2>&1; then
    # A system account without login: the application runs under it and owns
    # only its data directory.
    useradd --system --home-dir "${data_dir}" --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi
install -d -m 755 -o root -g root "${RENTALARS_HOME}" "${RELEASES_DIR}"
install -d -m 750 -o root -g "${SERVICE_USER}" "${CONFIG_DIR}"
install -d -m 750 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${data_dir}" "${data_dir}/media" "${data_dir}/imports"
# NGINX delivers the static files; they hold nothing confidential.
install -d -m 755 -o "${SERVICE_USER}" -g "${SERVICE_USER}" "${data_dir}/static"
install -d -m 700 -o root -g root "${DEFAULT_BACKUP_DIR}"
# NGINX (user www-data) must be able to enter the data directory to reach
# "static" and – after the application allowed it – "media", and to reach the socket of the application.
usermod -a -G "${SERVICE_USER}" www-data

# --- 4. Program and Python libraries --------------------------------------------------------

say "$(t "4/9  Programm und Python-Bibliotheken" "4/9  Program and Python libraries")"
release="$(build_release "${SOURCE_TREE}")"
activate_release "${release}"
note "${release}"

# --- 5. Configuration file (NFA-032) --------------------------------------------------------

say "$(t "5/9  Konfigurationsdatei" "5/9  Configuration file") ${CONFIG_FILE}"
( umask 027
  sed -e "s|^url = .*|url = https://${domain}|" \
      -e "s|^secret_key = .*|secret_key = $(openssl rand -hex 48)|" \
      "${APP_DIR}/deploy/rentalars.conf.example" > "${CONFIG_FILE}" )
# Not readable for the group of the service account, which NGINX belongs to: see protect_configuration.
protect_configuration "${CONFIG_FILE}"
config_set "${CONFIG_FILE}" database name "${db_name}"
config_set "${CONFIG_FILE}" database user "${db_user}"
config_set "${CONFIG_FILE}" database password "${database_password}"
if [[ -n "${db_host}" ]]; then
    config_set "${CONFIG_FILE}" database host "${db_host}"
    config_set "${CONFIG_FILE}" database port "${db_port}"
    config_set "${CONFIG_FILE}" database tls "${db_tls}"
    [[ -n "${db_tls_ca}" ]] && config_set "${CONFIG_FILE}" database tls_ca "${db_tls_ca}"
    if [[ -f "${CONFIG_DIR}/database-ca.pem" ]]; then
        chown root:"${SERVICE_USER}" "${CONFIG_DIR}/database-ca.pem"
        chmod 640 "${CONFIG_DIR}/database-ca.pem"
    fi
fi
[[ "${encrypt}" == "true" ]] && config_set "${CONFIG_FILE}" backup encrypt true

# --- 6. Tables and static files ---------------------------------------------------------------

say "$(t "6/9  Tabellen anlegen, statische Dateien sammeln" "6/9  Creating tables, collecting static files")"
manage migrate --noinput > /dev/null
manage collectstatic --noinput --clear > /dev/null
# The one-time key for the first-run setup is created now, before anything
# answers requests (NFA-064). The setup page creates the first administrator
# and stays closed without a key – but the key must exist before the address
# can be reached, not a moment after.
setup_address="$(manage prepare_setup)"
[[ "${setup_address}" == *"/setup/?token="* ]] || fail "$(t "Der Schlüssel für die Ersteinrichtung ließ sich nicht anlegen:" "The key for the first-run setup could not be created:") ${setup_address}"

# --- 7. Application service and timers (NFA-036) -------------------------------------------------

say "$(t "7/9  Anwendungsdienst und Zeitpläne: Sicherung, Aufräumen, Mailabruf, Aufgaben im Hintergrund" "7/9  Application service and timers: backup, tidy-up, fetching mails, tasks in the background")"
install_units
# A link, not a copy: the command then always belongs to the installed version.
install_cli
systemctl enable --quiet --now rentalars.service
enable_timers
application_answers || fail "$(t "Die Anwendung antwortet nicht. Die Meldungen stehen in: journalctl -u rentalars" "The application does not answer. The messages are in: journalctl -u rentalars")"

# --- 8. Certificate (NFA-035) ------------------------------------------------------------------

say "$(t "8/9  Zertifikat" "8/9  Certificate") (${tls_mode})"
install -d -m 755 "${ACME_ROOT}"
install -d -m 750 -o root -g root "${CONFIG_DIR}/tls"
rm -f /etc/nginx/sites-enabled/default
install_nginx_snippets
site="${NGINX_SITE}"
ln -sfn "${site}" "${NGINX_SITE_LINK}"
systemctl enable --quiet nginx

certificate="" private_key=""

# Write the NGINX site from a template of the package: write_nginx_site TEMPLATE
write_nginx_site() {
    render_nginx_site "$1" "${site}" "${domain}" "${certificate}" "${private_key}" "${data_dir}"
}

case "${tls_mode}" in
    letsencrypt)
        # NGINX answers on port 80 first, so that Let's Encrypt can check the domain.
        write_nginx_site "${APP_DIR}/deploy/nginx/rentalars-http-only.conf"
        nginx -t -q && systemctl restart nginx
        certbot certonly --non-interactive --agree-tos --email "${email}" \
            --webroot --webroot-path "${ACME_ROOT}" -d "${domain}" \
            --deploy-hook "systemctl reload nginx" \
            || fail "$(t "Let's Encrypt konnte kein Zertifikat ausstellen. Ist ${domain} aus dem Internet auf Port 80 erreichbar? Sonst: --tls dns" "Let's Encrypt could not issue a certificate. Can ${domain} be reached from the internet on port 80? Otherwise: --tls dns")"
        certificate="/etc/letsencrypt/live/${domain}/fullchain.pem"
        private_key="/etc/letsencrypt/live/${domain}/privkey.pem"
        ;;
    dns)
        if [[ -n "${dns_plugin}" ]]; then
            chmod 600 "${dns_credentials}"
            certbot certonly --non-interactive --agree-tos --email "${email}" \
                "--dns-${dns_plugin}" "--dns-${dns_plugin}-credentials" "${dns_credentials}" -d "${domain}" \
                --deploy-hook "systemctl reload nginx" \
                || fail "$(t "Let's Encrypt konnte kein Zertifikat ausstellen. Stimmen die Zugangsdaten in ${dns_credentials}?" "Let's Encrypt could not issue a certificate. Are the access data in ${dns_credentials} right?")"
        else
            if [[ "$(operator_language)" == de ]]; then
                note "certbot nennt gleich einen TXT-Eintrag. Lege ihn bei deinem DNS-Anbieter an,"
                note "warte, bis er abrufbar ist, und bestätige dann mit Enter."
                note "Achtung: Auf diesem Weg erneuert sich das Zertifikat NICHT von selbst; es gilt"
                note "90 Tage. Erneuern: denselben certbot-Befehl wiederholen (docs/betrieb/betrieb.md)."
            else
                note "certbot names a TXT record in a moment. Create it at your DNS provider,"
                note "wait until it can be looked up, and then confirm with Enter."
                note "Note: this way the certificate does NOT renew by itself; it is valid for"
                note "90 days. To renew: repeat the same certbot command (docs/en/operations/operation.md)."
            fi
            certbot certonly --manual --preferred-challenges dns --agree-tos --email "${email}" -d "${domain}" \
                || fail "$(t "Let's Encrypt konnte kein Zertifikat ausstellen." "Let's Encrypt could not issue a certificate.")"
        fi
        certificate="/etc/letsencrypt/live/${domain}/fullchain.pem"
        private_key="/etc/letsencrypt/live/${domain}/privkey.pem"
        ;;
    own)
        openssl x509 -in "${own_certificate}" -noout > /dev/null 2>&1 || fail "$(t "${own_certificate} ist kein Zertifikat im PEM-Format." "${own_certificate} is no certificate in PEM format.")"
        install -m 644 "${own_certificate}" "${CONFIG_DIR}/tls/certificate.pem"
        install -m 600 "${own_key}" "${CONFIG_DIR}/tls/private-key.pem"
        certificate="${CONFIG_DIR}/tls/certificate.pem"
        private_key="${CONFIG_DIR}/tls/private-key.pem"
        ;;
    selfsigned)
        openssl req -x509 -newkey rsa:3072 -nodes -days 825 \
            -subj "/CN=${domain}" -addext "subjectAltName=DNS:${domain}" \
            -keyout "${CONFIG_DIR}/tls/private-key.pem" -out "${CONFIG_DIR}/tls/certificate.pem" 2> /dev/null
        chmod 600 "${CONFIG_DIR}/tls/private-key.pem"
        certificate="${CONFIG_DIR}/tls/certificate.pem"
        private_key="${CONFIG_DIR}/tls/private-key.pem"
        note "$(t "Selbst erstelltes Zertifikat: Browser zeigen eine Warnung. Nur zum Ausprobieren." "Self-signed certificate: browsers show a warning. Only for trying things out.")"
        ;;
esac

# --- 9. NGINX with HTTPS (NFA-030) ----------------------------------------------------------------

say "$(t "9/9  NGINX mit HTTPS" "9/9  NGINX with HTTPS")"
write_nginx_site "${APP_DIR}/deploy/nginx/rentalars.conf"
nginx -t -q || fail "$(t "Die NGINX-Konfiguration ${site} ist fehlerhaft (siehe oben)." "The NGINX configuration ${site} has errors (see above).")"
systemctl restart nginx

# A first backup at once: it shows that backing up works here – with
# encryption and with a database elsewhere too – and the self-check has a
# backup to judge from the first day on (NFA-015, NFA-037).
if first_backup="$(bash "${APP_DIR}/deploy/backup.sh" 2>&1)"; then
    first_backup="$(printf '%s\n' "${first_backup}" | tail -n 1)"
else
    warn "$(t "Die erste Sicherung ist fehlgeschlagen; die Installation ist trotzdem fertig. Die Meldung:" "The first backup failed; the installation is finished all the same. The message:") $(printf '%s' "${first_backup}" | tail -n 1). $(t "Von Hand: sudo rentalars backup" "By hand: sudo rentalars backup")"
    first_backup=""
fi

# --- Done ----------------------------------------------------------------------------------------

say "$(t "Rentalars ${version} ist installiert." "Rentalars ${version} is installed.")"
note ""
note "$(t "Öffne jetzt diese Adresse im Browser und richte Firma und Administrator ein:" "Now open this address in the browser and set up company and administrator:")"
note ""
note "    ${setup_address}"
note ""
note "$(t "Die Adresse gilt einmal. Verloren? Eine neue gibt:  sudo rentalars prepare_setup" "The address works once. Lost it? A new one comes from:  sudo rentalars prepare_setup")"
note ""
if [[ "$(operator_language)" == de ]]; then
    note "Konfiguration:    ${CONFIG_FILE}   (E-Mail-Versand dort eintragen)"
    if [[ -n "${db_host}" ]]; then
        note "Datenbank:        ${db_name} auf ${db_host}:${db_port}"
    fi
    if [[ "${encrypt}" == "true" ]]; then
        note "Sicherungen:      /var/backups/rentalars, jede Nacht um 2:30 Uhr, verschlüsselt"
    else
        note "Sicherungen:      /var/backups/rentalars, jede Nacht um 2:30 Uhr"
    fi
    [[ -n "${first_backup}" ]] && note "Erste Sicherung:  ${first_backup}"
    note "Zustand prüfen:   sudo rentalars status"
    note "Anleitungen:      ${APP_DIR}/docs/betrieb/"
else
    note "Configuration:    ${CONFIG_FILE}   (enter the sending of e-mail there)"
    if [[ -n "${db_host}" ]]; then
        note "Database:         ${db_name} on ${db_host}:${db_port}"
    fi
    if [[ "${encrypt}" == "true" ]]; then
        note "Backups:          /var/backups/rentalars, every night at 2:30, encrypted"
    else
        note "Backups:          /var/backups/rentalars, every night at 2:30"
    fi
    [[ -n "${first_backup}" ]] && note "First backup:     ${first_backup}"
    note "Check the state:  sudo rentalars status"
    note "Guides:           ${APP_DIR}/docs/en/operations/"
fi
if [[ "${encrypt}" == "true" ]]; then
    present_recovery_key "${recovery_key}"
fi
