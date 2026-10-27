import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

@dataclass
class TestCase:
    id: str
    description: str
    prompt: str
    initial_files: Dict[str, str] = field(default_factory=dict)
    expected_files: List[str] = field(default_factory=list)
    verification_command: Optional[str] = None
    disallowed_tools: List[str] = field(default_factory=list)
    timeout_seconds: int = 120

    @classmethod
    def from_json(cls, path: str) -> "TestCase":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"테스트 케이스 파일을 찾을 수 없습니다: '{path}'")
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 형식 오류가 발생했습니다 ('{path}'): {e}")
        return cls(**data)

    def to_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2, ensure_ascii=False)


class SandboxEnvironment:
    """에이전트가 안전하게 코드를 생성하고 실행할 수 있는 격리된 샌드박스 환경"""

    def __init__(self, test_case: TestCase, base_dir: Optional[str] = None, preserve: bool = False):
        self.test_case = test_case
        self.base_dir = base_dir
        self.preserve = preserve
        self.path: Optional[Path] = None

    def __enter__(self) -> Path:
        if self.base_dir:
            self.path = Path(self.base_dir) / f"sandbox_{self.test_case.id}"
            if self.path.exists():
                shutil.rmtree(self.path)
            self.path.mkdir(parents=True, exist_ok=True)
        else:
            self.path = Path(tempfile.mkdtemp(prefix=f"agy_harness_{self.test_case.id}_"))

        # 초기 파일 주입
        for rel_path, content in self.test_case.initial_files.items():
            target_file = self.path / rel_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(content)

        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.preserve and self.path and self.path.exists():
            shutil.rmtree(self.path, ignore_errors=True)
