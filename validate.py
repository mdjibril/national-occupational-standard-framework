#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Literal

ERROR = 'ERROR'
WARNING = 'WARNING'

# Regex Patterns
PC_PATTERN = re.compile(r"^(\d+)\.(\d+)$")

_ARTIFACT_PATTERNS = (
    r"\bPAGE\s+\d+\b",
    r"\bNSQ\b",
    r"\bLEVEL\b",
    r"CREDIT\s+VALUE",
    r"//",
)

# Level
LEVEL_PATTERN = re.compile(r"/L([1-5])(?:/|$)")

# Unit Code
CODE_PATTERNS = [
        # CON/PD/004/L2
        re.compile(
            r"^[A-Z]{2,5}/[A-Z0-9]{2,6}/\d{2,4}/L[1-5]$",
            re.IGNORECASE,
        ),

        # AGR/AEM/L1/001
        re.compile(
            r"^[A-Z]{2,5}/[A-Z0-9]{2,6}/L[1-5]/\d{2,4}$",
            re.IGNORECASE,
        ),

        # CONCJ/001/L3
        re.compile(
            r"^[A-Z]{4,8}/\d{2,4}/L[1-5]$",
            re.IGNORECASE,
        ),
]
# NBTE source PDFs sometimes use the letter 'O' instead of the digit '0'
# in unit codes (e.g. CBT/COS/OO4/L2). These are treated as possible OCR
# or source-document errors and reported as warnings rather than accepted
# as valid unit codes.

def add_issue(result: Dict[str, Any], severity: Literal['ERROR', 'WARNING'], rule: Any, message: str, location: str | None = None):
    issue = {
        "severity": severity,
        "rule": rule,
        "message": message,
        "location": location,
    }

    result["issues"].append(issue)

    if severity == ERROR:
        result["errors"] += 1
    elif severity == WARNING:
        result["warnings"] += 1

def is_valid(errors: int) -> bool:
    return errors == 0

def validate_file(path):
    data = load_json(path)

    result = {
        "file": str(path),
        "issues": [],
        "errors": 0,
        "warnings": 0,
    }

    # Call each rule in order
    validate_structure(data, result)
    validate_trade(data, result)
    validate_level(data, result)
    validate_unit_code(data, result)
    validate_learning_outcomes(data, result)
    validate_performance_criteria(data, result)
    validate_duplicates(data, result)
    validate_empty_descriptions(data, result)
    validate_empty_performance_criteria(data, result)

    return result

def load_json(path):
    path = Path(path)

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
    
def validate_structure(data, result, file = None):

        # ---------- Root ----------

        required_root = (
            "trade_name",
            "level",
            "units",
        )

        for key in required_root:
            if key not in data:
                add_issue(
                    result,
                    severity=ERROR,
                    rule='StructureRule',
                    message=f"Missing root key '{key}'.",
                )

        if "units" not in data:
            return

        if not isinstance(data["units"], list):
            add_issue(
                result,
                severity=ERROR,
                rule='StructureRule',
                message="'units' must be a list.",
            )
            return

        # ---------- Units ----------

        for unit_index, unit in enumerate(data["units"], start=1):

            required_unit = (
                "code",
                "title",
                "learning_outcomes",
            )

            for key in required_unit:
                if key not in unit:
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='StructureRule',
                        message=f"Missing unit key '{key}'.",
                        location=f"Unit {unit_index}",
                    )

            if "learning_outcomes" not in unit:
                continue

            if not isinstance(unit["learning_outcomes"], list):
                add_issue(
                    result,
                    severity=ERROR,
                    rule='StructureRule',
                    message="'learning_outcomes' must be a list.",
                    location=f"Unit {unit_index}",
                )
                continue

            # ---------- Learning Outcomes ----------

            for lo in unit["learning_outcomes"]:

                required_lo = (
                    "lo_num",
                    "description",
                    "performance_criteria",
                )

                for key in required_lo:
                    if key not in lo:
                        add_issue(
                            result,
                            severity=ERROR,
                            rule='StructureRule',
                            message=f"Missing learning outcome key '{key}'.",
                            location=f"Unit {unit_index}",
                        )

                if "performance_criteria" not in lo:
                    continue

                if not isinstance(lo["performance_criteria"], list):
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='StructureRule',
                        message="'performance_criteria' must be a list.",
                        location=f"Unit {unit_index}",
                    )
                    continue

                # ---------- Performance Criteria ----------

                for pc in lo["performance_criteria"]:

                    required_pc = (
                        "pc_code",
                        "description",
                    )

                    for key in required_pc:
                        if key not in pc:
                            add_issue(
                                result,
                                severity=ERROR,
                                rule='StructureRule',
                                message=f"Missing performance criteria key '{key}'.",
                                location=f"Unit {unit_index}",
                            )

