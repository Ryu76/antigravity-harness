import os
from pathlib import Path
from typing import Dict, Optional
from cryptography.fernet import Fernet, InvalidToken
from dotenv import dotenv_values, set_key

DEFAULT_KEY_FILE = Path(".secret.key")
DEFAULT_ENV_FILE = Path(".env")
ENCRYPTED_PREFIX = "enc:"


class SecretManager:
    """Fernet(AES-128-CBC + HMAC) 기반의 대칭키 암복호화 관리자"""

    def __init__(self, key: Optional[str] = None, key_file: Optional[Path] = None):
        self.key_file = Path(key_file) if key_file else DEFAULT_KEY_FILE
        self._key = key or self._resolve_key()
        self._fernet = Fernet(self._key.encode("utf-8"))

    def _resolve_key(self) -> str:
        # 1. 환경변수 확인
        env_key = os.environ.get("HARNESS_MASTER_KEY")
        if env_key:
            return env_key.strip()

        # 2. 로컬 키 파일 확인
        if self.key_file.exists():
            with open(self.key_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content

        raise FileNotFoundError(
            f"마스터 암호화 키를 찾을 수 없습니다.\n"
            f"환경변수 'HARNESS_MASTER_KEY'를 설정하거나, "
            f"'python manage_secret.py init-key'를 실행하여 '{self.key_file}'를 생성하세요."
        )

    @classmethod
    def generate_key(cls, save_to: Optional[Path] = None) -> str:
        """신규 32바이트 url-safe base64 인코딩 마스터 키 생성"""
        new_key = Fernet.generate_key().decode("utf-8")
        if save_to:
            target_path = Path(save_to)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_key + "\n")
        return new_key

    def encrypt(self, plain_text: str) -> str:
        """평문 문자열을 암호화하여 'enc:<토큰>' 형식으로 반환"""
        if not plain_text:
            return ""
        cipher_bytes = self._fernet.encrypt(plain_text.encode("utf-8"))
        return f"{ENCRYPTED_PREFIX}{cipher_bytes.decode('utf-8')}"

    def decrypt(self, cipher_text: str) -> str:
        """'enc:<토큰>' 또는 '<토큰>' 형식의 암호문을 복호화하여 평문 반환"""
        if not cipher_text:
            return ""
        raw_cipher = cipher_text
        if raw_cipher.startswith(ENCRYPTED_PREFIX):
            raw_cipher = raw_cipher[len(ENCRYPTED_PREFIX):]

        try:
            plain_bytes = self._fernet.decrypt(raw_cipher.encode("utf-8"))
            return plain_bytes.decode("utf-8")
        except InvalidToken:
            raise ValueError(
                "암호화 토큰 복호화에 실패했습니다. "
                "마스터 키가 일치하지 않거나 암호문이 손상되었습니다."
            )


def load_encrypted_env(
    env_path: Optional[Path] = None,
    key_file: Optional[Path] = None,
    override: bool = True,
) -> Dict[str, str]:
    """
    .env 파일의 값을 로드하고, 'enc:' 접두사가 붙은 암호화된 값을
    복호화하여 os.environ에 주입합니다.
    """
    env_file = Path(env_path) if env_path else DEFAULT_ENV_FILE
    if not env_file.exists():
        return {}

    values = dotenv_values(env_file)
    manager: Optional[SecretManager] = None
    loaded_secrets = {}

    for key, value in values.items():
        if value is None:
            continue

        str_val = str(value).strip()
        if str_val.startswith(ENCRYPTED_PREFIX):
            if manager is None:
                manager = SecretManager(key_file=key_file)
            decrypted_val = manager.decrypt(str_val)
            loaded_secrets[key] = decrypted_val
            if override or key not in os.environ:
                os.environ[key] = decrypted_val
        else:
            loaded_secrets[key] = str_val
            if override or key not in os.environ:
                os.environ[key] = str_val

    return loaded_secrets


def set_encrypted_secret(
    key_name: str,
    plain_value: str,
    env_path: Optional[Path] = None,
    key_file: Optional[Path] = None,
) -> str:
    """
    평문 값을 암호화하여 .env 파일에 'KEY=enc:...' 형태로 저장/갱신합니다.
    """
    env_file = Path(env_path) if env_path else DEFAULT_ENV_FILE
    k_file = Path(key_file) if key_file else DEFAULT_KEY_FILE

    # 마스터 키가 없으면 자동 생성
    if not k_file.exists() and "HARNESS_MASTER_KEY" not in os.environ:
        SecretManager.generate_key(save_to=k_file)

    manager = SecretManager(key_file=k_file)
    encrypted_value = manager.encrypt(plain_value)

    if not env_file.exists():
        env_file.touch()

    set_key(str(env_file), key_name, encrypted_value, quote_mode="never")
    return encrypted_value
