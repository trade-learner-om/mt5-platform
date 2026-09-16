from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings
from app.exceptions import AppError


class EncryptionService:
    def __init__(self) -> None:
        self._fernet = Fernet(get_settings().fernet_key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise AppError(
                "Stored credential could not be decrypted.",
                code="CREDENTIAL_DECRYPTION_FAILED",
                status_code=500,
            ) from exc


encryption_service = EncryptionService()
