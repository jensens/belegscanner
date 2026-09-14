"""WebKit-Sandbox-Umgebung pruefen und nur bei Bedarf deaktivieren.

Die WebKit-Sandbox braucht unprivilegierte User-Namespaces. Wo die fehlen
(gehaertete Kernel, manche Container), crasht WebKit mit "bwrap: Permission
denied" - nur dort wird die Sandbox per Env-Var abgeschaltet.
"""

import os
import subprocess
from pathlib import Path

from belegscanner.log import get_logger

logger = get_logger(__name__)

ENV_VAR = "WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS"

_USERNS_SYSCTL = Path("/proc/sys/kernel/unprivileged_userns_clone")
_APPARMOR_SYSCTL = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")


def _sysctl_is(path: Path, value: str) -> bool:
    try:
        return path.exists() and path.read_text().strip() == value
    except OSError:
        return False


def user_namespaces_available() -> bool:
    """True, wenn unprivilegierte User-Namespaces praktisch nutzbar sind.

    Massgeblich ist ein echter bwrap-Probelauf — genau das, was WebKit beim
    Sandbox-Start tut. Die Sysctls allein reichen nicht: Ubuntu-Familie-Kernel
    (auch TUXEDO OS) melden in unprivileged_userns_clone "1", blocken bwrap
    aber trotzdem ueber apparmor_restrict_unprivileged_userns. Die Sysctls
    dienen nur als Naeherung, falls bwrap nicht ausfuehrbar ist.
    """
    try:
        result = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        pass
    if _sysctl_is(_APPARMOR_SYSCTL, "1"):
        return False
    return _sysctl_is(_USERNS_SYSCTL, "1")


def ensure_webkit_sandbox_env() -> None:
    """Sandbox-Env-Var setzen, falls noetig und nicht schon konfiguriert.

    Muss VOR dem ersten WebKit-Import laufen.
    """
    if ENV_VAR in os.environ:
        return
    if not user_namespaces_available():
        logger.warning("User-Namespaces nicht verfuegbar - WebKit-Sandbox wird deaktiviert")
        os.environ[ENV_VAR] = "1"
