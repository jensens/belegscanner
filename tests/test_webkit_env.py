"""Tests for the WebKit sandbox environment probe."""

import os
from unittest.mock import MagicMock, patch

import belegscanner.webkit_env as webkit_env
from belegscanner.webkit_env import (
    ENV_VAR,
    ensure_webkit_sandbox_env,
    user_namespaces_available,
)


class TestUserNamespacesAvailable:
    """Der bwrap-Probelauf ist die Wahrheit; Sysctls nur Fallback.

    Hintergrund: Ubuntu-Familie-Kernel (auch TUXEDO OS) melden in
    /proc/sys/kernel/unprivileged_userns_clone "1", blocken bwrap aber
    trotzdem per apparmor_restrict_unprivileged_userns — die Sysctl allein
    ist kein verlaesslicher Indikator.
    """

    def test_bwrap_failure_wins_over_userns_sysctl(self, tmp_path, monkeypatch):
        userns = tmp_path / "unprivileged_userns_clone"
        userns.write_text("1\n")
        monkeypatch.setattr(webkit_env, "_USERNS_SYSCTL", userns)
        monkeypatch.setattr(webkit_env, "_APPARMOR_SYSCTL", tmp_path / "missing")
        with patch("belegscanner.webkit_env.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert user_namespaces_available() is False

    def test_bwrap_success_means_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(webkit_env, "_USERNS_SYSCTL", tmp_path / "missing")
        monkeypatch.setattr(webkit_env, "_APPARMOR_SYSCTL", tmp_path / "missing")
        with patch("belegscanner.webkit_env.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert user_namespaces_available() is True

    def test_missing_bwrap_honors_apparmor_restriction(self, tmp_path, monkeypatch):
        userns = tmp_path / "unprivileged_userns_clone"
        userns.write_text("1\n")
        apparmor = tmp_path / "apparmor_restrict_unprivileged_userns"
        apparmor.write_text("1\n")
        monkeypatch.setattr(webkit_env, "_USERNS_SYSCTL", userns)
        monkeypatch.setattr(webkit_env, "_APPARMOR_SYSCTL", apparmor)
        with patch("belegscanner.webkit_env.subprocess.run", side_effect=FileNotFoundError):
            assert user_namespaces_available() is False

    def test_missing_bwrap_falls_back_to_userns_sysctl(self, tmp_path, monkeypatch):
        userns = tmp_path / "unprivileged_userns_clone"
        userns.write_text("1\n")
        apparmor = tmp_path / "apparmor_restrict_unprivileged_userns"
        apparmor.write_text("0\n")
        monkeypatch.setattr(webkit_env, "_USERNS_SYSCTL", userns)
        monkeypatch.setattr(webkit_env, "_APPARMOR_SYSCTL", apparmor)
        with patch("belegscanner.webkit_env.subprocess.run", side_effect=FileNotFoundError):
            assert user_namespaces_available() is True

    def test_nothing_determinable_defaults_to_false(self, tmp_path, monkeypatch):
        monkeypatch.setattr(webkit_env, "_USERNS_SYSCTL", tmp_path / "missing")
        monkeypatch.setattr(webkit_env, "_APPARMOR_SYSCTL", tmp_path / "missing")
        with patch("belegscanner.webkit_env.subprocess.run", side_effect=FileNotFoundError):
            assert user_namespaces_available() is False


class TestEnsureWebkitSandboxEnv:
    def test_respects_existing_env_value(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "0")
        with patch("belegscanner.webkit_env.user_namespaces_available") as probe:
            ensure_webkit_sandbox_env()
        probe.assert_not_called()
        assert os.environ[ENV_VAR] == "0"

    def test_sets_var_when_namespaces_unavailable(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        with patch("belegscanner.webkit_env.user_namespaces_available", return_value=False):
            ensure_webkit_sandbox_env()
        assert os.environ.get(ENV_VAR) == "1"
        monkeypatch.delenv(ENV_VAR, raising=False)

    def test_keeps_sandbox_when_namespaces_available(self, monkeypatch):
        monkeypatch.delenv(ENV_VAR, raising=False)
        with patch("belegscanner.webkit_env.user_namespaces_available", return_value=True):
            ensure_webkit_sandbox_env()
        assert ENV_VAR not in os.environ
