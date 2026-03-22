from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import os
class PullRequestData(BaseModel):
    action: str
    pr_number: int
    pr_title: str
    pr_body: str | None
    pr_url: str
    pr_diff_url: str
    pr_author: str
    repo_name: str
    repo_url: str
    created_at: str
    owl_level: str

    pr_data: Optional[Dict[str, Any]] = None


class Finding(BaseModel):
    severity: str
    title: str
    details: str
    file: str | None = None
    line: int | None = None

    def to_markdown(self) -> str:
        """Format finding as markdown for GitHub comments."""
        severity_emoji = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🔵",
            "info": "ℹ️"
        }
        emoji = severity_emoji.get(self.severity.lower(), "⚠️")

        markdown = f"### {emoji} {self.severity.upper()}: {self.title}\n\n"
        markdown += f"{self.details}\n\n"

        if self.file:
            location = f"`{self.file}`"
            if self.line:
                location += f" (Line {self.line})"
            markdown += f"**Location:** {location}\n"

        return markdown


class ReviewResult(BaseModel):
    review_id: str = Field(default_factory=lambda: os.urandom(8).hex())
    repo_name: str
    pr_number: int
    pr_url: str
    summary: str
    findings: list[Finding]
    guideline_references: list[str] = Field(
        default_factory=lambda: [
            "Avoid secrets in code",
            "Add/adjust tests when behavior changes",
        ]
    )
    llm_meta: dict = Field(default_factory=dict)

    def to_github_comment(self) -> str:
        """Format the review result as a comprehensive GitHub comment."""
        lines = []

        # Header
        lines.append("# 🦉 PROwl Code Review")
        lines.append(f"**Review ID:** `{self.review_id}`")
        lines.append("")

        # Summary section
        lines.append("## 📋 Summary")
        lines.append(self.summary)
        lines.append("")


        if self.findings:
            lines.append("## 🔍 Findings")
            lines.append("")

            for finding in self.findings:
                lines.append(finding.to_markdown())
                lines.append("---")
                lines.append("")
        else:
            lines.append("## ✅ No Issues Found")
            lines.append("Great job! No significant issues were detected in this PR.")
            lines.append("")

        # Guidelines section
        if self.guideline_references:
            lines.append("## 📚 Guideline References")
            for guideline in self.guideline_references:
                lines.append(f"- {guideline}")
            lines.append("")

        # Metadata footer
        if self.llm_meta:
            lines.append("<details>")
            lines.append("<summary>🤖 Review Metadata</summary>")
            lines.append("")
            lines.append("```json")
            import json
            lines.append(json.dumps(self.llm_meta, indent=2))
            lines.append("```")
            lines.append("</details>")
            lines.append("")

        lines.append("---")
        lines.append("*Automated review powered by PROwl 🦉*")

        return "\n".join(lines)