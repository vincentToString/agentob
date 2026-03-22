import asyncio
from aio_pika.abc import AbstractIncomingMessage
import aio_pika
from aio_pika import Message, DeliveryMode
import os, json, argparse
from pathlib import Path
import orjson
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import logging
import signal
import boto3
import base64
from ai_service.models import PullRequestData, ReviewResult, Finding
from ai_service.config import Config
from ai_service.redis_client import RedisClient
from typing import Tuple, List, Dict
import boto3
from botocore.config import Config as BotoCoreConfig
from botocore.exceptions import BotoCoreError, ClientError
import re
from .heartbeat import WorkerHealthState, heartbeat_loop
import socket



logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BEDROCK_SYSTEM_PROMPT = "You are a precise code review assistant. Return ONLY JSON."

redis_client = RedisClient(Config.REDIS_URL)


async def handle_message(message: AbstractIncomingMessage, channel):
    async with message.process(requeue=False):  # manual ack
        event_dict = json.loads(message.body.decode("utf-8"))

        diff_id = event_dict.get("diff_id")

        if diff_id:
            logger.info(f"Retrieved diff from Redis with id{diff_id}")
            diff_content = await redis_client.get_diff(diff_id)
            # pr_data is a Dict (RedisClient converts JSON string → dict)

            if not diff_content:
                logger.error(f"Diff {diff_id} not found in Redis")
                return

            event_dict["pr_data"] = diff_content
        else:
            logger.error(f"Diff id not presented, failed")
            return

        result = await process_event(
            event_dict,
            prompt_path=Path(__file__).parent / "prompt.md",
            bedrock_model_id=Config.BEDROCK_MODEL_ID,
            aws_region=Config.AWS_REGION,
            llm_timeout=Config.LLM_TIMEOUT,
            max_files=Config.MAX_FILES,
            max_lines=Config.MAX_LINES,
        )

        # Legacy OpenRouter version
        #
        # result = process_event(
        #     event_dict,
        #     prompt_path=Path(__file__).parent / "prompt.md",
        #     model=Config.MODEL,
        #     base_url=Config.OPENROUTER_BASE,
        #     api_key=Config.OPENROUTER_API_KEY,
        #     llm_timeout=Config.LLM_TIMEOUT,
        #     max_files=Config.MAX_FILES,
        #     max_lines=Config.MAX_LINES,
        # )

        # if diff_id:
        #     await redis_client.delete_diff(diff_id)
        #     logger.info(f"Deleted diff {diff_id} from Redis")

        out_exchange = await channel.get_exchange("out_exchange")
        msg = Message(
            body=orjson.dumps(result.model_dump()),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={"repo": result.repo_name, "pr_number": result.pr_number},
        )
        await out_exchange.publish(msg, routing_key="")
        logger.info(
            "Published review result for %s PR#%s", result.repo_name, result.pr_number
        )


async def process_event(
    event_dict: dict,
    *,
    prompt_path: Path,
    bedrock_model_id: str,
    aws_region: str,
    llm_timeout: int,
    max_files: int,
    max_lines: int,
) -> ReviewResult:
    event = PullRequestData.model_validate(event_dict)
    if not event.pr_data:
        logger.error(f"Receiving PR #{event.pr_number}has no diff content available")
        raise Exception(f"Invalid PR to review: #{event.pr_number}")
    files, snippets = parse_compressed_diff(
        event.pr_data, max_files=max_files, max_lines_per_file=max_lines
    )

    if not files or not snippets:
        logger.error(f"No files or snippets parsed for PR #{event.pr_number}")
        raise Exception(f"Failed to parse diff for PR #{event.pr_number}")

    logger.info(
        f"Parsed {len(files)} files and {len(snippets)} snippets "
        f"for {event.repo_name} PR#{event.pr_number}"
    )
    prompt_template = load_prompt_template(prompt_path)
    rag_context = ""
    if event.owl_level == "owl_standard":
        # Fetch RAG context
        rag_context = await fetch_rag_context(files, event.pr_title, event.pr_body or "")
    prompt = render_prompt(prompt_template, event, files, snippets, rag_context)
    logger.info(prompt)
    llm_response = call_bedrock(
        prompt,
        model_id=bedrock_model_id,
        region=aws_region,
        timeout_s=llm_timeout,
    )

    # Legacy OpenRouter version
    #
    # llm_response = call_openrouter(
    #     prompt,
    #     model=model,
    #     base_url=base_url,
    #     api_key=api_key,
    #     timeout_s=llm_timeout,
    # )

    findings = [
        Finding.model_validate(finding)
        for finding in (llm_response.get("findings") or [])
    ]

    return ReviewResult(
        repo_name=event.repo_name,
        pr_number=event.pr_number,
        pr_url=event.pr_url,
        summary=(llm_response.get("summary") or "").strip(),
        findings=findings,
        guideline_references=[
            "Avoid secrets in code",
            "Add/adjust tests when behavior changes",
        ],
        llm_meta={
            "provider": "bedrock",
            "model": bedrock_model_id,
            "region": aws_region,
            "owl_level": event.owl_level
        },
    )



