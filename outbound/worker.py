import asyncio
import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta

from aio_pika import connect_robust
from aio_pika.abc import AbstractIncomingMessage
import aiohttp
import jwt
from dotenv import load_dotenv
from outbound.worker_heartbeat import WorkerHealthState, heartbeat_loop, _default_instance_id
from outbound.redis_client import RedisClient


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

def format_finding_markdown(finding: dict) -> str:
    """Format a single finding as markdown for GitHub comments."""
    severity_emoji = {
        "critical": "🔴",
        "high": "🟠",
        "medium": "🟡",
        "low": "🔵",
        "info": "ℹ️"
    }
    severity = finding.get("severity", "").lower()
    emoji = severity_emoji.get(severity, "⚠️")

    markdown = f"### {emoji} {severity.upper()}: {finding.get('title', 'N/A')}\n\n"
    markdown += f"{finding.get('details', '')}\n\n"

    if finding.get("file"):
        location = f"`{finding['file']}`"
        if finding.get("line"):
            location += f" (Line {finding['line']})"
        markdown += f"**Location:** {location}\n"

    return markdown


def format_github_comment(data: dict) -> str:
    """Format review result as a comprehensive GitHub comment."""
    lines = []

    # Header
    lines.append("# 🦉 PROwl Code Review")
    lines.append(f"**Review ID:** `{data.get('review_id', 'N/A')}`")
    lines.append("")

    # Summary section
    lines.append("## 📋 Summary")
    lines.append(data.get("summary", "No summary available"))
    lines.append("")


    # if findings:
    #     # Group findings by severity
    #     severity_order = ["critical", "high", "medium", "low", "info"]
    #     findings_by_severity = {}
    #     for finding in findings:
    #         sev = finding.get("severity", "").lower()
    #         if sev not in findings_by_severity:
    #             findings_by_severity[sev] = []
    #         findings_by_severity[sev].append(finding)

    #     lines.append("## 🔍 Findings")
    #     lines.append("")

    #     total = len(findings)
    #     severity_counts = {sev: len(findings_by_severity.get(sev, [])) for sev in severity_order}
    #     lines.append(f"**Total Issues Found:** {total}")

    #     # Show severity breakdown
    #     breakdown = " | ".join([f"{sev.capitalize()}: {count}" for sev, count in severity_counts.items() if count > 0])
    #     lines.append(f"**Breakdown:** {breakdown}")
    #     lines.append("")
    #     lines.append("---")
    #     lines.append("")

    #     # Output findings grouped by severity
    #     for severity in severity_order:
    #         if severity in findings_by_severity:
    #             for finding in findings_by_severity[severity]:
    #                 lines.append(format_finding_markdown(finding))
    #                 lines.append("---")
    #                 lines.append("")
    # else:
    #     lines.append("## ✅ No Issues Found")
    #     lines.append("Great job! No significant issues were detected in this PR.")
    #     lines.append("")

    # Findings section
    findings = data.get("findings", [])
    if findings:
        lines.append("## 🔍 Findings")
        lines.append("")

        for finding in findings:
            lines.append(format_finding_markdown(finding))
            lines.append("---")
            lines.append("")
    else:
        lines.append("## ✅ No Issues Found")
        lines.append("Great job! No significant issues were detected in this PR.")
        lines.append("")

    # Guidelines section
    guideline_refs = data.get("guideline_references", [])
    if guideline_refs:
        lines.append("## 📚 Guideline References")
        for guideline in guideline_refs:
            lines.append(f"- {guideline}")
        lines.append("")

    # Metadata footer
    llm_meta = data.get("llm_meta", {})
    if llm_meta:
        lines.append("<details>")
        lines.append("<summary>🤖 Review Metadata</summary>")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(llm_meta, indent=2))
        lines.append("```")
        lines.append("</details>")
        lines.append("")

    lines.append("---")
    lines.append("*Automated review powered by PROwl 🦉*")

    return "\n".join(lines)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("outbound-worker")

RABBITMQ_URL = os.getenv('RABBITMQ_URL')



# ----------------------
# GitHub App Authentication
# ----------------------






# ----------------------
# Message Handlers
# ----------------------

async def handle_github(msg: AbstractIncomingMessage):
    """Handle PR review result and post to GitHub as a comment."""
    async with msg.process(requeue=False):
        data = json.loads(msg.body.decode("utf-8"))

        # No dependency on ai_service models - work directly with dict
        repo = data.get("repo_name")
        pr = data.get("pr_number")

        # Use standalone formatting function
        review_body = format_github_comment(data)

        log.info(f"Posting formatted review to GitHub PR#{pr} in {repo}")
        log.debug(f"Review preview:\n{review_body[:500]}...")

        




# ----------------------
# Worker Main Loop
# ----------------------

async def main():
    state = WorkerHealthState()
    redis_client = RedisClient(REDIS_URL)
    instance_id = _default_instance_id()

    hb_task = asyncio.create_task(
        heartbeat_loop(
            redis=redis_client,
            state=state,
            service_name="outbound",
            instance_id=instance_id,
            interval_s=5,
            ttl_s=15,
            max_errors=10,
            max_stuck_s=120,
            metadata={
                "queues": ["github_comments", "slack_msgs"],
                "worker": "outbound",
            },
        ),
        name=f"heartbeat:outbound:{instance_id}",
    )

    conn = await connect_robust(RABBITMQ_URL)
    ch = await conn.channel()
    await ch.set_qos(prefetch_count=5)

    await state.set_connected(True)

    github_q = await ch.declare_queue("github_comments", durable=True)
    slack_q = await ch.declare_queue("slack_msgs", durable=True)

    # ----------------------
    # Github Wrapper
    # ----------------------
    async def github_consumer(msg: AbstractIncomingMessage):
        await state.on_msg_start()
        try:
            await handle_github(msg)
            await state.on_msg_ok()
        except Exception:
            await state.on_msg_error()
            raise
        finally:
            await state.on_msg_done()

    await github_q.consume(github_consumer)
    # await slack_q.consume(handle_slack)

    log.info("Outbound worker consuming from github_comments and slack_msgs queues...")

    stop_event = asyncio.Event()

    def _stop(*_):
        log.info("Shutdown signal received.")
        stop_event.set()

    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(s, _stop)
        except NotImplementedError:
            pass

    await stop_event.wait()

    hb_task.cancel()
    try:
        await hb_task
    except asyncio.CancelledError:
        pass

    await redis_client.close()
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
