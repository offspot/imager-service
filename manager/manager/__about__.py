import os
import subprocess


def get_git_ident() -> str | None:
    ps = subprocess.run(
        ["/usr/bin/env", "git", "rev-parse", "--short", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    if ps.returncode == 0:
        return ps.stdout.strip()[:7]

    if os.getenv("GIT_REV"):
        return os.environ["GIT_REV"].strip()[:7]

    return None


__version__ = "2025-12"
__tech_version__ = get_git_ident()


def get_version(*, extended: bool = False) -> str:
    """Hotspot-stack version, with imager-service tech one optionaly"""
    if extended:
        return f"{__version__} ({__tech_version__})"
    return __version__
