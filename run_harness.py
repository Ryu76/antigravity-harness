import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
from harness.environment import SandboxEnvironment, TestCase
from harness.driver import AgentDriver
from harness.evaluator import Evaluator, EvaluationReport
from harness.security import load_encrypted_env

async def run_single_case(test_case: TestCase, use_mock: bool, preserve: bool) -> EvaluationReport:
    print(f"\n==================================================")
    print(f"🚀 [Case 실행] {test_case.id} - {test_case.description}")
    print(f"==================================================")

    with SandboxEnvironment(test_case=test_case, preserve=preserve) as sandbox_path:
        print(f"📁 샌드박스 준비 완료: {sandbox_path}")

        # 1. 드라이버 실행
        driver = AgentDriver(use_mock=use_mock)
        print("🤖 에이전트 구동 중...")
        trace = await driver.run(test_case, sandbox_path)
        print(f"⏱️ 에이전트 실행 완료 ({trace.duration_seconds}초 소요)")

        # 2. 결과 검증 (오라클)
        print("🔍 결과 평가 및 검증 진행 중...")
        report = Evaluator.evaluate(test_case, trace, sandbox_path)
        print(report.to_summary_markdown())
        return report

async def main():
    parser = argparse.ArgumentParser(description="Antigravity Test Harness Runner")
    parser.add_argument("--case", type=str, help="실행할 단일 테스트 케이스 JSON 파일 경로")
    parser.add_argument("--cases-dir", type=str, default="cases", help="테스트 케이스 디렉터리 경로")
    parser.add_argument("--mock", action="store_true", help="Antigravity SDK 없이 Mock 에이전트로 실행")
    parser.add_argument("--preserve", action="store_true", help="테스트 완료 후 샌드박스 디렉터리 보존")
    parser.add_argument("--output", type=str, default="harness_report.json", help="결과 리포트 파일 경로")
    parser.add_argument("--env-file", type=str, default=None, help=".env 파일 경로")
    parser.add_argument("--key-file", type=str, default=None, help="마스터 키 파일 경로")
    args = parser.parse_args()

    # 0. 암호화된 환경 변수 로드
    try:
        loaded = load_encrypted_env(
            env_path=Path(args.env_file) if args.env_file else None,
            key_file=Path(args.key_file) if args.key_file else None,
        )
        if "GEMINI_API_KEY" in loaded:
            print("🔐 암호화된 GEMINI_API_KEY를 성공적으로 복호화하여 메모리에 주입했습니다.")
    except Exception as e:
        print(f"⚠️ 암호화 환경변수 로드 알림: {e}")

    cases_to_run = []
    if args.case:
        case_path = Path(args.case)
        if not case_path.exists():
            print(f"❌ [파일 없음] 지정한 테스트 케이스 파일을 찾을 수 없습니다: '{args.case}'")
            cases_dir = Path(args.cases_dir)
            if cases_dir.exists():
                available = [str(p) for p in sorted(cases_dir.glob("*.json"))]
                if available:
                    print(f"💡 현재 사용 가능한 케이스 목록:\n   " + "\n   ".join(available))
            sys.exit(1)
        cases_to_run.append(case_path)
    else:
        cases_dir = Path(args.cases_dir)
        if not cases_dir.exists():
            print(f"❌ [디렉터리 없음] 테스트 케이스 디렉터리를 찾을 수 없습니다: '{args.cases_dir}'")
            sys.exit(1)
        cases_to_run.extend(sorted(cases_dir.glob("*.json")))

    if not cases_to_run:
        print(f"❌ 실행할 테스트 케이스(.json)를 찾을 수 없습니다: '{args.cases_dir}'")
        sys.exit(1)

    print(f"✨ 총 {len(cases_to_run)}개의 테스트 케이스를 시작합니다. (Mock 모드: {args.mock})")

    reports = []
    for case_path in cases_to_run:
        try:
            test_case = TestCase.from_json(str(case_path))
        except Exception as e:
            print(f"❌ 케이스 로드 실패 ({case_path}): {e}")
            continue
        report = await run_single_case(test_case, use_mock=args.mock, preserve=args.preserve)
        reports.append(report)

    # 요약 집계
    total = len(reports)
    passed = sum(1 for r in reports if r.passed)
    failed = total - passed

    print("\n" + "=" * 50)
    print("📊 [하네스 최종 실행 요약]")
    print(f"총 케이스: {total} | 통과: {passed} | 실패: {failed}")
    print("=" * 50)

    # 결과 JSON 저장
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump([r.__dict__ for r in reports], f, indent=2, ensure_ascii=False, default=str)
    print(f"💾 상세 리포트가 저장되었습니다: {args.output}")

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
