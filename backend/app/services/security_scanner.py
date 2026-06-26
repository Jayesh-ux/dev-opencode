import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# OWASP Top 10 detection patterns
OWASP_PATTERNS: dict[str, list[dict[str, Any]]] = {
    "A01_Broken_Access_Control": [
        {
            "pattern": re.compile(r"@app\.route\(.*\)[^@]*def\s+\w+\([^)]*\):\s*\n(?!.*@login_required|.*require_auth|.*@roles_allowed)", re.DOTALL),
            "message": "Route without authorization decorator",
            "severity": "high",
            "lang": "python",
        },
    ],
    "A02_Cryptographic_Failures": [
        {
            "pattern": re.compile(r"hashlib\.md5|hashlib\.sha1|DES\.new|ARC4\.new|DSA\.generate"),
            "message": "Weak cryptographic algorithm detected",
            "severity": "high",
            "lang": "python",
        },
        {
            "pattern": re.compile(r"http://[^\s\"'\)]+(?!localhost|127\.0\.0\.1)", re.IGNORECASE),
            "message": "Plain HTTP URL detected (possible cleartext transmission)",
            "severity": "medium",
            "lang": "any",
        },
    ],
    "A03_Injection": [
        {
            "pattern": re.compile(r"(?<!create_subprocess_)exec\s*\(|eval\s*\(|os\.system\s*\(|subprocess\.Popen\s*\([^)]*shell\s*=\s*True|subprocess\.call\s*\([^)]*shell\s*=\s*True"),
            "message": "Potential code injection via exec/eval/shell=True",
            "severity": "critical",
            "lang": "python",
        },
        {
            "pattern": re.compile(r"\.innerHTML\s*=|\.outerHTML\s*=|dangerouslySetInnerHTML"),
            "message": "Potential XSS via innerHTML/dangerouslySetInnerHTML",
            "severity": "high",
            "lang": "tsx",
        },
        {
            "pattern": re.compile(r"SELECT\s+.*\s+FROM\s+.*\s+WHERE\s+.*['\"]\s*\+\s*"),
            "message": "Potential SQL injection via string concatenation",
            "severity": "critical",
            "lang": "any",
        },
        {
            "pattern": re.compile(r"<\s*%\s*=\s*params\[|@RequestMapping.*\{\w+\}|@GetMapping.*\{\w+\}"),
            "message": "Potential unvalidated parameter binding",
            "severity": "medium",
            "lang": "java",
        },
    ],
    "A04_Insecure_Design": [
        {
            "pattern": re.compile(r"password\s*=\s*['\"][^'\"]{0,5}['\"]|secret\s*=\s*['\"][^'\"]{0,10}['\"]"),
            "message": "Hardcoded secret/password detected",
            "severity": "critical",
            "lang": "any",
        },
        {
            "pattern": re.compile(r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]"),
            "message": "CORS allows all origins",
            "severity": "medium",
            "lang": "python",
        },
    ],
    "A05_Security_Misconfiguration": [
        {
            "pattern": re.compile(r"DEBUG\s*=\s*True|debug\s*=\s*True|\.env\.local"),
            "message": "Debug mode enabled or local env file present",
            "severity": "medium",
            "lang": "any",
        },
        {
            "pattern": re.compile(r"app\.run\(.*debug\s*=\s*True"),
            "message": "Flask debug mode enabled in production",
            "severity": "high",
            "lang": "python",
        },
    ],
    "A06_Vulnerable_Components": [
        {
            "pattern": re.compile(r"^\s+\"[\w-]+\":\s*\"\^?\d+\.\d+\.\d+\"", re.MULTILINE),
            "message": "Check dependency version for known vulnerabilities (run npm audit / pip audit)",
            "severity": "info",
            "lang": "json",
            "is_dependency": True,
        },
    ],
    "A07_Authentication_Failures": [
        {
            "pattern": re.compile(r"session\[\"user\"\]|request\.cookies\.get\(\"auth\"\)|@app\.route\(.*\)(?:(?!login|auth).)*$", re.DOTALL),
            "message": "Possible weak session management",
            "severity": "high",
            "lang": "python",
        },
    ],
    "A08_Integrity_Failures": [
        {
            "pattern": re.compile(r"https?://[^\s\"'\)]*\.(?:exe|dmg|pkg|msi|sh|bat)\b"),
            "message": "Insecure binary download over HTTP",
            "severity": "high",
            "lang": "any",
        },
    ],
    "A09_Logging_Monitoring": [
        {
            "pattern": re.compile(r"except\s*:?\s*\n\s*pass|except\s+Exception:\s*\n\s*pass"),
            "message": "Bare except:pass silences all errors (poor observability)",
            "severity": "low",
            "lang": "python",
        },
        {
            "pattern": re.compile(r"api_key|apikey|api_secret|auth_token|secret_key\s*=\s*['\"][^'\"]+['\"]"),
            "message": "Hardcoded credential detected",
            "severity": "critical",
            "lang": "any",
        },
    ],
    "A10_SSRF": [
        {
            "pattern": re.compile(r"requests\.(get|post|put|delete)\(['\"](?:https?://)?\{|urllib\.request\.urlopen\(['\"].*\{|fetch\(`https?://\$\{"),
            "message": "Potential server-side request forgery via user-controlled URL",
            "severity": "high",
            "lang": "any",
        },
    ],
}

