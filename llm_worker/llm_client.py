import httpx
import logging
from llm_worker.config import Config

logger = logging.getLogger(__name__)

async def generate_summary(prompt: str) -> str:
    """
    Call OpenRouter API to generate summary based on the provided prompt.
    Args:
        prompt: The prompt string to send to the LLM.
    Returns:
        The generated summary string.
    Raises:
        httpx.HTTPError: If the API call fails.
    """
    headers = {
        "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agentob.local",
        "X-Title": "AgentOB - Run Summary Generator",
    }
    payload = {
        "model": Config.MODEL,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "reasoning": {"enabled": True}
    }
    last_error = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=Config.LLM_TIMEOUT) as client:
                response = await client.post(
                    f"{Config.OPENROUTER_BASE}",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                summary = data["choices"][0]["message"]["content"].strip()
                logger.info(f"[OK] Generated summary ({len(summary)} chars) on attempt {attempt + 1}")
                return summary
        
        except httpx.TimeoutException as e:
            last_error = f"Timeout after {Config.LLM_TIMEOUT}s"
            logger.warning(f"LLM timeout on attempt {attempt + 1}/3")
        
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}: {e.response.text[:100]}"
            logger.warning(f"LLM HTTP error on attempt {attempt + 1}/3: {last_error}")
        
        except Exception as e:
            last_error = str(e)
            logger.warning(f"LLM error on attempt {attempt + 1}/3: {e}")
    
    # All retries failed
    raise Exception(f"Failed to generate summary after 3 attempts: {last_error}")

