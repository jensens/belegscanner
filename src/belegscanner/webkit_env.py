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


def user_namespaces_available() -> bool:
    """True, wenn unprivilegierte User-Namespaces nutzbar sind."""
    proc_file = Path("/proc/sys/kernel/unprivileged_userns_clone")
    if proc_file.exists():
        try:
            return proc_file.read_text().strip() == "1"
        except OSError:
            pass
    try:
        result = subprocess.run(
            ["bwrap", "--ro-bind", "/", "/", "true"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_webkit_sandbox_env() -> None:
    """Sandbox-Env-Var setzen, falls noetig und nicht schon konfiguriert.

    Muss VOR dem ersten WebKit-Import laufen.
    """
    if ENV_VAR in os.environ:
        return
    if not user_namespaces_available():
        logger.warning("User-Namespaces nicht verfuegbar - WebKit-Sandbox wird deaktiviert")
        os.environ[ENV_VAR] = "1"
