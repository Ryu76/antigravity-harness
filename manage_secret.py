#!/usr/bin/env python3
import argparse
import getpass
import sys
from pathlib import Path

# Windows 콘솔 utf-8 인코딩 안전화
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from harness.security import (
    DEFAULT_ENV_FILE,
    DEFAULT_KEY_FILE,
    ENCRYPTED_PREFIX,
    SecretManager,
    load_encrypted_env,
    set_encrypted_secret,
)


def mask_secret(secret: str) -> str:
    """비밀값을 안전하게 마스킹 (예: AIzaSy...1234 -> AIzaSy********1234)"""
    if len(secret) <= 8:
        return "********"
    return secret[:6] + "*" * (len(secret) - 10) + secret[-4:]


def cmd_init_key(args):
    key_path = Path(args.key_file)
    if key_path.exists() and not args.force:
        print(f"[WARN] 이미 마스터 키 파일이 존재합니다: {key_path}")
        print("덮어쓰려면 --force 옵션을 추가하세요. (주의: 기존 암호화된 값들은 복호화할 수 없게 됩니다)")
        sys.exit(1)

    key = SecretManager.generate_key(save_to=key_path)
    print(f"[OK] 신규 마스터 키가 안전하게 생성되었습니다: {key_path}")
    print("[SECURITY] 이 파일은 절대로 Git 저장소에 커밋하거나 외부로 공유하지 마세요.")


def cmd_set(args):
    key_name = args.name
    plain_value = args.value

    # 인자로 넘어오지 않은 경우 대화형(마스킹)으로 입력받음
    if not plain_value:
        print(f"[INPUT] [{key_name}] 설정:")
        plain_value = getpass.getpass(f"'{key_name}'에 저장할 평문 값을 입력하세요 (입력값 숨김): ")
        if not plain_value:
            print("[ERROR] 값이 입력되지 않아 취소되었습니다.")
            sys.exit(1)

    enc_val = set_encrypted_secret(
        key_name=key_name,
        plain_value=plain_value,
        env_path=Path(args.env_file),
        key_file=Path(args.key_file),
    )

    print(f"[OK] '{key_name}' 값이 암호화되어 {args.env_file}에 저장되었습니다!")
    print(f"[SAVED] 암호화 토큰: {enc_val[:14]}... (전체 길이: {len(enc_val)})")


def cmd_get(args):
    key_name = args.name
    env_secrets = load_encrypted_env(
        env_path=Path(args.env_file),
        key_file=Path(args.key_file),
    )

    if key_name not in env_secrets:
        print(f"[ERROR] '{key_name}'이 {args.env_file}에 존재하지 않습니다.")
        sys.exit(1)

    val = env_secrets[key_name]
    if args.reveal:
        print(f"{key_name}={val}")
    else:
        print(f"{key_name}={mask_secret(val)} (전체 확인은 --reveal 옵션 사용)")


def cmd_verify(args):
    print(f"[INFO] 환경 설정 및 마스터 키 검증 중... (Env: {args.env_file}, Key: {args.key_file})")

    env_path = Path(args.env_file)
    if not env_path.exists():
        print(f"[WARN] {args.env_file} 파일이 없습니다.")
        return

    try:
        loaded = load_encrypted_env(env_path=env_path, key_file=Path(args.key_file))
        print(f"[OK] 총 {len(loaded)}개의 환경변수를 성공적으로 확인/복호화했습니다.")
        for k, v in loaded.items():
            print(f"  • {k}: {mask_secret(v)}")
    except Exception as e:
        print(f"[ERROR] 복호화 검증 실패: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Antigravity 하네스 비밀키 & 암호화 .env 관리 도구"
    )
    parser.add_argument(
        "--env-file", default=str(DEFAULT_ENV_FILE), help=".env 파일 경로 (기본값: .env)"
    )
    parser.add_argument(
        "--key-file", default=str(DEFAULT_KEY_FILE), help="마스터 키 파일 경로 (기본값: .secret.key)"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init-key
    p_init = subparsers.add_parser("init-key", help="마스터 암호화 키(.secret.key) 신규 생성")
    p_init.add_argument("--force", action="store_true", help="기존 키가 있어도 강제 재생성")
    p_init.set_defaults(func=cmd_init_key)

    # set
    p_set = subparsers.add_parser("set", help=".env에 암호화된 비밀값 저장/갱신")
    p_set.add_argument("name", help="환경변수 이름 (예: GEMINI_API_KEY)")
    p_set.add_argument("--value", help="평문 값 (미입력 시 마스킹 대화형 입력 프롬프트)")
    p_set.set_defaults(func=cmd_set)

    # get
    p_get = subparsers.add_parser("get", help="저장된 비밀값 복호화 조회")
    p_get.add_argument("name", help="환경변수 이름 (예: GEMINI_API_KEY)")
    p_get.add_argument("--reveal", action="store_true", help="마스킹 없이 평문 전체 출력")
    p_get.set_defaults(func=cmd_get)

    # verify
    p_verify = subparsers.add_parser("verify", help=".env 내 모든 암호화 항목 복호화 검증")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
