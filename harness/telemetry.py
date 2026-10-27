from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

@dataclass
class ToolCallRecord:
    name: str
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class ExecutionTrace:
    test_case_id: str
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    duration_seconds: float = 0.0
    thoughts: List[str] = field(default_factory=list)
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    response_text: str = ""
    error: Optional[str] = None
    status: str = "PENDING"  # PENDING, SUCCESS, FAILED, TIMEOUT
