"""
Token tracking utility for extracting and storing LLM token usage.
"""

from dataclasses import dataclass
from typing import Any
from psycopg.rows import dict_row
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Represents token usage from an LLM call."""
    input_tokens: int = 0
    output_tokens: int = 0
    
    def __add__(self, other: "TokenUsage") -> "TokenUsage":
        """Allows accumulating token usage with + operator."""
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens
        )
    
    def __iadd__(self, other: "TokenUsage") -> "TokenUsage":
        """Allows in-place accumulation with += operator."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        return self


def extract_tokens(response: Any) -> TokenUsage:
    """
    Extracts token count from a LangChain LLM response.
    
    Supports both Azure OpenAI and Vertex AI response formats:
    - Azure OpenAI: token_usage.prompt_tokens / completion_tokens
    - Vertex AI: usage_metadata.prompt_token_count / candidates_token_count
    """
    try:
        metadata = getattr(response, "response_metadata", {})
        
        # Formato Azure OpenAI / OpenAI
        token_usage = metadata.get("token_usage", {})
        if token_usage:
            input_tokens = token_usage.get("prompt_tokens", 0)
            output_tokens = token_usage.get("completion_tokens", 0)
            return TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
        
        # Fallback: Formato Vertex AI (legado)
        usage = metadata.get("usage_metadata", {})
        input_tokens = usage.get("prompt_token_count", 0)
        output_tokens = usage.get("candidates_token_count", 0)
        
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens
        )
    except Exception as e:
        logger.warning(f"Error extracting tokens from response: {e}")
        return TokenUsage()


async def upsert_thread_tokens(conn, thread_id: str, user_id: str, tokens: TokenUsage) -> None:
    """
    Inserts or updates (accumulates) token usage for a thread.
    
    Uses ON CONFLICT to add new tokens to existing values.
    """
    if tokens.input_tokens == 0 and tokens.output_tokens == 0:
        logger.debug(f"Skipping token upsert for thread {thread_id}: no tokens to save")
        return
    
    try:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO thread_tokens (thread_id, user_id, input_tokens, output_tokens)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (thread_id) DO UPDATE SET
                    input_tokens = thread_tokens.input_tokens + EXCLUDED.input_tokens,
                    output_tokens = thread_tokens.output_tokens + EXCLUDED.output_tokens,
                    updated_at = CURRENT_TIMESTAMP
            """, (thread_id, user_id, tokens.input_tokens, tokens.output_tokens))
        logger.info(f"Token usage saved for thread {thread_id}: +{tokens.input_tokens} input, +{tokens.output_tokens} output")
    except Exception as e:
        logger.error(f"Error saving token usage for thread {thread_id}: {e}", exc_info=True)
        # Don't raise - token tracking should not break main functionality


async def get_thread_tokens(conn, thread_id: str) -> TokenUsage:
    """
    Retrieves current token usage for a thread.
    Returns TokenUsage(0, 0) if thread not found.
    """
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT input_tokens, output_tokens FROM thread_tokens WHERE thread_id = %s",
                (thread_id,)
            )
            row = await cur.fetchone()
            if row:
                return TokenUsage(
                    input_tokens=row['input_tokens'] or 0,
                    output_tokens=row['output_tokens'] or 0
                )
    except Exception as e:
        logger.warning(f"Error fetching tokens for thread {thread_id}: {e}")
    
    return TokenUsage()
