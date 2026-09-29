"""Secure, per-user storage for Google OAuth tokens.

Desktop installations keep refresh tokens in the operating system credential
vault through ``keyring``.  Carole deliberately has no automatic plaintext
fallback: a machine without a usable vault must configure one before Google
Workspace can be connected.
"""

from __future__ import annotations

import uuid


SERVICE_NAME = "carole.ai.google.oauth"


class SecureTokenStoreError(RuntimeError):
    """Raised when the operating-system credential vault is unavailable."""


def _account_name(user_id: str) -> str:
    return f"carole-user:{uuid.UUID(str(user_id))}"


def _keyring_module():
    try:
        import keyring
        from keyring.errors import KeyringError, NoKeyringError

        backend = keyring.get_keyring()
        if float(getattr(backend, "priority", 0)) <= 0:
            raise NoKeyringError("No secure system credential vault is available")
        return keyring, (KeyringError, NoKeyringError)
    except SecureTokenStoreError:
        raise
    except Exception as exc:
        raise SecureTokenStoreError(
            "No secure operating-system credential vault is available"
        ) from exc


def available() -> bool:
    try:
        _keyring_module()
        return True
    except SecureTokenStoreError:
        return False


def load(user_id: str) -> str | None:
    keyring, keyring_errors = _keyring_module()
    try:
        return keyring.get_password(SERVICE_NAME, _account_name(user_id))
    except keyring_errors as exc:
        raise SecureTokenStoreError("Could not read the Google token from the OS vault") from exc


def save(user_id: str, token_json: str) -> None:
    keyring, keyring_errors = _keyring_module()
    try:
        keyring.set_password(SERVICE_NAME, _account_name(user_id), token_json)
    except keyring_errors as exc:
        raise SecureTokenStoreError("Could not save the Google token in the OS vault") from exc


def delete(user_id: str) -> None:
    keyring, keyring_errors = _keyring_module()
    try:
        keyring.delete_password(SERVICE_NAME, _account_name(user_id))
    except keyring_errors as exc:
        # Missing credentials are already disconnected.  Different keyring
        # backends expose different exception subclasses, so confirm by read.
        try:
            if keyring.get_password(SERVICE_NAME, _account_name(user_id)) is None:
                return
        except keyring_errors:
            pass
        raise SecureTokenStoreError("Could not delete the Google token from the OS vault") from exc
