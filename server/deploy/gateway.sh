#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Rentalars – the link to the Rentalars Gateway.
#
#   sudo rentalars gateway connect 'RGWL1:…'     connect this installation to a gateway and switch the link service on
#   sudo rentalars gateway disconnect            switch the link service off and forget the gateway
#   sudo rentalars gateway status|pair|devices|revoke|announce-move|announce-clear|rekey   (see "rentalars gateway --help")
#
# The commands themselves are those of the application (manage.py gateway …); this script only adds what needs
# root: switching the systemd unit rentalars-gateway-link on and off, and restarting it after a new key.
# Without "connect" nothing runs and nothing changes: the apps keep using the server directly.
set -euo pipefail
# shellcheck source=deploy/lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/lib.sh"

readonly LINK_UNIT="rentalars-gateway-link"

subcommand="${1:-}"
case "${subcommand}" in
    connect)
        require_root
        manage gateway "$@"
        systemctl daemon-reload
        systemctl enable "${LINK_UNIT}" > /dev/null 2>&1 || true
        # restart, not start: a link service that already runs must read the new keys
        systemctl restart "${LINK_UNIT}"
        note "$(t "Der Dienst ${LINK_UNIT} läuft." "The service ${LINK_UNIT} is running.")"
        ;;
    disconnect)
        require_root
        manage gateway "$@"
        systemctl disable --now "${LINK_UNIT}" > /dev/null 2>&1 || true
        note "$(t "Der Dienst ${LINK_UNIT} ist abgeschaltet." "The service ${LINK_UNIT} is switched off.")"
        ;;
    rekey)
        require_root
        manage gateway "$@"
        if systemctl is-enabled --quiet "${LINK_UNIT}" 2> /dev/null; then systemctl restart "${LINK_UNIT}"; fi
        ;;
    *)
        require_root
        manage gateway "$@"
        ;;
esac
