"""Tests for the WebKit sandbox environment probe."""

import os
from unittest.mock import patch

from belegscanner.webkit_env import ENV_VAR, ensure_webkit_sandbox_env


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