# Helper:
def parse_diff(diff_text: str, max_files: int, max_lines_per_file: int):
    """
    Parse unified diff into file metadata and code snippets.

    Args:
        diff_text: Raw unified diff from GitHub
        max_files: Maximum number of files to return
        max_lines_per_file: Maximum lines per file snippet

    Returns:
        (files, snippets):
            - files: List of {filename, additions, deletions}
            - snippets: List of {filename, added_text, removed_text}
    """
    # Validation
    if not diff_text or not diff_text.strip():
        logger.warning("Empty diff provided")
        return [], []

    files = []
    snippets = []

    # Current file state
    current_file = None
    additions = 0
    deletions = 0
    added_lines = []
    removed_lines = []

    # Files to ignore (generated, minified, lock files)
    SKIP_PATTERNS = (
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "uv.lock",
        ".min.js",
        ".min.css",
        "dist/",
        "build/",
    )

    def should_skip_file(filename: str) -> bool:
        """Check if file should be excluded from review"""
        return any(pattern in filename for pattern in SKIP_PATTERNS)

    def save_file_data():
        """Save current file's data to results"""
        nonlocal current_file, additions, deletions, added_lines, removed_lines

        if current_file is None:
            return

        # Always save file metadata
        files.append(
            {
                "filename": current_file,
                "additions": additions,
                "deletions": deletions,
            }
        )

        # Only save snippets for non-noisy files with actual changes
        if not should_skip_file(current_file) and (added_lines or removed_lines):
            snippets.append(
                {
                    "filename": current_file,
                    "added_text": "\n".join(added_lines[:max_lines_per_file]),
                    "removed_text": "\n".join(removed_lines[:max_lines_per_file]),
                }
            )

        # Reset state for next file
        current_file = None
        additions = 0
        deletions = 0
        added_lines = []
        removed_lines = []

    # Parse diff line by line
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            # New file header - save previous file and reset
            save_file_data()
            current_file = None

        elif line.startswith("+++ b/"):
            # Extract filename (new version)
            current_file = line[6:].strip()  # Skip "+++ b/"

        elif line.startswith("--- a/"):
            # Old version filename - ignore
            pass

        elif line.startswith("@@"):
            # Hunk header - ignore
            pass

        else:
            # Only process if we have a current file
            if current_file is None:
                continue

            # Added line
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
                added_lines.append(line[1:])  # Remove '+' prefix

            # Deleted line
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
                removed_lines.append(line[1:])  # Remove '-' prefix

            # Context line (no prefix) - ignore for now

    # Don't forget the last file!
    save_file_data()

    # Sort by total impact (additions + deletions)
    files.sort(key=lambda f: f["additions"] + f["deletions"], reverse=True)

    # Select top N most-changed files
    top_files = files[:max_files]
    selected_filenames = {f["filename"] for f in top_files}

    # Filter snippets to only include top files
    top_snippets = [s for s in snippets if s["filename"] in selected_filenames][
        :max_files
    ]

    logger.info(
        f"Parsed {len(files)} files, "
        f"selected {len(top_files)} top files, "
        f"{len(top_snippets)} snippets for review"
    )

    return top_files, top_snippets


