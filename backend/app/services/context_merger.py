import asyncio
import logging

from app.services.gemini import _call_gemini
from app.services.security_scanner import scan_directory
from app.services.types import GeminiResult

logger = logging.getLogger(__name__)

SYNTHESIS_PROMPT_TEMPLATE = """You are the OpenCode Lead Automation Engineer. Your task is to process a raw conversation history between a developer and a research AI, extract the concrete engineering requirements, and output a highly dense, executable prompt optimized for terminal automation, file manipulation, and service initialization.

### INPUT DATA FOR COMPILATION
[RAW RESEARCH HISTORY]
{history}
[END RAW RESEARCH HISTORY]

[CURRENT ENVIRONMENT STATE]
Target: Debian Environment (Termux)
Active Frontend: Next.js (Port 3000)
Active Backend: FastAPI + Uvicorn (Port 8000)
Available Tooling: execute_command, read_file, write_file, list_directory
[END CURRENT ENVIRONMENT STATE]

### INSTRUCTIONS FOR PROMPT GENERATION
Analyze the input data above and output a single, consolidated execution directive for the OpenCode assistant. Your output must strictly follow this structural schema:

1. **Core Objective**: A one-sentence declaration of what is being built or fixed right now.
2. **Technical Architecture**: Explicit file paths, ports, and framework-specific parameters derived from the conversation.
3. **Incremental TODO List**: A bulleted checklist of direct actions.
4. **Validation Routine**: The exact curl or shell commands to run to verify the changes worked.

### OUTPUT FORMAT
Generate the engineering prompt below this line:
---
"""


def merge_context(history_text: str) -> tuple[str, str | None]:
    prompt = SYNTHESIS_PROMPT_TEMPLATE.format(history=history_text)
    try:
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        result: GeminiResult = _call_gemini(contents)
        if result.error_code:
            if result.error_code == 429:
                return _generate_local_prompt(history_text), None
            return _generate_local_prompt(history_text), result.error_message
        return result.text, None
    except Exception as e:
        logger.warning("Context merge failed: %s — using local fallback", e)
        return _generate_local_prompt(history_text), None


async def merge_context_with_security(history_text: str) -> tuple[str, str | None, list[dict]]:
    prompt, error = merge_context(history_text)
    findings = []
    try:
        code_findings, _total_lines = await scan_directory()
        from app.services.security_scanner import get_security_gate_prompt
        gate_block = get_security_gate_prompt(code_findings)
        if gate_block:
            prompt += "\n\n" + gate_block
            findings = [f.to_dict() for f in code_findings if f.severity in ("critical", "high")]
    except Exception as e:
        logger.warning("Security scan failed during context merge: %s", e)
    return prompt, error, findings


def _generate_local_prompt(history: str) -> str:
    lines = history.strip().split("\n")
    objective = "Unknown"
    for line in lines:
        if ":" in line and len(line) > 10:
            objective = line.strip()
            break
    return f"""## OpenCode Engineering Directive

### 1. Core Objective
{objective[:200]}

### 2. Technical Architecture
- Frontend: Next.js (http://127.0.0.1:3000)
- Backend: FastAPI + Uvicorn (http://127.0.0.1:8000)
- Model: Gemini 2.0 Flash (with local fallback)
- Tools: execute_command, read_file, write_file, list_directory

### 3. Incremental TODO List
- Review the conversation history for specific file paths and changes discussed
- Apply the agreed-upon modifications
- Verify service health after changes

### 4. Validation Routine
```bash
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w "%{{http_code}}" http://127.0.0.1:3000
```

---
*Generated from conversation context*"""
