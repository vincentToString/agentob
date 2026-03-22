from fastapi import APIRouter, HTTPException, Header, Request
from aio_pika import Message, DeliveryMode
from typing import Optional, Set
import json
import hmac
import hashlib
import logging
import uuid
from .redis_client import RedisClient
from .config import Config
from .models import PullRequestData
from .compression.models import FileChange, CompressionResult, CompressionConfig
from .compression.smart_strategy import SmartCompressionStrategy
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()
    
redis_client = RedisClient(Config.REDIS_URL)


@router.post("/webhook/github")
async def handle_github_webhook(
    request:Request,
    x_hub_signature_256: Optional[str]=Header(None),
    x_github_event:str = Header(...)
):
    if x_github_event != "pull_request":
        return {"message": f"Event {x_github_event} ignored"}
    
    payload_body = await request.body()

    if Config.GITHUB_WEBHOOK_SECRET:
        if not verify_signature(payload_body, x_hub_signature_256, Config.GITHUB_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid signature")
        

    webhook_data = json.loads(payload_body)

    if webhook_data.get("action") not in ["opened", "synchronize", "reopened"]:
        return {"message": f"PR action '{webhook_data.get('action')}' ignored"}
    
    owl_level = extract_owl_labels(webhook_data)
    logger.info(owl_level)
    if owl_level == "owl_ignore":
        return {"message": f"PR ignored as per requested"}
    

    repo_name = webhook_data["repository"]["full_name"]
    pr_number = webhook_data["number"]
    diff_content = await fetch_pr_diff(repo_name, pr_number)

    if not diff_content:
        logger.warning(f"Cannot Proceed without diff for PR #{webhook_data['number']}")
        diff_content = "Diff file unable to retrieve"
        return {"status": "error", "message": "Failed to fetch diff"}
    
    diff_id =  str(uuid.uuid4())

    pr_meta = webhook_data["pull_request"]
    repo_name = webhook_data["repository"]["full_name"]
    pr_number = pr_meta["number"]
    head_sha = pr_meta["head"]["sha"]



    diff = await smart_compress(repo_name, pr_number, head_sha, diff_content)

    diff_for_storage = {
        # Metadata
        "diff_id": diff_id,
        "repo_name": repo_name,
        "pr_number": pr_number,
        "head_sha": head_sha,
        
        # PR info
        "pr_title": pr_meta["title"],
        "pr_author": pr_meta["user"]["login"],
        "pr_url": pr_meta["html_url"],
        
        # Compression data (nested)
        "compression": diff.to_dict()
    }

    success = await redis_client.store_diff(diff_id, json.dumps(diff_for_storage))
    if not success:
        logger.error(f"Failed to store diff in Redis for {repo_name}#{pr_number}")
        return {"status": "error", "message": "Failed to store diff"}

    pr_data = PullRequestData(
        action=webhook_data["action"],
        pr_number=webhook_data["number"],
        pr_title=webhook_data["pull_request"]["title"],
        pr_body=webhook_data["pull_request"].get("body"),
        pr_url=webhook_data["pull_request"]["html_url"],
        pr_diff_url=webhook_data["pull_request"]["diff_url"],
        pr_author=webhook_data["pull_request"]["user"]["login"],
        repo_name=webhook_data["repository"]["full_name"],
        repo_url=webhook_data["repository"]["html_url"],
        created_at=webhook_data["pull_request"]["created_at"],
        owl_level=owl_level,
        diff_id = diff_id
    )
    channel = await request.app.state.rabbitmq_connection.channel()

    try:
        ai_exchange = await channel.get_exchange("ai_service")
        msg = Message(
            body=json.dumps(pr_data.model_dump()).encode("utf-8"),
            delivery_mode=DeliveryMode.PERSISTENT,
            headers={
                "repo": pr_data.repo_name,
                "pr_number": str(pr_data.pr_number)
            }
        )
        await ai_exchange.publish(msg, routing_key="pr")
        logger.info(f"Published PR#{pr_data.pr_number} to AI Service")
    except Exception as e:
        logger.error(f"Failed to publish to RabbitMQ: {e}")
        raise HTTPException(status_code=503, detail="Queue Unavailable")
    finally:
        # await redis_client.close()
        await channel.close()

    return {
        "status": "accepted",
        "pr_number": pr_data.pr_number,
        "action": "queued_for_processing"
    }

async def smart_compress(repo_name: str, pr_number: int, head_sha: str, diff_content: list[FileChange]) -> CompressionResult:
    config = CompressionConfig()
    compressor = SmartCompressionStrategy(config)
    return await compressor.compress(repo_name, pr_number, head_sha, diff_content)



async def fetch_pr_diff(repo: str, pr_number: int, timeout: int = 30) -> list[FileChange] | None:
    """fetch actual diff content"""
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    token = await Config.github_app_auth.get_installation_token()
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "PR-Owl-Bot"
    }


    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.get(api_url, headers=headers) as response:
                response.raise_for_status()
                files_data = await response.json()
                
                # Convert to FileChange objects
                pr_files = []
                for file_data in files_data:
                    pr_files.append(
                        FileChange(
                            path=file_data["filename"],
                            status=file_data["status"],
                            additions=file_data["additions"],
                            deletions=file_data["deletions"],
                            changes=file_data["changes"],
                            patch=file_data.get("patch", ""),
                            is_binary="patch" not in file_data
                        )
                    )
                
                logger.info(f"Fetched {len(pr_files)} files from GitHub API")
                
                # Warn if exactly 100 (might be truncated)
                if len(pr_files) == 100:
                    logger.warning(
                        f"PR #{pr_number} has exactly 100 files - "
                        "might be paginated, some files may be missing!"
                    )
                
                return pr_files
    
    except aiohttp.ClientResponseError as e:
        logger.error(f"HTTP error fetching files: {e.status} - {e.message}")
        return []
    except asyncio.TimeoutError:
        logger.error(f"Timeout fetching files after {timeout}s")
        return []
    except Exception as e:
        logger.error(f"Unexpected error fetching files: {e}")
        return []
    
# helper funtions
def verify_signature(payload_body: bytes, signature: str | None, secret: str) -> bool:
    """Verify GitHub webhook signature"""
    if not signature or not secret:
        return False
    
    hash_object = hmac.new(
        secret.encode('utf-8'),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature)

def extract_owl_labels(webhook_data: dict) -> str:
    """
    Extract the PR review level from labels
    
    Returns:
        Single owl level string (e.g., "owl_quick", "owl_ignore")
        Returns "owl_standard" if no owl label found (default)
    
    Priority order (if multiple labels):
        1. owl_ignore (highest - skip review)
        2. owl_deep (TODO)
        3. owl_standard
        4. owl_quick
    """
    labels = webhook_data.get("pull_request", {}).get("labels", [])
    
    if labels is None:
        return "owl_quick"  # Default
    
    # Extract all owl labels
    owl_labels = set()
    for label in labels:
        if not isinstance(label, dict):
            continue
        
        name = label.get("name", "")
        if name.startswith("owl_"):
            owl_labels.add(name)
    
    if "owl_ignore" in owl_labels:
        return "owl_ignore"
    elif "owl_deep" in owl_labels:
        return "owl_deep"
    elif "owl_standard" in owl_labels:
        return "owl_standard"
    elif "owl_quick" in owl_labels:
        return "owl_quick"
    else:
        return "owl_quick"  

