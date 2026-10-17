from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from truvix_ai.analysis.schemas import AnalysisRequest


MAX_COPILOT_INPUT_LENGTH: Final[int] = 4000

PROMPT_INJECTION_PATTERNS: Final[list[re.Pattern]] = [
    re.compile(r"ignore previous instructions", re.IGNORECASE),
    re.compile(r"forget all instructions", re.IGNORECASE),
    re.compile(r"you are now a", re.IGNORECASE),
    re.compile(r"system message", re.IGNORECASE),
    re.compile(r"bypassing filters", re.IGNORECASE),
]

BLOCKED_TOPICS: Final[list[str]] = [
    "hukuki tavsiye", "tıbbi", "sağlık", "legal advice", "medical"
]


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    passed: bool
    violations: list[str]
    sanitized_input: str | None


class InputValidator:
    """Validates inputs before sending to AI models."""
    
    def validate_analysis_input(self, request: AnalysisRequest) -> GuardrailResult:
        violations = []
        
        if len(request.photos) > 12:
            violations.append("Maximum of 12 photos allowed.")
            
        import datetime
        current_year = datetime.datetime.now().year
        if request.vehicle.model_year > current_year + 1 or request.vehicle.model_year < 1900:
            violations.append(f"Model year {request.vehicle.model_year} is out of bounds.")
            
        for photo in request.photos:
            if len(photo.data_b64) > 10 * 1024 * 1024:  # roughly 10MB base64
                violations.append("A photo exceeds the size limits.")
                break
                
        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
            sanitized_input=None
        )

    def validate_copilot_input(self, message: str) -> GuardrailResult:
        violations = []
        
        if len(message) > MAX_COPILOT_INPUT_LENGTH:
            violations.append("Input exceeds max length of 4000 characters.")
            
        for pattern in PROMPT_INJECTION_PATTERNS:
            if pattern.search(message):
                violations.append("Input matches prompt injection patterns.")
                break
                
        message_lower = message.lower()
        for topic in BLOCKED_TOPICS:
            if topic in message_lower:
                violations.append(f"Input contains blocked topic: {topic}.")
                
        return GuardrailResult(
            passed=len(violations) == 0,
            violations=violations,
            sanitized_input=message if len(violations) == 0 else None
        )
