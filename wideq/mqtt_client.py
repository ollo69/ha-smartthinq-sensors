import ssl
import json
import logging
import asyncio
import os
import tempfile
import certifi
import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from cryptography.x509.oid import NameOID

from .core_async import CoreAsync, Auth

_LOGGER = logging.getLogger(__name__)

# MQTT message types (from T20Service.java)
_TYPE_MONITORING = "monitoring"
_TYPE_DEVICE_UPDATED = "device_updated"
_TYPE_DEVICE_DELETED = "device_deleted"
_TYPE_DEVICE_REGISTERED = "device_registered"

# AWS IoT shadow keys (from T20Service.java: setTypeMonitoring / funcSyncRefreshMonitoring)
_DASHBOARD_REFRESH = "dashboardRefresh"
_FUNC_SYNC_REFRESH = "funcSyncRefresh"

# Reconnect settings
_RECONNECT_DELAY_BASE = 5      # seconds
_RECONNECT_DELAY_MAX = 300     # seconds (5 min cap)
_RECONNECT_MAX_ATTEMPTS = 10


class MQTTClient:
    """LG ThinQ AWS IoT Core MQTT Push Client."""

    def __init__(self, auth: Auth, core: CoreAsync):
        self._auth = auth
        self._core = core
        self._client = None
        self._callbacks = []
        self._refresh_callbacks = []   # called on dashboardRefresh / funcSyncRefresh
        self._subscriptions = []
        self._host = None
        self._port = 8883
        self._key_path = None
        self._cert_path = None
        self._reconnect_count = 0
        self._loop = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_callback(self, callback):
        """Register a callback that receives {key: value} state dicts."""
        self._callbacks.append(callback)

    def register_refresh_callback(self, callback):
        """Register a callback that receives a deviceId and triggers a full poll."""
        self._refresh_callbacks.append(callback)

    async def connect(self):
        self._loop = asyncio.get_event_loop()
        core = self._auth.gateway.core
        try:
            # ---- 1. Resolve MQTT broker address -------------------------
            gateway_info = await core.gateway_info()
            rti_uri = gateway_info.get("rtiUri", "")

            if rti_uri and not rti_uri.startswith("http"):
                rti_uri = "https://" + rti_uri
            rti_uri = rti_uri.rstrip("/")

            if ":47878" in rti_uri or ":8883" in rti_uri or not rti_uri.startswith("http"):
                mqtt_server = rti_uri.replace("https://", "").replace("http://", "")
            else:
                route_url = f"{rti_uri}/route"
                route_headers = core._thinq2_headers()
                route_headers.update({
                    "User-Agent": "okhttp/4.10.0",
                    "x-Device-Platform": "AOS",
                    "x-platform-type": "ANDROID/13",
                    "x-iot-sdk-type": "aws-sdk-android",
                })
                try:
                    async with core._get_session().get(route_url, headers=route_headers) as resp:
                        if resp.status == 404:
                            _LOGGER.info("MQTT /route not found. Falling back to polling.")
                            return False
                        resp.raise_for_status()
                        route_res = await resp.json()
                except Exception as e:
                    _LOGGER.info("MQTT /route failed: %s. Falling back to polling.", e)
                    return False

                result = route_res.get("result", route_res)
                mqtt_server = result.get("mqttServer", "")

            for prefix in ("tls://", "ssl://", "tcp://"):
                if mqtt_server.startswith(prefix):
                    mqtt_server = mqtt_server[len(prefix):]

            parts = mqtt_server.split(":")
            self._host = parts[0]
            self._port = int(parts[1]) if len(parts) > 1 else 8883

            # ---- 2. Generate RSA keypair + CSR --------------------------
            # Subject matches what AmazonUXUtil.generateCSR() uses in the APK:
            #   CN=AWS IoT Certificate, O=Amazon
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            csr = (
                x509.CertificateSigningRequestBuilder()
                .subject_name(x509.Name([
                    x509.NameAttribute(NameOID.COMMON_NAME, "AWS IoT Certificate"),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Amazon"),
                ]))
                .sign(key, hashes.SHA256())
            )
            csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")

            # ---- 3. Fetch certificate from LG ---------------------------
            thinq2_base = self._auth.gateway.thinq2_uri.rstrip("/")
            cert_url = f"{thinq2_base}/service/users/client/certificate"
            cert_headers = core._thinq2_headers(
                client_id=None,
                access_token=self._auth.access_token,
                user_number=self._auth.user_number,
                country=core._country,
                language=core._language,
                security_key=False,
            )
            try:
                async with core._get_session().post(
                    url=cert_url, headers=cert_headers, json={"csr": csr_pem}
                ) as resp:
                    resp_text = await resp.text()
                    try:
                        cert_res = json.loads(resp_text)
                    except json.JSONDecodeError:
                        cert_res = {}

                    if cert_res.get("resultCode") == "0101":
                        _LOGGER.info("MQTT not supported for this account. Falling back to polling.")
                        return False

                    if resp.status != 200 or cert_res.get("resultCode", "0000") != "0000":
                        _LOGGER.error("MQTT cert fetch failed: HTTP %s  %s", resp.status, resp_text)
                        return False

                    cert_res = cert_res.get("result", cert_res)
            except Exception as e:
                _LOGGER.error("MQTT cert request failed: %s", e)
                return False

            certificate_pem = cert_res.get("certificatePem")
            subscriptions = cert_res.get("subscriptions", [])

            if not certificate_pem:
                _LOGGER.error("Empty certificatePem in response: %s", cert_res)
                return False

            # ---- 4. Write temp certs (cleaned up on disconnect) ---------
            self._cleanup_temp_files()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as f:
                f.write(key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.TraditionalOpenSSL,
                    serialization.NoEncryption(),
                ))
                self._key_path = f.name

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as f:
                f.write(certificate_pem.encode("utf-8"))
                self._cert_path = f.name

            # ---- 5. Create paho client ----------------------------------
            try:
                self._client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                    client_id=self._core.client_id,
                )
            except AttributeError:
                self._client = mqtt.Client(client_id=self._core.client_id)

            self._client.tls_set(
                ca_certs=certifi.where(),
                certfile=self._cert_path,
                keyfile=self._key_path,
                tls_version=ssl.PROTOCOL_TLSv1_2,
            )
            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect

            self._subscriptions = subscriptions
            self._reconnect_count = 0

            _LOGGER.debug("Connecting to MQTT %s:%s", self._host, self._port)
            self._client.connect_async(self._host, self._port, keepalive=60)
            self._client.loop_start()
            return True

        except Exception as e:
            _LOGGER.error("MQTT connect failed: %s", e)
            return False

    def disconnect(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None
        self._cleanup_temp_files()

    # ------------------------------------------------------------------
    # Paho callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            _LOGGER.info("MQTT connected")
            self._reconnect_count = 0
            for topic in self._subscriptions:
                _LOGGER.debug("Subscribing: %s", topic)
                client.subscribe(topic)
        else:
            _LOGGER.warning("MQTT connect failed, rc=%s", rc)

    def _on_message(self, client, userdata, msg):
        """
        Parse LG ThinQ MQTT messages.

        Official message structure (from T20Service.java):
          {
            "type": "monitoring",
            "deviceId": "<id>",
            "data": {
              "state": {
                "reported": { "<airState.key>": "<value>", ... },
                "desired":  { "dashboardRefresh": "true" }   ← optional control flag
              }
            }
          }
        """
        try:
            raw = json.loads(msg.payload.decode("utf-8"))
        except Exception as e:
            _LOGGER.debug("MQTT payload parse error: %s", e)
            return

        msg_type = raw.get("type")
        device_id = raw.get("deviceId")

        # Extract deviceId from topic as fallback
        if not device_id:
            parts = msg.topic.split("/")
            for i, part in enumerate(parts):
                if part in ("devices", "things") and i + 1 < len(parts):
                    device_id = parts[i + 1]
                    break

        # Only handle monitoring messages (skip device_updated, device_deleted, etc.)
        if msg_type != _TYPE_MONITORING:
            _LOGGER.debug("Ignoring MQTT message type: %s", msg_type)
            return

        if not device_id:
            _LOGGER.debug("MQTT monitoring message with no deviceId, skipping")
            return

        data_block = raw.get("data", {})
        state_block = data_block.get("state", {})

        # Check for control flags in 'desired' (from setTypeMonitoring / funcSyncRefreshMonitoring)
        desired = state_block.get("desired", {})
        if desired.get(_DASHBOARD_REFRESH) == "true" or desired.get(_FUNC_SYNC_REFRESH) == "true":
            _LOGGER.debug("MQTT %s flag for %s → triggering full refresh",
                          _DASHBOARD_REFRESH if desired.get(_DASHBOARD_REFRESH) == "true" else _FUNC_SYNC_REFRESH,
                          device_id)
            for cb in self._refresh_callbacks:
                cb(device_id)
            return

        # Normal state update
        reported = state_block.get("reported", {})
        if not reported:
            _LOGGER.debug("MQTT monitoring message for %s has empty reported state", device_id)
            return

        reported["deviceId"] = device_id
        _LOGGER.debug("MQTT state update for %s: %s", device_id, reported)
        for cb in self._callbacks:
            cb(reported)

    def _on_disconnect(self, client, userdata, rc):
        _LOGGER.info("MQTT disconnected, rc=%s", rc)
        if rc != 0 and self._loop:
            self._loop.call_soon_threadsafe(
                asyncio.ensure_future,
                self._async_reconnect(),
            )

    # ------------------------------------------------------------------
    # Reconnect with exponential backoff
    # ------------------------------------------------------------------

    async def _async_reconnect(self):
        if self._reconnect_count >= _RECONNECT_MAX_ATTEMPTS:
            _LOGGER.error("MQTT max reconnect attempts reached. Giving up.")
            return

        delay = min(
            _RECONNECT_DELAY_BASE * (2 ** self._reconnect_count),
            _RECONNECT_DELAY_MAX,
        )
        self._reconnect_count += 1
        _LOGGER.info("MQTT reconnecting in %ss (attempt %s/%s)…",
                     delay, self._reconnect_count, _RECONNECT_MAX_ATTEMPTS)
        await asyncio.sleep(delay)

        try:
            if self._client:
                self._client.reconnect()
            else:
                await self.connect()
        except Exception as e:
            _LOGGER.warning("MQTT reconnect failed: %s", e)
            await self._async_reconnect()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cleanup_temp_files(self):
        for path in (self._key_path, self._cert_path):
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except OSError:
                    pass
        self._key_path = None
        self._cert_path = None