def validate_trade(data, result, file = None):

        trade_name = data.get("trade_name")

        if trade_name is None:
            return

        if not isinstance(trade_name, str):
            add_issue(
                result,
                severity=ERROR,
                rule='TradeRule',
                message="'trade_name' must be a string.",
            )
            return

        trade_name = trade_name.strip()

        if not trade_name:
            add_issue(
                result,
                severity=ERROR,
                rule='TradeRule',
                message="Trade name is empty.",
            )
            return

        for pattern in _ARTIFACT_PATTERNS:
            if re.search(pattern, trade_name, re.IGNORECASE):
                add_issue(
                    result,
                    severity=WARNING,
                    rule='TradeRule',
                    message="Trade name appears to contain PDF extraction artifacts.",
                )
                break

def validate_level(data, result, file = None):

        document_level = data.get("level")

        if not isinstance(document_level, int):
            add_issue(
                result,
                severity=ERROR,
                rule='LevelRule',
                message="'level' must be an integer.",
            )
            return

        units = data.get("units", [])

        for unit_index, unit in enumerate(units, start=1):

            code = unit.get("code")

            if not isinstance(code, str):
                continue

            match = LEVEL_PATTERN.search(code)

            if match is None:
                continue

            unit_level = int(match.group(1))

            if unit_level != document_level:
                add_issue(
                    result,
                    severity=ERROR,
                    rule='LevelRule',
                    message=(
                            f"Unit level L{unit_level} does not match "
                            f"document level L{document_level}."
                        ),
                        location=f"Unit {unit_index}",
                )

def validate_unit_code(data, result, file = None):

        units = data.get("units", [])

        for unit_index, unit in enumerate(units, start=1):

            code = unit.get("code")

            if code is None:
                continue

            if not isinstance(code, str):
                add_issue(
                    result,
                    severity=ERROR,
                    rule='UnitCodeRule',
                    message="Unit code must be a string.",
                    location=f"Unit {unit_index}",
                )
                continue

            code = code.strip()

            if not code:
                add_issue(
                    result,
                    severity=ERROR,
                    rule='UnitCodeRule',
                    message="Unit code is empty.",
                    location=f"Unit {unit_index}",
                )
                continue

            if not any(pattern.fullmatch(code) for pattern in CODE_PATTERNS):
                add_issue(
                    result,
                    severity=ERROR,
                    rule='UnitCodeRule',
                    message=f"Invalid unit code format: '{code}'.",
                    location=f"Unit {unit_index}",
                )
            
            if re.search(r"/O+\d+/L", code):
                add_issue(
                    result,
                    severity=WARNING,
                    rule='UnitCodeRule',
                    message=(
                            f"Possible OCR error in unit code '{code}' "
                            "(letter 'O' used instead of zero)."
                        ),
                    location=f"Unit {unit_index}",
                )

def validate_learning_outcomes(data, result, file = None):

        units = data.get("units", [])

        for unit_index, unit in enumerate(units, start=1):

            learning_outcomes = unit.get("learning_outcomes", [])

            numbers = []

            for lo in learning_outcomes:

                lo_num = lo.get("lo_num")

                if lo_num is None:
                    continue

                try:
                    numbers.append(int(lo_num))
                except (TypeError, ValueError):
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='LearningOutcomesRule',
                        message=f"Invalid learning outcome number '{lo_num}'.",
                        location=f"Unit {unit_index}",
                    )

            if not numbers:
                continue

            expected = list(range(1, max(numbers) + 1))

            if numbers[0] != 1:
                add_issue(
                    result,
                    severity=ERROR,
                    rule='LearningOutcomesRule',
                    message="Learning outcomes must start at 1.",
                    location=f"Unit {unit_index}",
                )

            for expected_num in expected:
                if expected_num not in numbers:
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='LearningOutcomesRule',
                        message=f"Missing learning outcome number {expected_num}.",
                        location=f"Unit {unit_index}",
                    )

