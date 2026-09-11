"""
Prophet needs a compiled cmdstan backend (it shells out to g++/make to
compile/verify its Stan model). On Linux (the actual Railway/Render
deployment target — Ch4 §4.1 Deployment View) this just needs
`build-essential` in the deploy image. On a Windows dev machine there's no
C++ toolchain by default, so cmdstanpy's own installer
(`python -m cmdstanpy.install_cxx_toolchain`) fetches a minimal RTools/MinGW
one under ~/.cmdstan/RTools40 — but that directory only lands on PATH for
*new* processes launched after the one that ran the installer, which a
long-running IDE/terminal session won't pick up until it's restarted.

This makes every process that imports this module self-sufficient instead
of depending on the user restarting their terminal: it's a no-op everywhere
except Windows-with-the-local-RTools-directory-present.
"""
import os
import sys
from pathlib import Path


def ensure_windows_cmdstan_toolchain() -> None:
    if sys.platform != "win32":
        return

    rtools_root = Path.home() / ".cmdstan" / "RTools40"
    bin_dirs = [rtools_root / "mingw64" / "bin", rtools_root / "usr" / "bin"]
    existing_bins = [str(d) for d in bin_dirs if d.is_dir()]
    if not existing_bins:
        return  # toolchain not installed here — let Prophet fail with its own error

    current_path = os.environ.get("PATH", "")
    missing = [d for d in existing_bins if d not in current_path]
    if missing:
        os.environ["PATH"] = os.pathsep.join([*missing, current_path])
