import os
import shutil
import tempfile
import unittest
from pathlib import Path

from harness.security import (
    SecretManager,
    load_encrypted_env,
    set_encrypted_secret,
    ENCRYPTED_PREFIX,
)


class TestSecurityModule(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="agy_sec_test_"))
        self.key_file = self.test_dir / ".secret.key"
        self.env_file = self.test_dir / ".env"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_key_generation(self):
        key = SecretManager.generate_key(save_to=self.key_file)
        self.assertTrue(self.key_file.exists())
        self.assertEqual(self.key_file.read_text(encoding="utf-8").strip(), key)

    def test_encrypt_decrypt_roundtrip(self):
        key = SecretManager.generate_key(save_to=self.key_file)
        manager = SecretManager(key=key)

        original_secret = "AIzaSyTestApiKey_9876543210"
        encrypted = manager.encrypt(original_secret)

        self.assertTrue(encrypted.startswith(ENCRYPTED_PREFIX))
        self.assertNotEqual(encrypted, original_secret)

        decrypted = manager.decrypt(encrypted)
        self.assertEqual(decrypted, original_secret)

    def test_invalid_key_fails(self):
        key1 = SecretManager.generate_key()
        key2 = SecretManager.generate_key()

        mgr1 = SecretManager(key=key1)
        mgr2 = SecretManager(key=key2)

        encrypted = mgr1.encrypt("my_super_secret")
        with self.assertRaises(ValueError):
            mgr2.decrypt(encrypted)

    def test_set_and_load_encrypted_env(self):
        original_api_key = "AIzaSy_Secret_Gemini_Key_XYZ"
        set_encrypted_secret(
            key_name="GEMINI_API_KEY",
            plain_value=original_api_key,
            env_path=self.env_file,
            key_file=self.key_file,
        )

        # .env 파일에 enc: 로 저장되었는지 확인
        content = self.env_file.read_text(encoding="utf-8")
        self.assertIn("GEMINI_API_KEY=enc:", content)
        self.assertNotIn(original_api_key, content)

        # 평문 일반 환경변수도 .env에 추가
        with open(self.env_file, "a", encoding="utf-8") as f:
            f.write("\nPLAIN_CONFIG=regular_value\n")

        # load_encrypted_env 로드 테스트
        loaded = load_encrypted_env(env_path=self.env_file, key_file=self.key_file)

        self.assertEqual(loaded["GEMINI_API_KEY"], original_api_key)
        self.assertEqual(loaded["PLAIN_CONFIG"], "regular_value")
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), original_api_key)
        self.assertEqual(os.environ.get("PLAIN_CONFIG"), "regular_value")


if __name__ == "__main__":
    unittest.main()