def validate_performance_criteria(data, result, file = None):

        units = data.get("units", [])

        for unit_index, unit in enumerate(units, start=1):

            learning_outcomes = unit.get("learning_outcomes", [])

            for lo in learning_outcomes:

                lo_num = lo.get("lo_num")

                try:
                    expected_lo = int(lo_num)
                except (TypeError, ValueError):
                    continue

                performance_criteria = lo.get("performance_criteria", [])

                numbers = []

                for pc in performance_criteria:

                    pc_code = pc.get("pc_code")

                    if not isinstance(pc_code, str):
                        continue

                    match = PC_PATTERN.fullmatch(pc_code.strip())

                    if match is None:
                        add_issue(
                            result,
                            severity=ERROR,
                            rule='PerformanceCriteriaRule',
                            message=f"Invalid performance criterion code '{pc_code}'.",
                            location=f"Unit {unit_index}, LO {expected_lo}",
                        )
                        continue

                    lo_part = int(match.group(1))
                    pc_part = int(match.group(2))

                    if lo_part != expected_lo:
                        add_issue(
                            result,
                            severity=ERROR,
                            rule='PerformanceCriteriaRule',
                            message=(
                                f"Performance criterion '{pc_code}' belongs "
                                f"to LO {lo_part}, expected LO {expected_lo}."
                            ),
                            location=f"Unit {unit_index}, LO {expected_lo}",
                        )
                        continue

                    numbers.append(pc_part)

                if not numbers:
                    continue

                if min(numbers) != 1:
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='PerformanceCriteriaRule',
                        message="Performance criteria must start at .1.",
                        location=f"Unit {unit_index}, LO {expected_lo}",
                    )

                expected = list(range(1, max(numbers) + 1))

                for expected_num in expected:
                    if expected_num not in numbers:
                        add_issue(
                            result,
                            severity=ERROR,
                            rule='PerformanceCriteriaRule',
                            message=(
                                    f"Missing performance criterion "
                                    f"{expected_lo}.{expected_num}."
                                ),
                            location=f"Unit {unit_index}, LO {expected_lo}",
                        )

def validate_duplicates(data, result, file = None):

        units = data.get("units", [])

        # ---------- Duplicate Unit Codes ----------

        seen_unit_codes = set()

        for unit_index, unit in enumerate(units, start=1):

            code = unit.get("code")

            if isinstance(code, str):

                if code in seen_unit_codes:
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='DuplicatesRule',
                        message=f"Duplicate unit code '{code}'.",
                        location=f"Unit {unit_index}",
                    )
                else:
                    seen_unit_codes.add(code)

        # ---------- Duplicate Learning Outcomes ----------

        for unit_index, unit in enumerate(units, start=1):

            learning_outcomes = unit.get("learning_outcomes", [])

            seen_lo_numbers = set()

            for lo in learning_outcomes:

                lo_num = lo.get("lo_num")

                if lo_num is None:
                    continue

                lo_num = str(lo_num)

                if lo_num in seen_lo_numbers:
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='DuplicatesRule',
                        message=f"Duplicate learning outcome '{lo_num}'.",
                        location=f"Unit {unit_index}",
                    )
                else:
                    seen_lo_numbers.add(lo_num)

                # ---------- Duplicate Performance Criteria ----------

                performance_criteria = lo.get("performance_criteria", [])

                seen_pc_codes = set()

                for pc in performance_criteria:

                    pc_code = pc.get("pc_code")

                    if pc_code is None:
                        continue

                    pc_code = str(pc_code)

                    if pc_code in seen_pc_codes:
                        add_issue(
                            result,
                            severity=ERROR,
                            rule='DuplicatesRule',
                            message=f"Duplicate performance criterion '{pc_code}'. Verify against the source PDF.",
                            location=f"Unit {unit_index}, LO {lo_num}",
                        )
                    else:
                        seen_pc_codes.add(pc_code)

