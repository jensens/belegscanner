"""Credential management using system keyring (libsecret)."""


class CredentialService:
    """Password management via system keyring.

    Uses libsecret (GNOME Keyring) to securely store and retrieve
    IMAP passwords. Falls back gracefully when keyring is unavailable.
    """

    SCHEMA_NAME = "de.kup.belegscanner"
    SCHEMA_ATTRIBUTE = "username"

    @staticmethod
    def _get_secret_module():
        """Get the Secret module if available.

        Returns:
            The gi.repository.Secret module, or None if unavailable.
        """
        try:
            import gi

            gi.require_version("Secret", "1")
            from gi.repository import Secret

            return Secret
        except (ImportError, ValueError):
            return None

    @classmethod
    def is_available(cls) -> bool:
        """Check if system keyring is available.

        Returns:
            True if libsecret is installed and accessible.
        """
        return cls._get_secret_module() is not None

    def _get_schema(self):
        """Get the Secret schema for password storage.

        Returns:
            A Secret.Schema object, or None if unavailable.
        """
        secret = self._get_secret_module()
        if secret is None:
            return None

        return secret.Schema.new(
            self.SCHEMA_NAME,
            secret.SchemaFlags.NONE,
            {self.SCHEMA_ATTRIBUTE: secret.SchemaAttributeType.STRING},
        )

    def store_password(self, username: str, password: str) -> bool:
        """Store password in system keyring.

        Args:
            username: The username/email to associate with the password.
            password: The password to store.

        Returns:
            True if storage was successful, False otherwise.
        """
        secret = self._get_secret_module()
        if secret is None:
            return False

        schema = self._get_schema()
        if schema is None:
            return False

        try:
            secret.password_store_sync(
                schema,
                {self.SCHEMA_ATTRIBUTE: username},
                secret.COLLECTION_DEFAULT,
                f"Belegscanner IMAP password for {username}",
                password,
                None,
            )
            return True
        except Exception:
            return False

    def get_password(self, username: str) -> str | None:
        """Retrieve password from system keyring.

        Args:
            username: The username/email to look up.

        Returns:
            The stored password, or None if not found or unavailable.
        """
        secret = self._get_secret_module()
        if secret is None:
            return None

        schema = self._get_schema()
        if schema is None:
            return None

        try:
            return secret.password_lookup_sync(
                schema,
                {self.SCHEMA_ATTRIBUTE: username},
                None,
            )
        except Exception:
            return None

    def delete_password(self, username: str) -> bool:
        """Remove password from system keyring.

        Args:
            username: The username/email whose password to delete.

        Returns:
            True if deletion was successful, False otherwise.
        """
        secret = self._get_secret_module()
        if secret is None:
            return False

        schema = self._get_schema()
        if schema is None:
            return False

        try:
            return secret.password_clear_sync(
                schema,
                {self.SCHEMA_ATTRIBUTE: username},
                None,
            )
        except Exception:
            return False