SCAN_DIRS = ["/root/dev/backend", "/root/dev/frontend"]


@dataclass
class Finding:
    rule: str
    message: str
    severity: str
    file: str
    line: int | None
    snippet: str
    lang: str

    def to_dict(self) -> dict:
        return {
            "rule": self.rule,
            "message": self.message,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "snippet": self.snippet[:200],
            "lang": self.lang,
        }


ScannedFile = tuple[str, int]  # (filepath, line_count)


async def scan_file(filepath: str) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    try:
        with open(filepath, "r", errors="replace") as f:
            content = f.read()
    except Exception as e:
        logger.debug("Cannot read %s: %s", filepath, e)
        return findings, 0

    total_lines = content.count("\n") + 1

    _, ext = os.path.splitext(filepath)
    ext_map = {
        ".py": "python",
        ".js": "tsx",
        ".ts": "tsx",
        ".tsx": "tsx",
        ".jsx": "tsx",
        ".html": "html",
        ".json": "json",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".env": "env",
    }
    lang = ext_map.get(ext, "any")

    for rule_name, patterns in OWASP_PATTERNS.items():
        for p in patterns:
            target_lang = p.get("lang", "any")
            if target_lang not in (lang, "any"):
                continue
            if p.get("is_dependency"):
                continue
            for match in p["pattern"].finditer(content):
                line_num = content[: match.start()].count("\n") + 1
                snippet = match.group()[:120]
                findings.append(Finding(
                    rule=rule_name,
                    message=p["message"],
                    severity=p["severity"],
                    file=filepath,
                    line=line_num,
                    snippet=snippet,
                    lang=lang,
                ))
    return findings, total_lines


