"""Tests for CredentialService."""

from unittest.mock import MagicMock, patch

from belegscanner.services.credential import CredentialService


class TestCredentialServiceAvailability:
    """Test availability checking."""

    def test_is_available_returns_true_when_secret_module_exists(self):
        """is_available returns True when libsecret is available."""
        with patch.object(CredentialService, "_get_secret_module") as mock:
            mock.return_value = MagicMock()
            assert CredentialService.is_available() is True

    def test_is_available_returns_false_when_import_fails(self):
        """is_available returns False when libsecret is not installed."""
        with patch.object(CredentialService, "_get_secret_module") as mock:
            mock.return_value = None
            assert CredentialService.is_available() is False


class TestCredentialServiceStore:
    """Test password storage."""

    def test_store_password_saves_to_keyring(self):
        """store_password saves credentials to system keyring."""
        mock_secret = MagicMock()
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=mock_secret):
            result = service.store_password("user@example.com", "secret123")

        assert result is True
        mock_secret.password_store_sync.assert_called_once()
        # Password is passed as positional arg (index 4)
        call_args = mock_secret.password_store_sync.call_args
        assert "secret123" in call_args[0]

    def test_store_password_returns_false_when_keyring_unavailable(self):
        """store_password returns False when keyring is not available."""
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=None):
            result = service.store_password("user@example.com", "secret123")

        assert result is False

    def test_store_password_returns_false_on_exception(self):
        """store_password returns False when storage fails."""
        mock_secret = MagicMock()
        mock_secret.password_store_sync.side_effect = Exception("Storage failed")
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=mock_secret):
            result = service.store_password("user@example.com", "secret123")

        assert result is False


class TestCredentialServiceRetrieve:
    """Test password retrieval."""

    def test_get_password_retrieves_from_keyring(self):
        """get_password retrieves password from system keyring."""
        mock_secret = MagicMock()
        mock_secret.password_lookup_sync.return_value = "secret123"
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=mock_secret):
            result = service.get_password("user@example.com")

        assert result == "secret123"
        mock_secret.password_lookup_sync.assert_called_once()

    def test_get_password_returns_none_when_not_found(self):
        """get_password returns None when no password is stored."""
        mock_secret = MagicMock()
        mock_secret.password_lookup_sync.return_value = None
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=mock_secret):
            result = service.get_password("unknown@example.com")

        assert result is None

    def test_get_password_returns_none_when_keyring_unavailable(self):
        """get_password returns None when keyring is not available."""
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=None):
            result = service.get_password("user@example.com")

        assert result is None

    def test_get_password_returns_none_on_exception(self):
        """get_password returns None when lookup fails."""
        mock_secret = MagicMock()
        mock_secret.password_lookup_sync.side_effect = Exception("Lookup failed")
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=mock_secret):
            result = service.get_password("user@example.com")

        assert result is None


class TestCredentialServiceDelete:
    """Test password deletion."""

    def test_delete_password_removes_from_keyring(self):
        """delete_password removes password from system keyring."""
        mock_secret = MagicMock()
        mock_secret.password_clear_sync.return_value = True
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=mock_secret):
            result = service.delete_password("user@example.com")

        assert result is True
        mock_secret.password_clear_sync.assert_called_once()

    def test_delete_password_returns_false_when_not_found(self):
        """delete_password returns False when no password exists."""
        mock_secret = MagicMock()
        mock_secret.password_clear_sync.return_value = False
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=mock_secret):
            result = service.delete_password("unknown@example.com")

        assert result is False

    def test_delete_password_returns_false_when_keyring_unavailable(self):
        """delete_password returns False when keyring is not available."""
        service = CredentialService()

        with patch.object(service, "_get_secret_module", return_value=None):
            result = service.delete_password("user@example.com")

        assert result is False


class TestCredentialServiceSchema:
    """Test schema configuration."""

    def test_service_uses_correct_schema_name(self):
        """Service uses 'de.kup.belegscanner' as schema name."""
        assert CredentialService.SCHEMA_NAME == "de.kup.belegscanner"

    def test_service_uses_username_as_attribute(self):
        """Service uses 'username' as the identifying attribute."""
        assert CredentialService.SCHEMA_ATTRIBUTE == "username"
