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
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "./github-app-private-key.pem")
GITHUB_INSTALLATION_ID = os.getenv("GITHUB_INSTALLATION_ID")


# ----------------------
# GitHub App Authentication
# ----------------------

class GitHubAppAuth:
    def __init__(self, app_id: str, private_key_path: str, installation_id: str):
        self.app_id = app_id
        self.installation_id = installation_id
        
        # Read private key
        with open(private_key_path, 'r') as f:
            self.private_key = f.read()
        
        self._token = None
        self._token_expires_at = None
    
    def _generate_jwt(self) -> str:
        """Generate JWT to authenticate as the GitHub App"""
        payload = {
            'iat': int(time.time()),
            'exp': int(time.time()) + 600,  # JWT expires in 10 minutes
            'iss': self.app_id
        }
        return jwt.encode(payload, self.private_key, algorithm='RS256')
    
    async def get_installation_token(self) -> str:
        """Get installation access token (cached)"""
        # Return cached token if still valid
        if self._token and self._token_expires_at and datetime.now() < self._token_expires_at:
            return self._token
        
        # Generate new token
        jwt_token = self._generate_jwt()
        
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'PR-Owl-Bot'
        }
        
        url = f'https://api.github.com/app/installations/{self.installation_id}/access_tokens'
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers) as response:
                response.raise_for_status()
                data = await response.json()
                
                self._token = data['token']
                # Tokens expire in 1 hour, refresh 5 min early
                self._token_expires_at = datetime.now() + timedelta(minutes=55)
                
                log.info("GitHub App installation token refreshed")
                return self._token
if not GITHUB_APP_ID or not GITHUB_INSTALLATION_ID:
    raise ValueError("GITHUB_APP_ID and GITHUB_INSTALLATION_ID must be set")

# Initialize GitHub App Auth
github_auth = GitHubAppAuth(
    app_id=GITHUB_APP_ID,
    private_key_path=GITHUB_PRIVATE_KEY_PATH,
    installation_id=GITHUB_INSTALLATION_ID
)




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

        # Get fresh installation token
        token = await github_auth.get_installation_token()

        url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "PR-Owl-Bot"
        }

        async with aiohttp.ClientSession() as session:
            resp = await session.post(url, headers=headers, json={"body": review_body})
            if resp.status != 201:
                text = await resp.text()
                log.error(f"GitHub API error {resp.status}: {text}")
                raise RuntimeError(f"GitHub API error {resp.status}")


# async def handle_slack(msg: AbstractIncomingMessage):
#     """Handle PR review result and post to Slack channel."""
#     async with msg.process(ignore_processed=True):
#         try:
#             data = json.loads(msg.body.decode("utf-8"))
#             repo = data["repo_name"]
#             pr = data["pr_number"]
#             review_summary = data.get("summary", "[no summary]")

#             log.info(f"Sending Slack notification for PR#{pr} in {repo}: {review_summary}")

#             url = "https://slack.com/api/chat.postMessage"
#             headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
#             payload = {"channel": "#code-reviews", "text": review_summary}

#             async with aiohttp.ClientSession() as session:
#                 resp = await session.post(url, headers=headers, json=payload)
#                 if resp.status != 200:
#                     text = await resp.text()
#                     log.error(f"Slack API error {resp.status}: {text}")

#         except Exception as e:
#             log.error("Failed to handle Slack message: %s", e, exc_info=True)
#             await msg.nack(requeue=False)


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