def parse_compressed_diff(
    diff_compressed: dict, max_files: int, max_lines_per_file: int
) -> Tuple[List[Dict], List[Dict]]:
    compression = diff_compressed.get("compression", {})

    if not compression:
        logger.error("No compressed diff file found")
        return [], []

    files_data = compression.get("files", [])
    if not files_data:
        logger.error("No file data found")
        return [], []

    files = []
    snippets = []

    full_tier = files_data.get("full", [])
    logger.info(f"Processing {len(full_tier)} full-tier files")

    for file_data in full_tier[:max_files]:
        files.append(
            {
                "filename": file_data["path"],
                "additions": file_data["additions"],
                "deletions": file_data["deletions"],
                "status": file_data["status"],
                "language": file_data["language"],
                "is_critical": file_data["is_critical"],
                "importance_score": file_data["importance_score"],
            }
        )

        patch = file_data.get("patch", "")

        if not patch:
            logger.warning(f"No patch found for {file_data['path']}")
            continue

        added_lines = []
        removed_lines = []

        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append(line[1:])  # Remove '+' prefix
            # Removed line
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines.append(line[1:])  # Remove '-' prefix

        snippets.append(
            {
                "filename": file_data["path"],
                "added_text": "\n".join(added_lines[:max_lines_per_file]),
                "removed_text": "\n".join(removed_lines[:max_lines_per_file]),
                "is_critical": file_data.get("is_critical", False),
                "language": file_data.get("language", "unknown"),
            }
        )

    remaining_slots = max_files - len(files)

    if remaining_slots > 0:
        summary_tier = files_data.get("summary", [])
        logger.info(
            f"Processing {len(summary_tier)} summary-tier files (limit: {remaining_slots})"
        )

        for file_data in summary_tier[:remaining_slots]:
            files.append(
                {
                    "filename": file_data["path"],
                    "additions": file_data["additions"],
                    "deletions": file_data["deletions"],
                    "status": file_data["status"],
                    "language": file_data["language"],
                    "is_critical": file_data["is_critical"],
                    "importance_score": file_data["importance_score"],
                }
            )

            # Summary tier doesn't have patch, provide metadata-only placeholder
            snippets.append(
                {
                    "filename": file_data["path"],
                    "added_text": f"[Summary only: +{file_data['additions']} lines added]",
                    "removed_text": f"[Summary only: -{file_data['deletions']} lines removed]",
                    "is_critical": file_data["is_critical"],
                    "language": file_data["language"],
                    "note": "Full diff excluded due to token limits",
                }
            )

    # ==========================================
    # Process LISTED-TIER files (just log them)
    # ==========================================
    listed_tier = files_data.get("listed", [])

    if listed_tier:
        # ✅ FIXED: listed_tier is List[str], not List[Dict]
        logger.info(
            f"{len(listed_tier)} files listed but not included in review: "
            f"{', '.join(listed_tier[:5])}"
            f"{'...' if len(listed_tier) > 5 else ''}"
        )

        # Note: We don't add these to files/snippets lists
        # They're just for logging/stats purposes

    logger.info(
        f"Parsed compressed diff: {len(files)} files, "
        f"{len(snippets)} snippets for review "
        f"(strategy: {compression.get('strategy', 'unknown')})"
    )

    return files, snippets


async def fetch_rag_context(
    files: list[dict], pr_title: str, pr_body: str = ""
) -> list[dict]:

    if not Config.RAG_ENABLED:
        logger.info("RAG is disabled, skipping context retrieval")
        return []

    try:
        # Build query from PR context
        languages = set(f.get("language", "").lower() for f in files if f.get("language"))
        languages.discard("")
        languages.discard("unknown")

        # Check if any critical files
        has_critical = any(f.get("is_critical", False) for f in files)

        # Build contextual query
        query_parts = [pr_title]
        if pr_body:
            query_parts.append(pr_body[:200])  # First 200 chars of description
        if languages:
            query_parts.append(f"languages: {', '.join(languages)}")
        if has_critical:
            query_parts.append("security critical")

        query = " ".join(query_parts)

        logger.info(f"RAG query: {query[:100]}... (languages: {languages})")

        # Call RAG service
        async with httpx.AsyncClient(timeout=Config.RAG_TIMEOUT) as client:
            response = await client.post(
                f"{Config.RAG_SERVICE_URL}/api/v1/vector-index/query",
                json={"query": query, "top_k": Config.RAG_TOP_K},
            )

            if response.status_code == 200:
                data = response.json()
                chunks = data.get("chunks", [])
                logger.info(
                    f"RAG retrieved {len(chunks)} chunks (top scores: "
                    f"{[round(c.get('score', 0), 2) for c in chunks[:3]]})"
                )
                return chunks
            else:
                logger.warning(
                    f"RAG service returned {response.status_code}: {response.text[:100]}"
                )
                return []

    except httpx.TimeoutException:
        logger.warning(f"RAG service timeout after {Config.RAG_TIMEOUT}s")
        return []
    except Exception as e:
        logger.error(f"RAG service error: {e}")
        return []


