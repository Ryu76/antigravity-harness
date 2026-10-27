import asyncio
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from harness.environment import TestCase
from harness.telemetry import ExecutionTrace, ToolCallRecord

class AgentDriver:
    """Antigravity 에이전트를 초기화하고 테스트 케이스를 실행하며 텔레메트리를 수집하는 드라이버"""

    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock

    async def run(self, test_case: TestCase, sandbox_dir: Path) -> ExecutionTrace:
        trace = ExecutionTrace(test_case_id=test_case.id)
        start_t = time.time()

        try:
            if self.use_mock:
                await self._run_mock(test_case, sandbox_dir, trace)
            else:
                await self._run_sdk(test_case, sandbox_dir, trace)
            trace.status = "SUCCESS"
        except asyncio.TimeoutError:
            trace.status = "TIMEOUT"
            trace.error = f"테스트 실행 시간 초과 ({test_case.timeout_seconds}초)"
        except Exception as e:
            trace.status = "FAILED"
            trace.error = str(e)
        finally:
            trace.duration_seconds = round(time.time() - start_t, 2)
            trace.end_time = datetime.now().isoformat()

        return trace

    async def _run_sdk(self, test_case: TestCase, sandbox_dir: Path, trace: ExecutionTrace):
        if "GEMINI_API_KEY" not in os.environ or not os.environ["GEMINI_API_KEY"].strip():
            raise RuntimeError(
                "GEMINI_API_KEY가 설정되지 않았습니다.\n"
                "'python manage_secret.py set GEMINI_API_KEY' 명령어로 .env 파일에 암호화된 키를 등록하거나,\n"
                "환경변수를 설정해 주세요."
            )

        try:
            from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
        except ImportError:
            raise RuntimeError(
                "google-antigravity 패키지가 설치되지 않았습니다. "
                "'pip install google-antigravity'를 실행하거나 --mock 옵션을 사용하세요."
            )

        config = LocalAgentConfig(
            capabilities=CapabilitiesConfig(),
            system_instructions=(
                "당신은 주어진 코딩 과제를 해결하는 AI 소프트웨어 엔지니어입니다. "
                "작업 디렉토리의 파일을 읽고 요구사항에 맞추어 솔루션을 작성하세요."
            ),
        )

        async with Agent(config) as agent:
            # 타임아웃 적용
            async with asyncio.timeout(test_case.timeout_seconds):
                response = await agent.chat(test_case.prompt)

                # 생각(Thinking) 스트림 수집
                if hasattr(response, "thoughts"):
                    async for thought in response.thoughts:
                        trace.thoughts.append(str(thought))

                # 도구 호출(ToolCall) 이벤트 수집
                if hasattr(response, "tool_calls"):
                    async for call in response.tool_calls:
                        trace.tool_calls.append(
                            ToolCallRecord(name=call.name, args=getattr(call, "args", {}))
                        )

                # 최종 응답 토큰 스트림 수집
                response_chunks = []
                async for token in response:
                    response_chunks.append(token)
                trace.response_text = "".join(response_chunks)

    async def _run_mock(self, test_case: TestCase, sandbox_dir: Path, trace: ExecutionTrace):
        """SDK 없이 하네스 파이프라인 검증을 위한 모의 실행기"""
        trace.thoughts.append("Mock: 요구사항 분석 중...")
        await asyncio.sleep(0.3)
        trace.thoughts.append("Mock: 테스트 코드 확인 및 필요한 파일 작성 계획 수립.")

        # 모의 파일 생성 (solution.py 가 기대되는 경우 예시 솔루션 작성)
        if "solution.py" in test_case.expected_files:
            sol_path = sandbox_dir / "solution.py"
            with open(sol_path, "w", encoding="utf-8") as f:
                f.write(
                    "def unique_sorted(numbers):\n"
                    "    \"\"\"중복을 제거하고 오름차순으로 정렬된 리스트를 반환합니다.\"\"\"\n"
                    "    return sorted(list(set(numbers)))\n"
                )
            trace.tool_calls.append(
                ToolCallRecord(
                    name="write_to_file",
                    args={"TargetFile": str(sol_path), "Description": "solution.py 생성"},
                )
            )

        await asyncio.sleep(0.2)
        trace.response_text = "요구사항에 맞추어 solution.py를 성공적으로 구현하였습니다."
