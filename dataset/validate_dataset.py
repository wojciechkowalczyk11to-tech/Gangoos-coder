#!/usr/bin/env python3
"""
Validation script for execution_traces_v2.jsonl dataset.
Checks format, structure, and content integrity.
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple


class DatasetValidator:
    """Validates execution traces dataset."""

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.traces: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def load_traces(self) -> bool:
        """Load and parse JSONL file."""
        if not self.filepath.exists():
            self.errors.append(f"File not found: {self.filepath}")
            return False

        try:
            with open(self.filepath, 'r') as f:
                for i, line in enumerate(f, 1):
                    try:
                        trace = json.loads(line)
                        self.traces.append(trace)
                    except json.JSONDecodeError as e:
                        self.errors.append(f"Line {i}: Invalid JSON - {e}")
                        return False
        except IOError as e:
            self.errors.append(f"File read error: {e}")
            return False

        return True

    def validate_structure(self) -> bool:
        """Validate trace structure."""
        required_keys = {"messages", "category", "language", "success", "timestamp"}

        for i, trace in enumerate(self.traces, 1):
            trace_id = f"Trace {i}"

            # Check required keys
            missing = required_keys - set(trace.keys())
            if missing:
                self.errors.append(f"{trace_id}: Missing keys {missing}")
                return False

            # Validate messages
            if not isinstance(trace["messages"], list):
                self.errors.append(f"{trace_id}: messages is not a list")
                return False

            if len(trace["messages"]) < 3:
                self.errors.append(
                    f"{trace_id}: Expected at least 3 messages, got {len(trace['messages'])}"
                )
                return False

            # Validate message structure
            for j, msg in enumerate(trace["messages"]):
                if "role" not in msg or "content" not in msg:
                    self.errors.append(
                        f"{trace_id}, message {j}: Missing role or content"
                    )
                    return False

                if msg["role"] not in {"system", "user", "assistant"}:
                    self.errors.append(
                        f"{trace_id}, message {j}: Invalid role '{msg['role']}'"
                    )
                    return False

            # Validate other fields
            if not isinstance(trace["success"], bool):
                self.errors.append(f"{trace_id}: success is not boolean")
                return False

            if trace["language"] not in {"python", "bash"}:
                self.errors.append(f"{trace_id}: Invalid language '{trace['language']}'")
                return False

            valid_categories = {
                "mcp_tools",
                "python_coding",
                "shell_devops",
                "api_integration",
                "error_handling",
                "multi_step",
            }
            if trace["category"] not in valid_categories:
                self.warnings.append(
                    f"{trace_id}: Unknown category '{trace['category']}'"
                )

        return True

    def validate_content(self) -> bool:
        """Validate message content."""
        for i, trace in enumerate(self.traces, 1):
            trace_id = f"Trace {i}"
            messages = trace["messages"]

            # Check for empty content
            for j, msg in enumerate(messages):
                if not msg["content"] or not msg["content"].strip():
                    self.warnings.append(f"{trace_id}, message {j}: Empty content")

            # Validate first message is system
            if messages[0]["role"] != "system":
                self.warnings.append(f"{trace_id}: First message should be system role")

            # Validate alternating user/assistant
            for j in range(1, len(messages)):
                if j == 1:
                    if messages[j]["role"] != "user":
                        self.warnings.append(
                            f"{trace_id}: Second message should be user role"
                        )
                elif j == 2:
                    if messages[j]["role"] != "assistant":
                        self.warnings.append(
                            f"{trace_id}: Third message should be assistant role"
                        )

            # Check for code in assistant messages
            assistant_count = sum(1 for m in messages if m["role"] == "assistant")
            if assistant_count == 0:
                self.errors.append(f"{trace_id}: No assistant code generation found")
                return False

            # Check for output in user messages
            last_user_msg = None
            for msg in reversed(messages):
                if msg["role"] == "user":
                    last_user_msg = msg["content"]
                    break

            if last_user_msg and len(last_user_msg) < 10:
                self.warnings.append(
                    f"{trace_id}: Last user message seems too short (likely incomplete)"
                )

        return True

    def analyze_statistics(self) -> Dict[str, Any]:
        """Analyze dataset statistics."""
        stats = {
            "total_traces": len(self.traces),
            "total_messages": sum(len(t["messages"]) for t in self.traces),
            "categories": {},
            "languages": {},
            "success_rate": 0,
        }

        for trace in self.traces:
            cat = trace["category"]
            lang = trace["language"]
            stats["categories"][cat] = stats["categories"].get(cat, 0) + 1
            stats["languages"][lang] = stats["languages"].get(lang, 0) + 1

        if self.traces:
            successes = sum(1 for t in self.traces if t["success"])
            stats["success_rate"] = successes / len(self.traces)

        # Analyze message lengths
        total_content_length = 0
        for trace in self.traces:
            for msg in trace["messages"]:
                total_content_length += len(msg["content"])

        stats["average_content_per_message"] = (
            total_content_length / stats["total_messages"] if stats["total_messages"] > 0 else 0
        )

        return stats

    def validate(self) -> Tuple[bool, Dict[str, Any]]:
        """Run complete validation."""
        print("Validating execution traces dataset...")
        print("=" * 70)

        # Load traces
        if not self.load_traces():
            print("FAILED: Could not load traces")
            return False, {}

        print(f"Loaded {len(self.traces)} traces")

        # Validate structure
        if not self.validate_structure():
            print("FAILED: Structure validation failed")
            return False, {}

        print("Structure validation: PASSED")

        # Validate content
        if not self.validate_content():
            print("FAILED: Content validation failed")
            return False, {}

        print("Content validation: PASSED")

        # Analyze statistics
        stats = self.analyze_statistics()

        return True, stats

    def print_report(self, valid: bool, stats: Dict[str, Any]):
        """Print validation report."""
        print("\n" + "=" * 70)
        print("VALIDATION REPORT")
        print("=" * 70)

        if valid:
            print("\nStatus: PASSED ✓")
        else:
            print("\nStatus: FAILED ✗")

        if self.errors:
            print(f"\nErrors ({len(self.errors)}):")
            for error in self.errors[:5]:  # Show first 5
                print(f"  - {error}")
            if len(self.errors) > 5:
                print(f"  ... and {len(self.errors) - 5} more")

        if self.warnings:
            print(f"\nWarnings ({len(self.warnings)}):")
            for warning in self.warnings[:5]:  # Show first 5
                print(f"  - {warning}")
            if len(self.warnings) > 5:
                print(f"  ... and {len(self.warnings) - 5} more")

        if stats:
            print("\nStatistics:")
            print(f"  Total traces: {stats['total_traces']}")
            print(f"  Total messages: {stats['total_messages']}")
            print(f"  Average message length: {stats['average_content_per_message']:.0f} chars")
            print(f"  Success rate: {stats['success_rate']*100:.1f}%")

            print("\n  Categories:")
            for cat, count in sorted(stats["categories"].items()):
                pct = (count / stats["total_traces"]) * 100
                print(f"    {cat}: {count} ({pct:.0f}%)")

            print("\n  Languages:")
            for lang, count in sorted(stats["languages"].items()):
                pct = (count / stats["total_traces"]) * 100
                print(f"    {lang}: {count} ({pct:.0f}%)")

        print("\n" + "=" * 70)


def main():
    """Main function."""
    filepath = "/sessions/loving-beautiful-mccarthy/Gangoos-coder/dataset/execution_traces_v2.jsonl"

    validator = DatasetValidator(filepath)
    valid, stats = validator.validate()
    validator.print_report(valid, stats)

    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