def load_prompt_template(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"Prompt file not found: {path.resolve()}")


def render_prompt(
    prompt_template: str,
    event: PullRequestData,
    files: list[dict],
    snippets: list[dict],
    rag_context: list[dict] = None,
) -> str:
    rag_context = rag_context or []
    return (
        prompt_template.replace("{{repo_name}}", event.repo_name)
        .replace("{{pr_number}}", str(event.pr_number))
        .replace("{{pr_title}}", event.pr_title)
        .replace("{{pr_author}}", event.pr_author)
        .replace("{{pr_body}}", (event.pr_body or "")[:1000])
        .replace("{{files_table}}", build_files_table(files))
        .replace("{{snippets}}", build_snippets_block(snippets))
        .replace("{{rag_context}}", build_rag_context_block(rag_context))
    )


# def render_prompt(
#     template: str,
#     event: PullRequestData,
#     files: List[Dict],
#     snippets: List[Dict]
# ) -> str:
#     """
#     Render prompt template with PR data

#     Enhanced to include compression metadata if available
#     """

#     # Build file list
#     file_list = []
#     for f in files:
#         critical_marker = "🔴 " if f.get("is_critical") else ""
#         score = f.get("importance_score", 0)

#         file_list.append(
#             f"{critical_marker}{f['filename']} "
#             f"(+{f['additions']}/-{f['deletions']}) "
#             f"[{f.get('language', 'unknown')}]"
#             f"{f' [score: {score:.1f}]' if score > 0 else ''}"
#         )

#     # Build code snippets
#     code_changes = []
#     for snippet in snippets:
#         critical_marker = "🔴 CRITICAL: " if snippet.get("is_critical") else ""
#         note = snippet.get("note", "")

#         section = f"### {critical_marker}{snippet['filename']}"
#         if note:
#             section += f"\n_{note}_"
#         section += "\n\n"

#         if snippet.get("added_text"):
#             section += f"**Added:**\n```{snippet.get('language', '')}\n{snippet['added_text']}\n```\n\n"

#         if snippet.get("removed_text"):
#             section += f"**Removed:**\n```{snippet.get('language', '')}\n{snippet['removed_text']}\n```\n\n"

#         code_changes.append(section)

#     # Fill template
#     rendered = template.format(
#         repo_name=event.repo_name,
#         pr_number=event.pr_number,
#         pr_title=event.pr_title,
#         pr_author=event.pr_author,
#         pr_body=event.pr_body or "(No description)",
#         file_count=len(files),
#         file_list="\n".join(file_list),
#         code_changes="\n".join(code_changes),
#     )

#     return rendered


