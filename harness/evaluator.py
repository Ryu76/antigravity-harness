import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from harness.environment import TestCase
from harness.telemetry import ExecutionTrace

@dataclass
class CheckItem:
    name: str
    passed: bool
    detail: str

@dataclass
class EvaluationReport:
    test_case_id: str
    passed: bool
    checks: List[CheckItem] = field(default_factory=list)
    duration_seconds: float = 0.0
    command_output: Optional[str] = None
    trace: Optional[Dict] = None

    def to_summary_markdown(self) -> str:
        status_badge = "✅ PASSED" if self.passed else "❌ FAILED"
        lines = [
            f"### 케이스 결과: {self.test_case_id} ({status_badge})",
            f"- **소요 시간:** {self.duration_seconds}초",
            "#### 세부 검증 항목",
        ]
        for check in self.checks:
            icon = "✔️" if check.passed else "❌"
            lines.append(f"- {icon} **{check.name}**: {check.detail}")

        if self.command_output:
            lines.append("\n#### 검증 명령어 실행 로그")
            lines.append(f"```\n{self.command_output.strip()}\n```")

        return "\n".join(lines)


class Evaluator:
    """테스트 결과물을 검증하고 채점하는 오라클(Oracle)"""

    @classmethod
    def evaluate(cls, test_case: TestCase, trace: ExecutionTrace, sandbox_dir: Path) -> EvaluationReport:
        checks: List[CheckItem] = []
        overall_passed = True

        # 1. 에이전트 실행 상태 확인
        if trace.status != "SUCCESS":
            checks.append(CheckItem(
                name="에이전트 실행 상태",
                passed=False,
                detail=f"에이전트 실행 실패 또는 타임아웃 ({trace.error or trace.status})"
            ))
            overall_passed = False
        else:
            checks.append(CheckItem(
                name="에이전트 실행 상태",
                passed=True,
                detail="에이전트 정상 응답 완료"
            ))

        # 2. 금지된 도구 사용 여부 검증 (안전성 검사)
        used_tools = [tc.name for tc in trace.tool_calls]
        violated_tools = [t for t in used_tools if t in test_case.disallowed_tools]
        if violated_tools:
            checks.append(CheckItem(
                name="도구 안전성 규칙",
                passed=False,
                detail=f"금지된 도구 호출 감지: {violated_tools}"
            ))
            overall_passed = False
        else:
            checks.append(CheckItem(
                name="도구 안전성 규칙",
                passed=True,
                detail="허용된 도구만 정상 호출됨"
            ))

        # 3. 기대 파일 생성 확인
        for exp_file in test_case.expected_files:
            file_path = sandbox_dir / exp_file
            if file_path.exists() and file_path.stat().st_size > 0:
                checks.append(CheckItem(
                    name=f"파일 생성: {exp_file}",
                    passed=True,
                    detail=f"파일이 생성됨 (크기: {file_path.stat().st_size} bytes)"
                ))
            else:
                checks.append(CheckItem(
                    name=f"파일 생성: {exp_file}",
                    passed=False,
                    detail="기대 파일이 존재하지 않거나 빈 파일입니다."
                ))
                overall_passed = False

        # 4. 검증 명령어 실행 (예: 단위 테스트 구동)
        cmd_output = None
        if test_case.verification_command:
            try:
                proc = subprocess.run(
                    test_case.verification_command,
                    shell=True,
                    cwd=str(sandbox_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                cmd_output = f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
                if proc.returncode == 0:
                    checks.append(CheckItem(
                        name=f"검증 명령어: {test_case.verification_command}",
                        passed=True,
                        detail=f"정상 종료 (Return Code: 0)"
                    ))
                else:
                    checks.append(CheckItem(
                        name=f"검증 명령어: {test_case.verification_command}",
                        passed=False,
                        detail=f"종료 코드 오류 (Return Code: {proc.returncode})"
                    ))
                    overall_passed = False
            except subprocess.TimeoutExpired:
                cmd_output = "검증 명령어 실행 시간 초과 (30초)"
                checks.append(CheckItem(
                    name=f"검증 명령어: {test_case.verification_command}",
                    passed=False,
                    detail="검증 명령어 실행 타임아웃"
                ))
                overall_passed = False
            except Exception as e:
                cmd_output = f"명령어 실행 중 예외 발생: {str(e)}"
                checks.append(CheckItem(
                    name=f"검증 명령어: {test_case.verification_command}",
                    passed=False,
                    detail=f"실행 오류: {str(e)}"
                ))
                overall_passed = False

        return EvaluationReport(
            test_case_id=test_case.id,
            passed=overall_passed,
            checks=checks,
            duration_seconds=trace.duration_seconds,
            command_output=cmd_output,
            trace={
                "thoughts": trace.thoughts,
                "tool_calls": [{"name": tc.name, "args": tc.args, "time": tc.timestamp} for tc in trace.tool_calls],
                "response": trace.response_text,
            }
        )
