# Rentalars Gateway: reaching the apps from the internet

The apps (Android, iOS) talk to Rentalars in **two ways**:

| Way | When | Who sits in between |
|---|---|---|
| **direct** | in the company network, over a VPN, or when you put the server on the internet yourself | nobody – the app speaks HTTPS to the server (as before) |
| **through the gateway** | on the road, from the internet, without the server being reachable from outside | the **Rentalars Gateway** on a machine in the DMZ or in a hoster's network |

Both ways work **side by side**. Without a gateway nothing changes: whoever
reaches the server directly uses it as before. The apps choose the way **when
signing in**: "Direct" or "Through gateway". Each installation of the app uses
one of the two and never switches silently; whoever moves between the company
network and the internet signs in with the fitting way.

## How it fits together

```
app ──HTTPS──▶ gateway (DMZ) ◀──HTTPS── link service ──▶ Rentalars (gunicorn socket)
```

- The gateway **never opens a connection** to the server. The link service
  (`rentalars-gateway-link`) on the server keeps asking the gateway for new
  requests (long poll). The firewall of the internal network therefore needs
  **no inbound rule**.
- The content of every request is **end-to-end encrypted** between app and
  server (protocol RGW1, ECDH P-256 + AES-256-GCM). The gateway sees **which
  device** asks and **how much**, never what.
- Every device has a key of its own and is **paired** and, if needed,
  **revoked** one by one. Unknown devices get no further than the gateway.
- Only the **API** (`/api/v1/…`) is reachable through the gateway – not the
  web interface, not the administration (`/admin/`), no static files.

The gateway itself (installation, operation, protocol) is a program of its
own; its documentation lies in its folder (`docs/`).

## Setting up

1. **Install and start the gateway** (see its documentation). It prints a
   **connection text** that starts with `RGWL1:`.
2. **Connect on the Rentalars server:**

   ```
   sudo rentalars gateway connect 'RGWL1:…'
   ```

   This creates the keys of this installation (stored encrypted in the
   database, so in every backup), registers the server at the gateway and
   switches the service `rentalars-gateway-link` on.
3. **Check:**

   ```
   sudo rentalars gateway status
   ```

   It shows the address and fingerprint of the gateway, whether the last poll
   worked and how many devices are paired.

The gateway needs a reachable HTTPS port. If it has a self-made certificate,
the connection text carries its fingerprint: the installation then trusts
exactly that certificate.

## Pairing a device

Each device and user account gets a **one-off pairing code**, valid for ten
minutes. An administrator makes it **in the browser**, without
SSH: **Settings → Gateway → "Pair an app"**. Choose the account (the app has
its rights), optionally a name for the device and how long the code is valid
(1, 5 or 10 minutes), then "Make a pairing code". The page shows the QR code
and the same content as text; it is gone when you leave the page. Pairing and
locking out need the right to delete in the settings and are written to the
change log. On the server it still works with

```
sudo rentalars gateway pair anna --name "Anna's phone"
```

Both ways show a QR code and the same content as text (`RGW1:…`). In the
app choose **"Through gateway"** on the sign-in screen and enter the code: iOS
scans the QR code with the camera, Android has no scanner of its own – there
paste the text copied from a scanner app or a mail. The server's address is in
the code. Afterwards the app signs in as usual with user name, password and,
if needed, authenticator code. The pairing belongs to phone and server and
survives signing out.

Important:

- A device belongs to **one account**. Through that device one can sign in
  only as that account; any other user name is refused.
- An **API token** created through a device **works only through that
  device**. On the direct way it is worthless. Tokens created on the direct
  way are not touched.
- When an account is deactivated, its devices are locked at once.

## Managing devices

**Settings → Gateway** lists the paired devices (account, name, paired on, last used) and locks one out with "Lock out"; locked-out ones are listed below. `rekey`, `disconnect` and `connect` remain commands on the server.

| Command | Effect |
|---|---|
| `sudo rentalars gateway devices` | paired devices (with `--all` also revoked ones) |
| `sudo rentalars gateway revoke ID` | revoke a device (the first characters of the ID are enough); the gateway knows at once |
| `sudo rentalars gateway rekey --yes` | new key of the installation: **all** pairings become invalid, all tokens created through devices are revoked, every device must be paired again |
| `sudo rentalars gateway disconnect` | switch the link service off and forget the gateway; keys and devices stay, so a later `connect` keeps the same pairings |

## Moving the gateway

When the gateway moves to another address or gets a new certificate, announce
it beforehand – the apps take it over with the next answer by themselves:

```
sudo rentalars gateway announce-move --url https://new.example.de:8799 --fingerprint AB:CD:… [--next FINGERPRINT]
sudo rentalars gateway announce-clear     # when every device has switched
```

## Settings

Everything needed is in the database. Optionally `/etc/rentalars/rentalars.conf`
has a section `[gateway]` (see `rentalars.conf.example`): `local` (where the
link service carries out the requests – on a server the gunicorn socket),
`workers`, `time_window`, `max_response_mib`, `call_timeout`.

## Limits

- Only API calls go through the gateway. Functions that open a web page of
  the server in the app (PDF, XML, documents in the browser) do not work there;
  the app says so (on the company network or a VPN it opens the address anyway).
- Answers are limited to 12 MiB; larger files are fetched on the direct way.
- The clock of the device may be off by three minutes at most; the app
  corrects itself by the server's time, which every answer carries.

## When something does not work

| Observation | Cause and remedy |
|---|---|
| `gateway status`: "server not connected" | The service is not running: `systemctl status rentalars-gateway-link`, log with `journalctl -u rentalars-gateway-link` |
| Self-check, group "Gateway", error "Not connected" | As with `gateway status`: the service `rentalars-gateway-link` is not running or does not reach the gateway; the last error is shown below it |
| Pairing fails with "expired" | The code is valid for ten minutes and exactly once; create a new one |
| App says "device no longer paired" | The device was revoked or `rekey` ran; pair again |
| App says "clock differs" | Set the device's clock (switch on automatic time) |
