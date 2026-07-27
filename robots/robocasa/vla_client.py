"""RoboCasa VLA client — thin RPC layer over the VLA server."""
from __future__ import annotations

import time

from rpent.utils.rpc import RpcClient

_TIMEOUT_S = {
    "default": 30.0,
    "predict": 120.0,
}


class RoboCasaVLAClient:
    def __init__(self, client: RpcClient, connect_retry_s: float = 300.0):
        self._client = client
        self.wait_for_healthz(timeout_s=connect_retry_s)

    def wait_for_healthz(self, *, timeout_s: float = 300.0,
                         poll_timeout_s: float = 5.0) -> None:
        """Block until the VLA server responds to ``healthz`` or *timeout_s* elapses.

        Each probe uses ``poll_timeout_s`` as the RPC timeout — the connection
        failure/refusal itself acts as the loop cadence; no extra sleep.
        """
        deadline = time.monotonic() + timeout_s
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self._client.call("env.healthz",
                    timeout_s=min(poll_timeout_s, max(0.1, deadline - time.monotonic())))
                return
            except (ConnectionRefusedError, ConnectionError, OSError) as exc:
                last_err = exc
        raise ConnectionError(
            f"Could not connect to VLA server after {timeout_s}s: {last_err}"
        ) from last_err

    def get_modality_config(self) -> dict:
        return self._client.call("env.get_modality_config", timeout_s=_TIMEOUT_S["default"])

    def predict(self, obs_dict: dict, options: dict) -> dict:
        """Run inference; returns raw actions dict.

        Actions are numpy arrays, already converted by ``_to_numpy_tree`` on the server.
        """
        return self._client.call("env.predict", args=(obs_dict, options),
                                 timeout_s=_TIMEOUT_S["predict"])

    def reset_session(self, session_id: str) -> dict:
        return self._client.call("env.reset_session", args=(session_id,),
                                 timeout_s=_TIMEOUT_S["default"])
