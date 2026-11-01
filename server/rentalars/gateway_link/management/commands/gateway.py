# SPDX-License-Identifier: GPL-3.0-or-later
"""Command ``gateway``: the link to the Rentalars Gateway.

    sudo rentalars gateway connect 'RGWL1:…'     link up with a gateway (the text comes from "rentalars-gateway enroll")
    sudo rentalars gateway status                 is the link up, how many devices are paired
    sudo rentalars gateway pair NAME              a pairing code (text and QR code) for the account NAME
    sudo rentalars gateway devices [--all]        the paired devices
    sudo rentalars gateway revoke ID              lock a device out at once (ID or its first characters)
    sudo rentalars gateway disconnect             take the link down (devices and keys stay)
    sudo rentalars gateway announce-move …        tell the devices of a new gateway address or certificate
    sudo rentalars gateway announce-clear         end that announcement
    sudo rentalars gateway rekey --yes            a new end-to-end key – every device must be paired again

``serve`` is the service ``rentalars-gateway-link`` (``deploy/systemd``); ``is-configured`` is its condition.
Everything is in the operator's language (``RENTALARS_LANG``).
"""

from __future__ import annotations

import io
import os
import signal
import sys
import threading
import time
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import close_old_connections
from django.utils import timezone

from rentalars.core.models import CompanyProfile
from rentalars.gateway_link import protocol, service
from rentalars.gateway_link.models import GatewayDevice, GatewayLink, GatewayPairing, GatewayTokenBinding

#: Exit status that makes systemd start the service again (its settings changed).
RESTART_STATUS = 75
#: Exit status of ``is-configured`` when it cannot tell (systemd skips the unit for 1 to 254 and fails it above).
UNKNOWN_STATUS = 255


def _use_german() -> bool:
    return (os.environ.get("RENTALARS_LANG", "") or settings.LANGUAGE_CODE).startswith("de")


def t(german: str, english: str) -> str:
    """The text in the operator's language."""
    return german if _use_german() else english


