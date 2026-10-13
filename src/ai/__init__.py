"""AI provider package re-exporting client, contexts, and schemas."""
from src.ai.client import AIClient
from src.ai.context import estimate_tokens, repair_context, text_sources
from src.ai.prompts import ANALYSIS_PROMPT, EDIT_PROMPT, FACTS_POLICY, REPAIR_PROMPT
from src.ai.schemas import ANALYSIS_SCHEMA, EDIT_SCHEMA, REPAIR_SCHEMA, object_schema, validate_json
from src.exceptions import ProviderError
from src.models import EditResult

__all__ = [
    "AIClient",
    "ProviderError",
    "EditResult",
    "object_schema",
    "validate_json",
    "text_sources",
    "repair_context",
    "estimate_tokens",
    "ANALYSIS_SCHEMA",
    "EDIT_SCHEMA",
    "REPAIR_SCHEMA",
    "ANALYSIS_PROMPT",
    "EDIT_PROMPT",
    "REPAIR_PROMPT",
    "FACTS_POLICY",
]