def call_bedrock(
    prompt_text: str,
    *,
    model_id: str,
    region: str,
    timeout_s: int,
    temperature: float = 0.5,
    max_tokens: int = 4096,
) -> dict:
    if not model_id:
        raise RuntimeError("BEDROCK_MODEL_ID is not configured")

    client = boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=BotoCoreConfig(
            read_timeout=timeout_s,
            connect_timeout=timeout_s,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )

    # Detect model provider and format request accordingly
    # Support both direct model IDs (anthropic.) and inference profiles (us.anthropic., global.anthropic.)
    is_anthropic = model_id.startswith("anthropic.") or "anthropic" in model_id

    if is_anthropic:
        # Claude/Anthropic format using Messages API
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": BEDROCK_SYSTEM_PROMPT,
            "messages": [
                {
                    "role": "user",
                    "content": prompt_text
                }
            ]
        }
    else:
        # Meta Llama format
        body = {
            "prompt": build_meta_prompt(prompt_text),
            "max_gen_len": max_tokens,
            "temperature": temperature,
            "top_p": 0.9,
        }

    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Bedrock invocation failed")
        raise RuntimeError("Bedrock invocation failed") from exc

    payload_bytes = response["body"].read()
    payload = json.loads(payload_bytes)

    # Parse response based on provider
    if is_anthropic:
        # Claude response format
        content_blocks = payload.get("content", [])
        completion_text = content_blocks[0].get("text", "") if content_blocks else ""
    else:
        # Meta Llama response format
        completion_text = (
            payload.get("generation")
            or payload.get("output_text")
            or payload.get("completion")
        )

    if not completion_text:
        outputs = payload.get("outputs") or []
        if outputs:
            completion_text = outputs[0].get("text") or (
                outputs[0].get("content") or [{}]
            )[0].get("text")

    if not completion_text:
        logger.error("Bedrock response missing completion text: %s", payload)
        raise RuntimeError("Bedrock response missing completion text")

    try:
        completion_text = completion_text.strip()
        # Remove markdown code fences if present
        completion_text = re.sub(r'^```(?:json)?\s*\n?', '', completion_text)
        completion_text = re.sub(r'\n?```\s*$', '', completion_text)

        # Try to parse the JSON
        try:
            return json.loads(completion_text)
        except json.JSONDecodeError as parse_error:
            # Claude often generates literal newlines in JSON strings instead of \n
            # Try to fix by using a more lenient JSON parser or fixing common issues
            logger.warning(
                "Initial JSON parse failed (error: %s), attempting repair...",
                str(parse_error)
            )

            # Attempt to repair: Fix unescaped newlines within JSON string values
            # This is a heuristic approach - look for patterns like: "text\nmore text"
            # and replace with: "text\\nmore text"
            # Log the problematic JSON for debugging
            logger.error(
                "JSON parse failed at char %s. First 1000 chars:\n%s\n\nLast 1000 chars:\n%s",
                str(parse_error).split("char ")[-1].split(")")[0] if "char" in str(parse_error) else "unknown",
                completion_text[:1000],
                completion_text[-1000:] if len(completion_text) > 1000 else ""
            )

            # Save full response to temp file for debugging
            try:
                with open("/tmp/bedrock_response.json", "w") as f:
                    f.write(completion_text)
                logger.info("Saved full response to /tmp/bedrock_response.json")
            except Exception:
                pass

            try:
                # Try a more aggressive approach: escape ALL literal newlines, tabs, etc. in the entire response
                # before trying to parse JSON strings
                logger.info("Attempting aggressive JSON repair...")

                # First, try to find the JSON object boundaries
                # Claude might have added text before or after the JSON
                start_idx = completion_text.find('{')
                end_idx = completion_text.rfind('}')

                if start_idx == -1 or end_idx == -1:
                    raise ValueError("No JSON object found in response")

                json_text = completion_text[start_idx:end_idx + 1]

                # Now repair the JSON by properly escaping strings
                # We need to be more careful - only escape newlines that are inside string values
                # Strategy: Find each string value and escape special characters within it

                repaired = []
                i = 0
                in_string = False
                escape_next = False

                while i < len(json_text):
                    char = json_text[i]

                    if escape_next:
                        # We're after a backslash - keep the char as-is
                        repaired.append(char)
                        escape_next = False
                        i += 1
                        continue

                    if char == '\\':
                        # Start of escape sequence
                        repaired.append(char)
                        escape_next = True
                        i += 1
                        continue

                    if char == '"' and not escape_next:
                        # Toggle string state (only if not escaped)
                        repaired.append(char)
                        in_string = not in_string
                        i += 1
                        continue

                    if in_string:
                        # Inside a string - escape special characters that aren't already escaped
                        if char == '\n':
                            repaired.append('\\')
                            repaired.append('n')
                        elif char == '\r':
                            repaired.append('\\')
                            repaired.append('r')
                        elif char == '\t':
                            repaired.append('\\')
                            repaired.append('t')
                        else:
                            repaired.append(char)
                    else:
                        repaired.append(char)

                    i += 1

                repaired_text = ''.join(repaired)

                # Save repaired version for debugging
                try:
                    with open("/tmp/bedrock_response_repaired.json", "w") as f:
                        f.write(repaired_text)
                    logger.info("Saved repaired response to /tmp/bedrock_response_repaired.json")
                except Exception:
                    pass

                result = json.loads(repaired_text)
                logger.info("Successfully parsed JSON after aggressive repair")
                return result

            except Exception as repair_error:
                logger.error("All repair attempts failed: %s", str(repair_error))
                raise RuntimeError(f"Bedrock completion was not valid JSON: {parse_error}") from parse_error
    except json.JSONDecodeError as exc:
        logger.error("Bedrock completion was not valid JSON: %s", completion_text[:1000])
        raise RuntimeError("Bedrock completion was not valid JSON") from exc