class Command(BaseCommand):
    """The administrator's way to set up and look after the link to the gateway."""

    help = (
        "The link to the Rentalars Gateway: connect, status, pair, devices, revoke, disconnect, announce-move, rekey."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        """One sub-command per action."""
        actions = parser.add_subparsers(dest="action", required=True, parser_class=CommandParser)
        connect = actions.add_parser("connect", help="link up with a gateway")
        connect.add_argument("text", help="the connection text 'RGWL1:…' printed by 'rentalars-gateway enroll'")
        actions.add_parser("status", help="state of the link")
        pair = actions.add_parser("pair", help="a pairing code for an account")
        pair.add_argument("username", help="the account the device is paired for")
        pair.add_argument("--name", default="", help="a name suggested for the device")
        pair.add_argument("--minutes", type=int, default=10, help="how long the code holds (1 to 10)")
        pair.add_argument("--no-qr", action="store_true", help="print the text only")
        devices = actions.add_parser("devices", help="the paired devices")
        devices.add_argument("--all", action="store_true", help="including the revoked ones")
        revoke = actions.add_parser("revoke", help="lock a device out")
        revoke.add_argument("device", help="the id of the device or its first characters")
        actions.add_parser("disconnect", help="take the link down")
        move = actions.add_parser("announce-move", help="announce a new gateway address or certificate to the devices")
        move.add_argument("--url", required=True, help="the new address, https://…")
        move.add_argument("--fingerprint", required=True, help="SHA-256 of the new certificate (hex)")
        move.add_argument("--next", default="", help="the fingerprint of the certificate after that (optional)")
        actions.add_parser("announce-clear", help="end the announcement")
        rekey = actions.add_parser("rekey", help="a new end-to-end key; all devices must be paired again")
        rekey.add_argument("--yes", action="store_true", help="yes, I know that every device must be paired again")
        serve = actions.add_parser("serve", help="the service: fetch and answer the requests of the apps")
        serve.add_argument(
            "--workers", type=int, default=0, help="requests at the same time (default: [gateway] workers)"
        )
        actions.add_parser("is-configured", help="exit status 0 if a gateway is connected")

    def handle(self, *args: Any, **options: Any) -> None:
        """Run the action."""
        action = options["action"].replace("-", "_")
        getattr(self, f"do_{action}")(options)

    # --- helpers -------------------------------------------------------------------------------------------------

    def say(self, text: str = "") -> None:
        """Print a line."""
        self.stdout.write(text)

    @staticmethod
    def connected_link() -> GatewayLink:
        """The link, which must be connected."""
        link = GatewayLink.current()
        if link is None or not link.is_connected:
            raise CommandError(
                t(
                    "Es ist kein Gateway verbunden (rentalars gateway connect).",
                    "No gateway is connected (rentalars gateway connect).",
                )
            )
        return link

    @staticmethod
    def find_device(prefix: str) -> GatewayDevice:
        """The device whose id starts with ``prefix`` (at least four characters, unambiguous)."""
        prefix = prefix.strip().lower()
        if len(prefix) < 4:
            raise CommandError(
                t(
                    "Bitte mindestens vier Zeichen der Geräte-Kennung angeben.",
                    "Please give at least four characters of the device id.",
                )
            )
        found = list(GatewayDevice.objects.filter(device_id__startswith=prefix)[:2])
        if not found:
            raise CommandError(t("Kein Gerät mit dieser Kennung.", "No device with this id."))
        if len(found) > 1:
            raise CommandError(
                t(
                    "Mehrere Geräte passen – bitte mehr Zeichen angeben.",
                    "Several devices match – please give more characters.",
                )
            )
        return found[0]

    # --- actions -------------------------------------------------------------------------------------------------

    def do_connect(self, options: dict[str, Any]) -> None:
        """Link up with the gateway named in the connection text, using its one-off token."""
        try:
            text = protocol.LinkText.decode(options["text"])
        except protocol.ProtocolError:
            raise CommandError(
                t(
                    "Der Verbindungstext ist nicht lesbar. Er beginnt mit RGWL1: und stammt von 'rentalars-gateway enroll'.",
                    "The connection text cannot be read. It starts with RGWL1: and comes from 'rentalars-gateway enroll'.",
                )
            ) from None
        if not text.gateway.startswith("https://"):
            raise CommandError(
                t(
                    "Die Adresse des Gateways muss mit https:// beginnen.",
                    "The gateway's address must start with https://.",
                )
            )
        link = GatewayLink.current() or GatewayLink()
        if link.link_key:
            link_key = protocol.private_from_pem(link.link_key_pem())
        else:
            link_key = protocol.generate_private_key()
            link.set_link_key_pem(protocol.private_to_pem(link_key))
        if not link.e2e_key:
            link.set_e2e_key_pem(protocol.private_to_pem(protocol.generate_private_key()))
        try:
            answer = service.GatewayClient.enroll(text.gateway, text.gateway_fingerprint, text.token, link_key)
        except (service.GatewayLinkError, OSError) as error:
            raise CommandError(
                t(
                    f"Das Gateway ist nicht erreichbar oder lehnt die Einrichtung ab: {error}",
                    f"The gateway cannot be reached or refuses the setup: {error}",
                )
            ) from None
        was = link.gateway_url
        link.gateway_url = text.gateway
        link.gateway_fingerprint = text.gateway_fingerprint
        link.gateway_id = str(answer.get("gateway_id", text.gateway_id))[:100]
        link.enrolled_at = timezone.now()
        link.last_error = ""
        link.save()
        try:
            service.GatewayClient.for_link(link).push_registry()
        except (service.GatewayLinkError, OSError) as error:
            self.say(
                t(
                    f"Hinweis: Die Liste der Geräte konnte noch nicht gesendet werden ({error}); der Dienst holt das nach.",
                    f"Note: the list of devices could not be sent yet ({error}); the service will do it.",
                )
            )
        self.say(
            t(
                f"Verbunden mit {link.gateway_url} (Gateway-Version {answer.get('version', '?')}).",
                f"Connected to {link.gateway_url} (gateway version {answer.get('version', '?')}).",
            )
        )
        if was and was != link.gateway_url and GatewayDevice.objects.filter(revoked_at__isnull=True).exists():
            self.say(
                t(
                    "Achtung: Das ist ein anderes Gateway als bisher. Gekoppelte Apps kennen nur die alte Adresse – siehe 'rentalars gateway announce-move'.",
                    "Attention: this is another gateway than before. Paired apps only know the old address – see 'rentalars gateway announce-move'.",
                )
            )
        self.say(
            t(
                "Nächster Schritt: ein Gerät koppeln mit  sudo rentalars gateway pair BENUTZERNAME",
                "Next: pair a device with  sudo rentalars gateway pair USERNAME",
            )
        )

    def do_status(self, options: dict[str, Any]) -> None:
        """Show whether the link is up and what is paired."""
        link = GatewayLink.current()
        if link is None or not link.is_connected:
            self.say(
                t(
                    "Kein Gateway verbunden. Ohne Gateway erreichen die Apps den Server direkt, wie bisher.",
                    "No gateway connected. Without a gateway the apps reach the server directly, as before.",
                )
            )
            return
        self.say(f"{t('Gateway', 'Gateway')}:           {link.gateway_url}")
        self.say(
            f"{t('Zertifikat', 'Certificate')}:       {link.gateway_fingerprint or t('Zertifizierungsstelle', 'certificate authority')}"
        )
        self.say(
            f"{t('Server-Schlüssel', 'Server key')}:    {protocol.server_key_id(protocol.public_bytes(protocol.private_from_pem(link.e2e_key_pem())))}"
        )
        if link.last_poll_at:
            age = int((timezone.now() - link.last_poll_at).total_seconds())
            state = (
                t(f"verbunden (letzter Abruf vor {age} s)", f"connected (last poll {age} s ago)")
                if age < 90
                else t(
                    f"NICHT verbunden (letzter Abruf vor {age} s) – läuft der Dienst rentalars-gateway-link?",
                    f"NOT connected (last poll {age} s ago) – is the service rentalars-gateway-link running?",
                )
            )
        else:
            state = t(
                "noch kein Abruf – läuft der Dienst rentalars-gateway-link?",
                "no poll yet – is the service rentalars-gateway-link running?",
            )
        self.say(f"{t('Zustand', 'State')}:            {state}")
        if link.last_error:
            self.say(f"{t('letzter Fehler', 'last error')}:     {link.last_error}")
        active = GatewayDevice.objects.filter(revoked_at__isnull=True).count()
        revoked = GatewayDevice.objects.filter(revoked_at__isnull=False).count()
        offers = GatewayPairing.objects.filter(expires_at__gt=int(time.time())).count()
        self.say(
            f"{t('Geräte', 'Devices')}:            {active} {t('gekoppelt', 'paired')}, {revoked} {t('gesperrt', 'revoked')}; {offers} {t('offene Kopplungscodes', 'open pairing codes')}"
        )
        if link.move_url:
            self.say(f"{t('Umzug angekündigt', 'Move announced')}:  {link.move_url}")
        try:
            info = service.GatewayClient.for_link(link).info()
            self.say(
                f"{t('Gateway meldet', 'Gateway reports')}:   {t('Version', 'version')} {info.get('version', '?')}, {t('Server', 'server')} {t('verbunden' if info.get('server_online') else 'nicht verbunden', 'connected' if info.get('server_online') else 'not connected')}"
            )
        except (service.GatewayLinkError, OSError, ValueError) as error:
            self.say(f"{t('Gateway nicht erreichbar', 'Gateway not reachable')}: {error}")

    def do_pair(self, options: dict[str, Any]) -> None:
        """Make a pairing code for an account and print it as text and QR code."""
        from rentalars.accounts.models import User

        link = self.connected_link()
        user = User.objects.filter(username__iexact=options["username"]).first()
        if user is None:
            raise CommandError(t("Dieses Konto gibt es nicht.", "There is no such account."))
        try:
            offer = service.create_offer(
                link, user, device_name=options["name"], lifetime=max(1, min(options["minutes"], 10)) * 60,
                organisation=CompanyProfile.load().name,
            )  # fmt: skip
        except (service.GatewayLinkError, OSError) as error:
            raise CommandError(str(error)) from None
        code = offer.encode()
        minutes = max(1, (offer.expires - int(time.time())) // 60)
        self.say(
            t(
                f"Kopplungscode für {user.username} – gilt {minutes} Minuten und genau einmal:",
                f"Pairing code for {user.username} – valid for {minutes} minutes and once only:",
            )
        )
        self.say("")
        if not options["no_qr"]:
            try:
                import segno

                picture = io.StringIO()
                segno.make(code, error="l").terminal(out=picture, compact=True)
                self.say(picture.getvalue())
            except Exception:
                self.say(
                    t("(Der QR-Code konnte hier nicht angezeigt werden.)", "(The QR code could not be shown here.)")
                )
        self.say("")
        self.say(code)
        self.say("")
        self.say(
            t(
                "In der App: Installation hinzufügen → „Mit Gateway koppeln“ → Code scannen oder den Text einfügen.",
                "In the app: add an installation → “Pair with gateway” → scan the code or paste the text.",
            )
        )

    def do_devices(self, options: dict[str, Any]) -> None:
        """List the paired devices."""
        devices = GatewayDevice.objects.select_related("user").order_by("-paired_at")
        if not options["all"]:
            devices = devices.filter(revoked_at__isnull=True)
        rows = list(devices)
        if not rows:
            self.say(t("Keine Geräte.", "No devices."))
            return
        for device in rows:
            seen = timezone.localtime(device.last_seen_at).strftime("%d.%m.%Y %H:%M") if device.last_seen_at else "-"
            state = (
                t("gesperrt", "revoked")
                if device.revoked_at
                else (t("Konto inaktiv", "account inactive") if not device.user.is_active else t("aktiv", "active"))
            )
            self.say(
                f"{device.device_id[:12]}  {device.user.username:<20} {device.name:<24} {device.platform:<8} {t('zuletzt', 'last')} {seen}  {state}"
            )

    def do_revoke(self, options: dict[str, Any]) -> None:
        """Lock a device out at once."""
        device = self.find_device(options["device"])
        link = GatewayLink.current()
        service.revoke_device(link, device)
        self.say(
            t(
                f"Gesperrt: {device.name or 'Gerät'} von {device.user.username}. Die nächste Anfrage des Geräts endet mit einer Sperrmeldung.",
                f"Revoked: {device.name or 'device'} of {device.user.username}. Its next request ends with a revocation message.",
            )
        )

    def do_disconnect(self, options: dict[str, Any]) -> None:
        """Take the link down. Keys and devices stay, so that connecting again (even to a new gateway) is possible."""
        link = GatewayLink.current()
        if link is None or not link.is_connected:
            self.say(t("Es war kein Gateway verbunden.", "No gateway was connected."))
            return
        link.gateway_url = ""
        link.gateway_fingerprint = ""
        link.gateway_id = ""
        link.enrolled_at = None
        link.last_poll_at = None
        link.save()
        GatewayPairing.objects.all().delete()
        self.say(
            t(
                "Getrennt. Geräte und Schlüssel bleiben erhalten. Das Gateway selbst behält die Verknüpfung, bis dort 'rentalars-gateway enroll' erneut läuft.",
                "Disconnected. Devices and keys are kept. The gateway itself keeps the link until 'rentalars-gateway enroll' is run there again.",
            )
        )

    def do_announce_move(self, options: dict[str, Any]) -> None:
        """Announce a new address or certificate: every sealed answer carries it until it is cleared (GWS-015)."""
        link = self.connected_link()
        url = options["url"].rstrip("/")
        if not url.startswith("https://"):
            raise CommandError(
                t("Die neue Adresse muss mit https:// beginnen.", "The new address must start with https://.")
            )
        for value in (options["fingerprint"], options["next"]):
            cleaned = value.lower().replace(":", "")
            if value and (len(cleaned) != 64 or any(ch not in "0123456789abcdef" for ch in cleaned)):
                raise CommandError(
                    t(
                        "Ein Fingerabdruck sind 64 Hexzeichen (SHA-256 des Zertifikats).",
                        "A fingerprint is 64 hex characters (SHA-256 of the certificate).",
                    )
                )
        link.move_url = url
        link.move_fingerprint = options["fingerprint"].lower().replace(":", "")
        link.move_next_fingerprint = options["next"].lower().replace(":", "")
        link.move_since = timezone.now()
        link.save()
        self.say(
            t(
                "Angekündigt. Jede versiegelte Antwort enthält jetzt die neue Adresse; Apps übernehmen sie beim nächsten Abruf. Danach das neue Gateway einrichten: 'rentalars gateway connect …'. Wenn alle Geräte umgezogen sind: 'rentalars gateway announce-clear'.",
                "Announced. Every sealed answer now carries the new address; apps take it over at their next call. Then set up the new gateway: 'rentalars gateway connect …'. When all devices have moved: 'rentalars gateway announce-clear'.",
            )
        )

    def do_announce_clear(self, options: dict[str, Any]) -> None:
        """End the announcement."""
        link = GatewayLink.current()
        if link is not None:
            link.move_url = link.move_fingerprint = link.move_next_fingerprint = ""
            link.move_since = None
            link.save()
        self.say(t("Die Ankündigung ist beendet.", "The announcement is ended."))

    def do_rekey(self, options: dict[str, Any]) -> None:
        """A new end-to-end key. Every pairing becomes useless, so every device is removed (GWS-014)."""
        link = GatewayLink.current()
        if link is None or not link.e2e_key:
            raise CommandError(t("Es gibt noch keinen Schlüssel.", "There is no key yet."))
        if not options["yes"]:
            raise CommandError(
                t(
                    "Ein neuer Schlüssel entwertet ALLE Kopplungen: Jedes Gerät muss neu gekoppelt werden. Mit --yes bestätigen.",
                    "A new key makes ALL pairings useless: every device must be paired again. Confirm with --yes.",
                )
            )
        link.set_e2e_key_pem(protocol.private_to_pem(protocol.generate_private_key()))
        link.save()
        from rentalars.accounts.models import ApiToken

        # The tokens that were bound to the devices would otherwise be free for the direct way.
        for token in ApiToken.objects.filter(gateway_binding__isnull=False):
            token.revoke()
        GatewayTokenBinding.objects.all().delete()
        GatewayDevice.objects.all().delete()
        GatewayPairing.objects.all().delete()
        if link.is_connected:
            service.GatewayClient.for_link(link).push_registry()
        self.say(
            t(
                "Neuer Schlüssel erzeugt, alle Geräte entfernt. Bitte den Dienst neu starten: sudo systemctl restart rentalars-gateway-link",
                "New key created, all devices removed. Please restart the service: sudo systemctl restart rentalars-gateway-link",
            )
        )

    def do_is_configured(self, options: dict[str, Any]) -> None:
        """Exit status 0 if a gateway is connected, 1 otherwise (the condition of the service)."""
        try:
            link = GatewayLink.current()
        except Exception:  # the database is not there (yet): not "no gateway" – the unit must fail and be tried again
            sys.exit(UNKNOWN_STATUS)
        if link is None or not link.is_connected:
            sys.exit(1)

    def do_serve(self, options: dict[str, Any]) -> None:
        """The service: fetch the requests of the apps, carry them out, answer. Ends when the link changes or is taken down."""
        link = self.connected_link()
        config = settings.CONFIG.gateway
        if options["workers"]:
            config = type(config)(**{**config.__dict__, "workers": max(3, options["workers"])})
        executor = service.build_executor(config)
        server = service.ServerLink(
            link, config, executor, server_url=settings.RENTALARS_URL, organisation=CompanyProfile.load().name
        )
        stop = threading.Event()
        for number in (signal.SIGTERM, signal.SIGINT):
            signal.signal(number, lambda *_: stop.set())
        server.serve(stop)
        service.hold_registry(link.pk, stop)
        self.say(
            f"rentalars-gateway-link: {link.gateway_url}, {config.workers} {t('Abrufe gleichzeitig', 'polls at the same time')}"
        )
        started = (link.gateway_url, link.gateway_fingerprint, link.link_key, link.e2e_key)
        while not stop.wait(30):
            try:
                close_old_connections()
                current = GatewayLink.objects.filter(pk=link.pk).first()
            except Exception as error:  # e.g. the database restarts: keep serving, look again in 30 seconds
                service.log.warning("The link could not be read from the database: %s", error)
                continue
            if current is None or not current.is_connected:
                self.say(
                    t(
                        "Das Gateway wurde getrennt – der Dienst endet.",
                        "The gateway was disconnected – the service ends.",
                    )
                )
                return
            if (current.gateway_url, current.gateway_fingerprint, current.link_key, current.e2e_key) != started:
                self.say(
                    t(
                        "Die Verbindung wurde geändert – der Dienst startet neu.",
                        "The link was changed – the service restarts.",
                    )
                )
                sys.exit(RESTART_STATUS)