def should_scan_file(filepath: str) -> bool:
    skip_dirs = [
        "node_modules", "__pycache__", ".next", ".git", ".pytest_cache",
        "venv", ".venv", "dist", "build", ".ai",
    ]
    if "security_scanner" in filepath and filepath.endswith(".py"):
        return False
    parts = filepath.replace("\\", "/").split("/")
    for skip in skip_dirs:
        if skip in parts:
            return False
    _, ext = os.path.splitext(filepath)
    return ext in (".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".json", ".yml", ".yaml", ".env")


async def scan_directory(path: str | None = None) -> tuple[list[Finding], int]:
    all_findings: list[Finding] = []
    total_lines = 0
    targets = [path] if path else SCAN_DIRS
    for target in targets:
        if not target or not os.path.isdir(target):
            logger.warning("Scan target %s not found", target)
            continue
        for root, _dirs, files in os.walk(target):
            for fname in files:
                fpath = os.path.join(root, fname)
                if should_scan_file(fpath):
                    try:
                        findings, line_count = await scan_file(fpath)
                        all_findings.extend(findings)
                        total_lines += line_count
                    except Exception as e:
                        logger.debug("Error scanning %s: %s", fpath, e)
    return all_findings, total_lines


async def run_dependency_audit(path: str | None = None) -> dict[str, Any]:
    results: dict[str, Any] = {"npm_audit": None, "pip_audit": None}
    base = path or "/root/dev"

    # npm audit
    pkg_path = os.path.join(base, "frontend")
    if os.path.exists(os.path.join(pkg_path, "package.json")):
        try:
            proc = await asyncio.create_subprocess_exec(
                "npm", "audit", "--json",
                cwd=pkg_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if stdout.strip():
                data = json.loads(stdout)
                results["npm_audit"] = {
                    "vulnerabilities": data.get("vulnerabilities", {}),
                    "metadata": data.get("metadata", {}),
                }
                logger.info("npm audit: %d vulnerabilities found", len(data.get("vulnerabilities", {})))
        except json.JSONDecodeError:
            results["npm_audit"] = {"error": "Failed to parse npm audit output"}
        except FileNotFoundError:
            results["npm_audit"] = {"error": "npm not installed"}
        except asyncio.TimeoutError:
            results["npm_audit"] = {"error": "npm audit timed out"}
        except Exception as e:
            results["npm_audit"] = {"error": str(e)}

    # pip audit (check installed packages for known vulnerabilities)
    try:
        proc = await asyncio.create_subprocess_exec(
            "pip3", "list", "--format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if stdout.strip():
            pkgs = json.loads(stdout)
            results["pip_packages"] = [{"name": p["name"], "version": p["version"]} for p in pkgs]
    except Exception as e:
        results["pip_audit"] = {"error": str(e)}

    return results


async def full_scan(path: str | None = None) -> dict[str, Any]:
    import time
    t0 = time.monotonic()

    code_findings, total_lines_scanned = await scan_directory(path)
    dep_results = await run_dependency_audit(path)

    execution_time_ms = int((time.monotonic() - t0) * 1000)

    by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    by_owasp: dict[str, int] = {}
    for f in code_findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
        by_owasp[f.rule] = by_owasp.get(f.rule, 0) + 1

    categorized = []
    for rule_name, count in sorted(by_owasp.items(), key=lambda x: -x[1]):
        categorized.append({"rule": rule_name, "count": count})

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    scan_result = {
        "summary": {
            "total_findings": len(code_findings),
            "total_lines_scanned": total_lines_scanned,
            "execution_time_ms": execution_time_ms,
            "by_severity": by_severity,
            "by_owasp": categorized,
            "passed": len(code_findings) == 0,
        },
        "findings": [
            f.to_dict() for f in sorted(
                code_findings,
                key=lambda x: (severity_order.get(x.severity, 5), x.file, x.line or 0),
            )
        ],
        "dependencies": dep_results,
    }
    return scan_result


def get_security_gate_prompt(findings: list[Finding]) -> str:
    if not findings:
        return ""
    critical = [f for f in findings if f.severity == "critical"]
    high = [f for f in findings if f.severity == "high"]

    prompt_parts = [
        "## SECURITY GATE: OWASP Vulnerabilities Detected",
        "",
        f"The security scanner found **{len(findings)}** potential vulnerabilities ({len(critical)} critical, {len(high)} high).",
        "",
        "### Top Findings",
    ]

    for f in (critical + high)[:5]:
        prompt_parts.append(f"- **[{f.severity.upper()}]** `{os.path.basename(f.file)}:{f.line}` — {f.message}")
        prompt_parts.append(f"  ```\n  {f.snippet}\n  ```")

    prompt_parts.extend([
        "",
        "**Action Required:** Review and fix the above findings before proceeding.",
        "The security gate blocks automated execution until all critical and high findings are resolved.",
    ])

    return "\n".join(prompt_parts)