# Legacy OpenRouter helper
def call_openrouter(
    prompt_text: str, model: str, base_url: str, api_key: str, timeout_s: int
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pr-demo.local",
        "X-Title": "AI PR Reviewer Demo",
    }

    body = {
        "model": model,
        "temperature": 0.5,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a precise code review assistant. Return ONLY JSON.",
            },
            {"role": "user", "content": prompt_text},
        ],
    }

    with httpx.Client(timeout=timeout_s, base_url=base_url) as client:
        response = client.post("/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def build_meta_prompt(user_prompt: str) -> str:
    """Format prompt for Meta Llama instruction models on Bedrock."""
    return (
        "<|begin_of_text|>"
        "<|start_header_id|>system<|end_header_id|>\n"
        f"{BEDROCK_SYSTEM_PROMPT}\n"
        "<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n"
        f"{user_prompt}\n"
        "<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n"
    )


def build_files_table(files: list[dict]) -> str:
    return (
        "\n".join(
            f'{file_info["filename"]} +{file_info["additions"]}/-{file_info["deletions"]}'
            for file_info in files
        )
        or "(no files parsed)"
    )


def build_snippets_block(snippets: list[dict]) -> str:
    if not snippets:
        return "(no change snippets)"

    blocks = []
    for snippet in snippets:
        parts = [f"--- file: {snippet['filename']}"]

        added_text = snippet.get("added_text") or ""
        removed_text = snippet.get("removed_text") or ""

        if added_text:
            parts.append("\n".join("+" + line for line in added_text.splitlines()))
        if removed_text:
            parts.append("\n".join("-" + line for line in removed_text.splitlines()))

        blocks.append("\n".join(parts))

    return "\n".join(blocks)


def build_rag_context_block(rag_chunks: list[dict]) -> str:
    if not rag_chunks:
        return "(no additional context available)"

    blocks = []
    for idx, chunk in enumerate(rag_chunks, 1):
        content = chunk.get("content", "").strip()
        score = chunk.get("score", 0.0)
        doc_title = chunk.get("document_title", "")

        if content:
            header = f"[{idx}] Relevance: {score:.2f}"
            if doc_title:
                header += f" | Source: {doc_title}"

            blocks.append(f"{header}\n{content}")

    return "\n\n".join(blocks) if blocks else "(no additional context available)"

def _default_instance_id() -> str:
    return os.getenv("HOSTNAME") or socket.gethostname() or "unknown"

async def main():
    state =  WorkerHealthState()
    instance_id = _default_instance_id()

    hb_task = asyncio.create_task(
        heartbeat_loop(
            redis=redis_client,
            state=state,
            service_name="ai_service",
            instance_id=instance_id,
            interval_s=10,
        ), 
        name=f"heartbeat:ai_service:{instance_id}",

    )
    conn = await aio_pika.connect_robust(Config.RABBITMQ_URL)
    channel = await conn.channel()
    await state.set_connected(True)

    await channel.set_qos(prefetch_count=1)

    pr_queue = await channel.declare_queue("pr_review", durable=True)

    stop_event = asyncio.Event()

    async def consumer(msg: AbstractIncomingMessage):
        await state.on_msg_start()
        try:
            await handle_message(msg, channel)
            await state.on_msg_ok()
        except Exception as e:
            logger.exception("Error processing message: %s", e)
            await state.on_msg_error()
        finally:
            await state.on_msg_done()

    await pr_queue.consume(consumer)
    logger.info("AI service consuming from pr_review queue")

    def _stop(*_):
        logger.info("Shut down")
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
