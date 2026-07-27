"""RoboCasa env server — hosts the raw robosuite env in a subprocess, exposes basic calls via RPC."""
import argparse
import inspect
import os
import re
import numpy as np
import robosuite
import robocasa  # noqa: F401 — registers robocasa envs
import robosuite.utils.camera_utils as CU
from robosuite.controllers import load_composite_controller_config
from robosuite.controllers.composite.composite_controller import HybridMobileBase

from robots.robocasa.env_utils import (
    DEFAULT_CAMS,
    _split_kwargs,
    _to_numpy_tree,
)
from rpent.utils.logging import get_logger
from rpent.utils.rpc import RpcFacade

logger = get_logger("driver")


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class RoboCasaEnvFacade(RpcFacade):
    """Wraps the raw robosuite env and exposes ONLY basic calls via RPC."""

    def __init__(self, env_name, split="target", seed=0, camera_h=256, camera_w=256,
                 cameras=None, use_camera_obs=False):
        super().__init__()
        self.cameras = list(cameras) if cameras else list(DEFAULT_CAMS)
        self.camera_h, self.camera_w = camera_h, camera_w
        self._last_obs = None
        self._terminated = False

        controller_config = load_composite_controller_config(controller=None, robot="PandaOmron")
        env_kwargs = dict(
            env_name=env_name,
            robots="PandaOmron",
            controller_configs=controller_config,
            camera_names=self.cameras,
            camera_widths=camera_w,
            camera_heights=camera_h,
            has_renderer=False,
            has_offscreen_renderer=True,
            ignore_done=True,
            use_object_obs=True,
            use_camera_obs=use_camera_obs,   # off -> no per-step render (EGL-safe OSC loops)
            camera_depths=False,             # depth rendered on demand
            seed=seed,
            **_split_kwargs(split),
        )
        self.env = robosuite.make(**env_kwargs)

    # ---- RPC dispatch ----
    def _dispatch(self, method: str, args: tuple, kwargs: dict):
        """Route ``env.*`` calls to the matching facade method."""
        if method.startswith("env."):
            attr = method[len("env."):]
            try:
                return _to_numpy_tree(getattr(self, attr)(*args, **kwargs))
            except Exception as e:
                logger.warning("run method %s failed: %s", method, e)
                raise
        raise ValueError(f"unknown RPC method: {method!r}")

    # ---- lifecycle ----
    def reset(self):
        # RLDX_RESET_SEED=<episode_seed> -> reproduce the EXACT scene the fullshot eval
        # generated for that episode, seeded the SAME way as the eval's VideoRecordingWrapper
        # (random.seed + np.random.seed + robosuite env.rng/seed) BEFORE reset. Lets the
        # hybrid run on the IDENTICAL reset layouts fullshot was scored on (true paired
        # comparison). The eval formula: episode_seed = (run_seed + env_idx)*100000 + episode_id.
        rs_env = os.environ.get("RLDX_RESET_SEED")
        if rs_env:
            import random
            sd = int(rs_env)
            random.seed(sd)
            np.random.seed(sd)
            if hasattr(self.env, "seed"):
                self.env.seed = sd
            if hasattr(self.env, "rng"):
                self.env.rng = np.random.default_rng(sd)
        self._last_obs = self.env.reset()
        self._terminated = False
        return self._last_obs

    def step(self, flat_action):
        """flat_action: np.ndarray[12] = [eef_pos(3), eef_rot(3), gripper(1),
        base_motion(4), control_mode(1)] in the PandaOmron composite layout."""
        a = np.asarray(flat_action, dtype=np.float64).reshape(-1)
        assert a.shape[0] == self.env.action_dim, (
            f"action dim {a.shape[0]} != env.action_dim {self.env.action_dim}")
        obs, reward, done, info = self.env.step(a)
        self._last_obs = obs
        if self.env._check_success():
            self._terminated = True
        return obs, reward, done, info

    def check_success(self):
        return bool(self.env._check_success())

    def raw_obs(self):
        return self._last_obs

    def render_raw(self, cam, h, w, depth):
        """sim.render in ROBOSUITE-NATIVE orientation (matches the camera
        transform matrices). rgb uint8 HxWx3, depth metric HxW."""
        out = self.env.sim.render(width=w, height=h, camera_name=cam, depth=depth)
        if depth:
            rgb, d = out
            # Sanitize the raw OpenGL normalized depth into [0,1]: replace NaN/inf
            # (degenerate camera pose) then clip numerical overshoot. Otherwise an
            # assertion inside get_real_depth_map crashes the whole driver process.
            d = np.nan_to_num(d, nan=1.0, posinf=1.0, neginf=0.0)
            d = np.clip(d, 0.0, 1.0)
            if d.ndim == 3:
                depth = CU.get_real_depth_map(self.env.sim, d)[..., 0]
            else:
                depth = CU.get_real_depth_map(self.env.sim, d[..., None])[..., 0]
            return rgb, depth
        return out

    def get_camera_meta(self, camera_name, height=None, width=None):
        K = CU.get_camera_intrinsic_matrix(self.env.sim, camera_name, height, width)
        Ext = CU.get_camera_extrinsic_matrix(self.env.sim, camera_name)  # cam->world
        m = self.env.sim.model
        extent = m.stat.extent
        return {
            "camera_name": camera_name,
            "height": height, "width": width,
            "intrinsic": np.asarray(K, dtype=np.float64).tolist(),
            "extrinsic_cam2world": np.asarray(Ext, dtype=np.float64).tolist(),
            "depth_near": float(m.vis.map.znear * extent),
            "depth_far": float(m.vis.map.zfar * extent),
        }

    def get_camera_transform(self, camera_name, height=None, width=None):
        T = CU.get_camera_transform_matrix(self.env.sim, camera_name, height, width)
        return np.linalg.inv(T)  # T_p2w

    def get_ep_meta(self):
        return self.env.get_ep_meta()

    def get_env_meta(self):
        return {"camera_h": self.camera_h, "camera_w": self.camera_w}

    def get_terminated(self):
        return self._terminated or self.check_success()

    def get_action_dim(self):
        return self.env.action_dim

    def grasp_contact(self):
        """Check if the gripper is currently contacting a task object."""
        try:
            robo = self.env                           # robosuite Kitchen env
            grip = robo.robots[0].gripper             # {"right": GripperModel}
            for name, obj in robo.objects.items():
                try:
                    if robo._check_grasp(grip, obj):
                        return True, name
                except Exception:
                    continue
        except Exception:
            pass
        return False, None

    def reassemble_env_action(self, unmap_result):
        """Reassemble the unmap result into a flat action using the env's robots."""
        env_action = []
        for robot in self.env.robots:
            cc = robot.composite_controller
            pf = robot.robot_model.naming_prefix
            a = np.zeros(cc.action_limits[0].shape)
            for part_name in cc.part_controllers:
                s, e = cc._action_split_indexes[part_name]
                a[s:e] = unmap_result.pop(f"{pf}{part_name}")
            if isinstance(cc, HybridMobileBase):
                a[-1] = unmap_result.pop(f"{pf}base_mode")
            env_action.append(a)
        return np.concatenate(env_action)

    def get_success_criteria_text(self):
        """Return the success_criteria.md text for this task."""
        env = self.env
        out = []
        try:
            src = inspect.getsource(type(env)._check_success)
            out.append("# SUCCESS CONDITION for this task (env._check_success)\n"
                       "# You must make this return True. Object positions are NOT given —\n"
                       "# localize every named object/fixture from the camera+world maps.\n\n"
                       + src)
            try:
                import robocasa.utils.object_utils as OU
                for fn in sorted(set(re.findall(r'OU\.(\w+)\(', src))):
                    f = getattr(OU, fn, None)
                    if f is not None:
                        try:
                            out.append("## helper OU.%s\n%s" % (fn, inspect.getsource(f)))
                        except Exception:
                            pass
            except Exception:
                pass
            for fix, meth in sorted(set(re.findall(r'self\.(\w+)\.(\w+)\(', src))):
                obj = getattr(env, fix, None)
                if obj is not None and hasattr(type(obj), meth):
                    try:
                        out.append("## %s.%s\n%s" % (fix, meth, inspect.getsource(getattr(type(obj), meth))))
                    except Exception:
                        pass
        except Exception as ex:
            out.append("(_check_success extraction failed: %s)" % ex)
        return "\n\n".join(out)[:9000]

    def get_task_progress(self):
        """Return the progress dict for this task."""
        env = self.env
        prog = {}
        code = type(env)._check_success.__code__
        try:
            src = inspect.getsource(type(env)._check_success)
            # capture both `self.attr` AND dotted `self.fixture._attr` paths used in the
            # success check (e.g. self.coffee_machine._turned_on) — a bare-attr regex
            # would only grab "coffee_machine" (the fixture object) and miss the real
            # gating flag. Resolve each dotted path to its live scalar/bool value.
            for path in sorted(set(re.findall(r"self\.([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)", src))):
                obj = env
                ok = True
                for part in path.split("."):
                    obj = getattr(obj, part, None)
                    if obj is None:
                        ok = False
                        break
                if not ok:
                    continue
                key = path.replace(".", "_")
                if isinstance(obj, (bool, np.bool_)):
                    prog[key] = bool(obj)
                elif isinstance(obj, (int, np.integer)):
                    prog[key] = int(obj)
                elif isinstance(obj, (float, np.floating)):
                    prog[key] = round(float(obj), 4)
        except Exception:
            pass
        # trace ONE read-only call of _check_success; grab its return-frame locals
        captured = {}
        def _tracer(frame, event, arg):
            if event == "call" and frame.f_code is code:
                def _local(f, e, a):
                    if e == "return":
                        captured.update(f.f_locals)
                    return _local
                return _local
            return None
        import sys as _sys
        old = _sys.gettrace()
        try:
            _sys.settrace(_tracer)
            env._check_success()
        except Exception:
            pass
        finally:
            _sys.settrace(old)
        for k, v in captured.items():
            if k == "self" or k in prog:
                continue
            if isinstance(v, (bool, np.bool_)):
                prog[k] = bool(v)
            elif isinstance(v, (int, np.integer)):
                prog[k] = int(v)
            elif isinstance(v, (float, np.floating)):
                prog[k] = round(float(v), 4)
        return prog

    def close(self):
        try:
            self.env.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--env", dest="env_name", default="OpenDrawer")
    p.add_argument("--split", default="target")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--transport_host", type=str, default="127.0.0.1")
    p.add_argument("--transport_port", type=int, default=0)
    args = p.parse_args()

    env_facade = RoboCasaEnvFacade(args.env_name, split=args.split, seed=args.seed)
    env_facade.serve(
        transport="socket",
        host=args.transport_host,
        port=args.transport_port,
    )


if __name__ == "__main__":
    main()
