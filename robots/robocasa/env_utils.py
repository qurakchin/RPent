"""RoboCasa env server utilities — constants, helpers, and torch-to-numpy conversion."""
from rpent.utils.logging import get_logger

logger = get_logger("driver")

DEFAULT_CAMS = [
    "robot0_agentview_left",
    "robot0_agentview_right",
    "robot0_eye_in_hand",
]


def _split_kwargs(split):
    """Replicate robocasa.utils.env_utils.create_env's split -> layout logic."""
    if split == "target":
        return dict(obj_instance_split="target", layout_ids=None, style_ids=None,
                    layout_and_style_ids=list(zip(range(1, 11), range(1, 11))))
    if split == "pretrain":
        return dict(obj_instance_split="pretrain", layout_ids=-2, style_ids=-2,
                    layout_and_style_ids=None)
    if split == "all":
        return dict(obj_instance_split=None, layout_ids=-3, style_ids=-3,
                    layout_and_style_ids=None)
    if split is None:
        return dict(obj_instance_split=None, layout_ids=None, style_ids=None,
                    layout_and_style_ids=None)
    raise ValueError('split must be {None,"all","pretrain","target"}')


# ---------------------------------------------------------------------------
# torch -> numpy conversion
# ---------------------------------------------------------------------------

try:
    import torch as _torch
except ImportError:
    _torch = None  # type: ignore[assignment]


def _to_numpy_tree(x):
    """Recursively convert torch tensors to CPU numpy arrays so the result
    pickles cleanly across the agent/driver wire."""
    if _torch is not None and isinstance(x, _torch.Tensor):
        return x.detach().cpu().numpy()
    if isinstance(x, dict):
        return {k: _to_numpy_tree(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_to_numpy_tree(v) for v in x]
    if isinstance(x, tuple):
        return tuple(_to_numpy_tree(v) for v in x)
    return x
