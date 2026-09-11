"""
One-time setup for Prophet on a Windows dev machine. Not needed on the
Linux deployment target (Railway/Render) — there, `pip install prophet`
just works given build-essential in the image.

What this fixes: Prophet's Windows wheel ships a precompiled
prophet_model.bin (good, no compile needed) alongside an *incomplete*
bundled-cmdstan support directory (prophet/stan_model/cmdstan-<version>/ —
present but empty, no makefile). Prophet's backend loader sees that
directory exists and tries to validate it as a real CmdStan install, which
fails even though the actual model binary is fine and a real, working
CmdStan install exists elsewhere on the machine. Moving the incomplete stub
aside makes Prophet fall back to the general CmdStan install instead.

Run once, after `pip install -r requirements.txt`:
    .venv\\Scripts\\python.exe scripts\\setup_windows_prophet.py

Prerequisites this script does NOT install (do these first, each is a
one-off machine-level setup, not a per-project step):
  1. python -m cmdstanpy.install_cxx_toolchain --silent
     (installs a minimal RTools/MinGW toolchain under ~/.cmdstan/RTools40)
  2. Open a NEW terminal window (so it picks up the PATH change step 1
     made), then:
     python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"
     (builds CmdStan itself — takes several minutes)
"""
import importlib_resources
import shutil
import sys
from pathlib import Path


def main() -> int:
    if sys.platform != "win32":
        print("Not Windows — nothing to do here.")
        return 0

    stan_model_dir = importlib_resources.files("prophet") / "stan_model"
    model_bin = Path(str(stan_model_dir / "prophet_model.bin"))
    if not model_bin.exists():
        print(
            f"ERROR: {model_bin} doesn't exist — this isn't the issue this "
            "script fixes. Try reinstalling prophet: "
            "pip install --force-reinstall --no-cache-dir prophet"
        )
        return 1

    bundled_cmdstan_dirs = [
        p for p in Path(str(stan_model_dir)).iterdir() if p.is_dir() and p.name.startswith("cmdstan-")
    ]
    if not bundled_cmdstan_dirs:
        print("No incomplete bundled cmdstan directory found — nothing to fix.")
        return 0

    for d in bundled_cmdstan_dirs:
        has_makefile = (d / "makefile").exists() or (d / "make" / "standalone").exists()
        if has_makefile:
            print(f"{d} looks like a complete CmdStan install — leaving it alone.")
            continue
        target = d.with_suffix(".broken")
        print(f"Moving incomplete bundled CmdStan stub aside: {d} -> {target}")
        if target.exists():
            shutil.rmtree(target)
        d.rename(target)

    print(
        "Done. Verify with:\n"
        "  python -c \"from prophet import Prophet; import pandas as pd; "
        "Prophet().fit(pd.DataFrame({'ds': pd.date_range('2026-01-01', periods=10), 'y': range(10)}))\""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
