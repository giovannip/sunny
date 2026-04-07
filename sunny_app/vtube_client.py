from __future__ import annotations

import errno
import json
import threading
import uuid
from typing import Any, Callable, Optional, TypeVar

import websocket

from sunny_app.config import VTubeConfig

T = TypeVar("T")


class VTubeClient:
    """VTube Studio API pública 1.0 via WebSocket (websocket-client).

    Operações serializadas com lock; reconecta e tenta de novo uma vez em erros de conexão (ex.: WinError 10053).
    """

    def __init__(self, cfg: VTubeConfig) -> None:
        self._cfg = cfg
        self._ws: Optional[websocket.WebSocket] = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        with self._lock:
            self._close_socket_unlocked()
            self._open_and_auth_unlocked()

    def trigger_hotkey(self, hotkey_id: str) -> None:
        if not hotkey_id:
            return

        def op() -> None:
            self._request(
                "HotkeyTriggerRequest",
                {"hotkeyID": hotkey_id},
            )
            resp = self._recv_json()
            if resp.get("messageType") == "APIError":
                raise RuntimeError(resp.get("data") or resp)

        self._with_connection_retry(op)

    def inject_mouth_value(self, parameter_id: str, value: float) -> None:
        if not parameter_id:
            return

        def op() -> None:
            self._request(
                "InjectParameterDataRequest",
                {
                    "faceFound": True,
                    "mode": "set",
                    "parameterValues": [{"id": parameter_id, "value": float(value)}],
                },
            )
            resp = self._recv_json()
            if resp.get("messageType") == "APIError":
                raise RuntimeError(resp.get("data") or resp)

        self._with_connection_retry(op)

    def close(self) -> None:
        with self._lock:
            self._close_socket_unlocked()

    def _close_socket_unlocked(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass
            finally:
                self._ws = None

    def _open_and_auth_unlocked(self) -> None:
        self._ws = websocket.create_connection(self._cfg.ws_url, timeout=15)
        self._request(
            "AuthenticationRequest",
            {
                "pluginName": self._cfg.plugin_name,
                "pluginDeveloper": self._cfg.plugin_developer,
                "authenticationToken": self._cfg.auth_token,
            },
        )
        resp = self._recv_json()
        if resp.get("messageType") != "AuthenticationResponse":
            raise RuntimeError(f"Unexpected auth message: {resp}")
        data = resp.get("data") or {}
        if not data.get("authenticated"):
            raise RuntimeError(f"VTube Studio authentication failed: {data}")

    def _with_connection_retry(self, op: Callable[[], T]) -> T:
        with self._lock:
            if self._ws is None:
                raise RuntimeError("WebSocket not connected")
            for attempt in range(2):
                try:
                    return op()
                except Exception as exc:
                    if attempt == 0 and _is_recoverable_connection_error(exc):
                        self._close_socket_unlocked()
                        try:
                            self._open_and_auth_unlocked()
                        except Exception:
                            raise exc from None
                        continue
                    raise

    def _request(self, message_type: str, data: dict[str, Any]) -> str:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        req_id = str(uuid.uuid4())
        payload = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": req_id,
            "messageType": message_type,
            "data": data,
        }
        self._ws.send(json.dumps(payload))
        return req_id

    def _recv_json(self) -> dict[str, Any]:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        raw = self._ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)


def _is_recoverable_connection_error(exc: BaseException) -> bool:
    """Erros em que reconectar costuma resolver (10053, socket fechado etc.)."""
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    if isinstance(exc, OSError):
        we = getattr(exc, "winerror", None)
        if we in (10053, 10054):
            return True
        en = getattr(exc, "errno", None)
        if en in (errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED):
            return True
    try:
        from websocket import WebSocketConnectionClosedException
    except ImportError:
        WebSocketConnectionClosedException = ()  # type: ignore[misc,assignment]
    if isinstance(exc, WebSocketConnectionClosedException):
        return True
    name = type(exc).__name__
    if "ConnectionClosed" in name:
        return True
    return False
