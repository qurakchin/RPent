"""RoboCasa CLI entrypoint — spawns env server, creates client, runs driver."""
import os, sys, socket, subprocess

from robots.robocasa.interactive_driver import RoboCasaDriver
from robots.robocasa.toolkit import RoboCasaToolkit
from robots.robocasa import _add_cli_args, _init_runtime

def main():
    import argparse
    ap = argparse.ArgumentParser()
    _add_cli_args(ap, False)
    args = ap.parse_args()

    daemons, primitives_kwargs = _init_runtime(args, args.workdir)

    # Run the driver with the remote env + VLA
    toolkit = RoboCasaToolkit(**primitives_kwargs)
    driver = RoboCasaDriver(toolkit, workdir=args.workdir)
    driver.run()


if __name__ == "__main__":
    main()