def validate_empty_descriptions(data, result, file = None):

        # ---------- Trade Name ----------

        trade_name = data.get("trade_name")

        if isinstance(trade_name, str) and not trade_name.strip():
            add_issue(
                result,
                severity=WARNING,
                rule='EmptyDescriptionsRule',
                message="Trade name is empty.",
            )

        # ---------- Units ----------

        units = data.get("units", [])

        for unit_index, unit in enumerate(units, start=1):

            title = unit.get("title")

            if isinstance(title, str) and not title.strip():
                add_issue(
                    result,
                    severity=WARNING,
                    rule='EmptyDescriptionsRule',
                    message="Unit title is empty.",
                    location=f"Unit {unit_index}",
                )

            # ---------- Learning Outcomes ----------

            learning_outcomes = unit.get("learning_outcomes", [])

            for lo in learning_outcomes:

                lo_num = lo.get("lo_num", "?")

                description = lo.get("description")

                if isinstance(description, str) and not description.strip():
                    add_issue(
                        result,
                        severity=WARNING,
                        rule='EmptyDescriptionsRule',
                        message="Learning outcome description is empty.",
                        location=f"Unit {unit_index}, LO {lo_num}",
                    )

                # ---------- Performance Criteria ----------

                performance_criteria = lo.get("performance_criteria", [])

                for pc in performance_criteria:

                    pc_code = pc.get("pc_code", "?")

                    description = pc.get("description")

                    if isinstance(description, str) and not description.strip():
                        add_issue(
                            result,
                            severity=WARNING,
                            rule='EmptyDescriptionsRule',
                            message="Performance criterion description is empty.",
                            location=f"Unit {unit_index}, PC {pc_code}",
                        )

def validate_empty_performance_criteria(data, result, file = None):

        units = data.get("units", [])

        for unit_index, unit in enumerate(units, start=1):

            learning_outcomes = unit.get("learning_outcomes", [])

            for lo in learning_outcomes:

                lo_num = lo.get("lo_num", "?")

                performance_criteria = lo.get("performance_criteria")

                if isinstance(performance_criteria, list) and not performance_criteria:
                    add_issue(
                        result,
                        severity=ERROR,
                        rule='EmptyPerformanceCriteriaRule',
                        message="Learning outcome has no performance criteria.",
                        location=f"Unit {unit_index}, LO {lo_num}",
                    )

def print_report(result: Dict) -> str:
        lines = []

        lines.append(f"File: {result['file']}")
        lines.append("-" * 60)

        if is_valid(result['errors']):
            lines.append("Status : PASS")
        else:
            lines.append("Status : FAIL")

        lines.append(f"Errors   : {result['errors']}")
        lines.append(f"Warnings : {result['warnings']}")
        lines.append("")

        if result.get('issues'):
            lines.append("Issues")
            lines.append("-" * 60)

            for issue in result['issues']:
                location = f" [{issue['location']}]" if issue['location'] else ""

                lines.append(
                    f"{issue['severity']:<7} "
                    f"{issue['rule']}{location}: "
                    f"{issue['message']}"
                )

        return "\n".join(lines)

def iter_json_files(path):
    path = Path(path)

    if path.is_file():
        yield path
        return

    for json_file in sorted(path.rglob("*.json")):
        yield json_file

def main() -> int:

    parser = argparse.ArgumentParser(
        description="Validate extracted NOS JSON files."
    )

    parser.add_argument(
        "path",
        help="JSON file or directory to validate.",
    )

    args = parser.parse_args()

    total_files = 0
    total_errors = 0
    total_warnings = 0

    for path in iter_json_files(args.path):

        total_files += 1

        result = validate_file(str(path))

        total_errors += result['errors']
        total_warnings += result['warnings']

        print(print_report(result))
        print()

    print("=" * 60)
    print("Validation Summary")
    print("=" * 60)
    print(f"Files     : {total_files}")
    print(f"Errors    : {total_errors}")
    print(f"Warnings  : {total_warnings}")

    return 1 if total_errors else 0

if __name__ == "__main__":
    sys.exit(main())