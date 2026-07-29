"""RoboCasa VLA server — loads RLDX model and exposes inference calls via RPC."""
import argparse

import numpy as np
from robots.robocasa.env_utils import _to_numpy_tree
from rpent.utils.logging import get_logger
from rpent.utils.rpc import RpcFacade

logger = get_logger("driver")


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class RoboCasaVLAServer(RpcFacade):
    """Loads RLDX model and exposes inference-only RPC methods."""

    def __init__(self, model_path):
        super().__init__()
        from rldx.data.embodiment_tags import EmbodimentTag
        from rldx.eval.rollout_policy import create_rldx_sim_policy

        self.policy = create_rldx_sim_policy(
            model_path, EmbodimentTag.GENERAL_EMBODIMENT, "", None
        )
        mod = self.policy.get_modality_config()
        self._vdi = np.asarray(mod["video"].delta_indices)
        self._hist_maxlen = int(self._vdi.max() - self._vdi.min()) + 2
        print(
            f"[vla_server] policy loaded; video_delta_indices={self._vdi.tolist()} "
            f"hist_maxlen={self._hist_maxlen}",
            flush=True,
        )

    # ---- RPC methods (exposed via env.* dispatch) ----

    def _dispatch(self, method: str, args: tuple, kwargs: dict):
        """Route ``env.*`` calls to the matching VLA method."""
        if method.startswith("env."):
            attr = method[len("env."):]
            try:
                return _to_numpy_tree(getattr(self, attr)(*args, **kwargs))
            except Exception as e:
                logger.warning("run method %s failed: %s", method, e)
                raise
        raise ValueError(f"unknown RPC method: {method!r}")

    def get_modality_config(self):
        return {
            "video_delta_indices": self._vdi.tolist(),
            "hist_maxlen": self._hist_maxlen,
        }

    def predict(self, obs_dict, options):
        actions, info = self.policy.get_action(obs_dict, options=options)
        return actions

    def reset_session(self, session_id):
        self.policy.reset({"session_ids": [session_id]})
        return {"ok": True}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--transport", choices=["socket", "http"], default="http")
    p.add_argument("--host", type=str, default="127.0.0.1")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--model-path", required=True, help="RLDX checkpoint path")
    args = p.parse_args()

    vla = RoboCasaVLAServer(args.model_path)
    vla.serve(
        transport=args.transport,
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
