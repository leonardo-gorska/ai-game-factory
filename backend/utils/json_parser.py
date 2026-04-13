"""
Gorvax Game Factory — Shared JSON parser for LLM responses.

Replaces duplicated _parse_* methods across all agents with a single
robust implementation that handles markdown code fences correctly.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_json_from_response(
    response: str,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract JSON from an LLM response, handling markdown code fences.

    Tries in order:
      1. Last ```json ... ``` block (most likely the final answer)
      2. Last generic ``` ... ``` block
      3. Raw JSON parse of the entire response
      4. Smart JS extraction (for developer agent responses)
      5. Returns *fallback* dict (or a minimal error dict)

    Using the **last** matching block avoids a common LLM pattern where
    the model "thinks aloud" in earlier blocks before producing output.
    """

    # 1. Try ```json blocks — pick the last one that parses
    json_blocks = re.findall(r"```json\s*(.*?)```", response, re.DOTALL)
    if json_blocks:
        for block in reversed(json_blocks):
            try:
                result = json.loads(block.strip())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

    # 2. Try generic ``` blocks (that could be JSON)
    code_blocks = re.findall(r"```\s*(.*?)```", response, re.DOTALL)
    if code_blocks:
        for block in reversed(code_blocks):
            try:
                result = json.loads(block.strip())
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                continue

    # 3. Try raw JSON parse
    try:
        result = json.loads(response)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 4. Try to fix common JSON issues (trailing commas, unescaped newlines)
    cleaned = _try_fix_json(response)
    if cleaned is not None:
        return cleaned

    # 5. Smart JS extraction — build a files array from ```javascript blocks
    js_result = _extract_js_files_from_response(response)
    if js_result:
        logger.info(
            "JSON parse failed but extracted %d JS file(s) from code blocks",
            len(js_result["files"]),
        )
        return js_result

    # 6. Fallback
    logger.warning(
        "Could not parse JSON from LLM response (len=%d). First 200 chars: %s",
        len(response),
        response[:200],
    )
    if fallback is not None:
        return fallback
    return {"raw_response": response[:500], "error": "Could not parse JSON from LLM response"}


def _try_fix_json(response: str) -> dict[str, Any] | None:
    """Try to fix common JSON issues from LLM responses."""
    # Find the outermost { ... } in the response
    first_brace = response.find("{")
    last_brace = response.rfind("}")
    if first_brace == -1 or last_brace == -1 or first_brace >= last_brace:
        return None

    candidate = response[first_brace:last_brace + 1]

    # Fix trailing commas before } or ]
    candidate = re.sub(r',\s*([\]}])', r'\1', candidate)

    # Fix single quotes → double quotes (careful with JS content)
    # Only do this if it looks like it doesn't contain JS code
    if "function" not in candidate and "=>" not in candidate:
        candidate = candidate.replace("'", '"')

    try:
        result = json.loads(candidate)
        if isinstance(result, dict):
            logger.info("Fixed JSON by extracting {..} and removing trailing commas")
            return result
    except json.JSONDecodeError:
        pass

    return None


def _extract_js_files_from_response(response: str) -> dict[str, Any] | None:
    """Extract JavaScript code blocks and infer file paths from context.

    When the LLM returns JavaScript code blocks instead of the expected JSON
    format, this function tries to salvage the code and create proper file
    entries.
    """
    # Find all JavaScript code blocks with optional filename hints
    # Pattern: ```javascript or ```js, optionally preceded by a filename/path
    js_blocks: list[tuple[str, str]] = []

    # Try to find blocks with filename hints like:
    # ### src/main.js
    # ```javascript
    # ... code ...
    # ```
    pattern = re.compile(
        r'(?:#{1,4}\s*`?([^\n`]+\.js)`?\s*\n)?'  # optional heading with .js filename
        r'```(?:javascript|js)\s*\n(.*?)```',
        re.DOTALL,
    )
    for match in pattern.finditer(response):
        filename = match.group(1)
        content = match.group(2).strip()
        if not content:
            continue

        if filename:
            # Clean up the filename
            filename = filename.strip().strip("`").strip()
            # Ensure it starts with src/
            if not filename.startswith("src/") and not filename.startswith("game/"):
                filename = f"src/{filename}"
        else:
            # Try to infer filename from content
            filename = _infer_filename_from_js(content)

        js_blocks.append((filename, content))

    if not js_blocks:
        return None

    files = []
    for path, content in js_blocks:
        files.append({
            "path": path,
            "action": "create",
            "content": content,
        })

    return {
        "summary": "Code extracted from JavaScript blocks (JSON parse failed)",
        "files": files,
        "dependencies_changed": False,
        "build_notes": "Auto-extracted from code blocks",
    }


def _infer_filename_from_js(content: str) -> str:
    """Try to infer a filename from JavaScript content."""
    content_lower = content[:500].lower()

    # Check for Phaser game config patterns
    if "phaser.game" in content_lower or "type: phaser" in content_lower:
        return "src/main.js"
    if "phaser.scene" in content_lower or "extends phaser.scene" in content_lower:
        # Try to get class name
        class_match = re.search(r'class\s+(\w+)', content)
        if class_match:
            name = class_match.group(1)
            return f"src/scenes/{name}.js"
        return "src/scenes/MainScene.js"

    # Check for config/constants
    if "export const config" in content_lower or "export default {" in content_lower:
        return "src/config.js"

    # Check for class definitions
    class_match = re.search(r'class\s+(\w+)', content)
    if class_match:
        name = class_match.group(1)
        if "system" in name.lower():
            return f"src/systems/{name}.js"
        if "scene" in name.lower():
            return f"src/scenes/{name}.js"
        return f"src/entities/{name}.js"

    # Default
    return "src/game.js"
