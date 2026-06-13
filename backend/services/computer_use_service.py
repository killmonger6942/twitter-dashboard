import json
import time
from datetime import datetime
from typing import Optional

from google import genai
from google.genai import types

from backend.config import settings
from backend.models.database import ComputerUseLog, async_session
from backend.services import browser_service

client = genai.Client(api_key=settings.gemini_api_key)

SYSTEM_PROMPT = (
    "You are an AI controlling a Chromium browser to perform Twitter/X actions. "
    "The browser is already logged into a Twitter account.\n\n"
    "Each turn you receive:\n"
    "1. A screenshot of the current page\n"
    "2. A numbered list of interactive elements on the page with their labels\n\n"
    "Respond with EXACTLY ONE JSON object (no markdown, no backticks, no extra text):\n\n"
    '- Click an element: {"action": "click", "element_id": 5}\n'
    '- Type text (into the currently focused/clicked input): {"action": "type", "text": "hello"}\n'
    '- Press a key: {"action": "key", "key": "Enter"}\n'
    '- Scroll down: {"action": "scroll", "direction": "down"}\n'
    '- Task complete: {"action": "done", "message": "what was accomplished"}\n'
    '- Task failed: {"action": "error", "message": "what went wrong"}\n\n'
    "Rules:\n"
    "- First click an input/textarea element, THEN type into it in the next step.\n"
    "- After typing a tweet, look for and click the Post/Tweet button.\n"
    "- If the same action doesn't work twice, try a different approach.\n"
    "- Only output the JSON object, nothing else."
)


def _parse_action(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if '"done"' in text:
            return {"action": "done", "message": text[:200]}
        if '"error"' in text:
            return {"action": "error", "message": text[:200]}
        raise


def _format_elements(elements: list) -> str:
    lines = []
    for el in elements:
        lines.append(f"[{el['id']}] {el['label']}")
    return "\n".join(lines)


async def run_task(
    account_id: str,
    username: str,
    task_description: str,
    max_iterations: Optional[int] = None,
) -> dict:
    if max_iterations is None:
        max_iterations = settings.max_computer_use_iterations

    start_time = time.time()
    total_input_tokens = 0
    total_output_tokens = 0
    actions_count = 0

    screenshot_b64 = await browser_service.take_screenshot_b64(account_id, username)
    elements = await browser_service.get_interactive_elements(account_id, username)

    history = []
    final_text = ""
    success = False
    last_action = None

    for iteration in range(max_iterations):
        elements_text = _format_elements(elements)

        if iteration == 0:
            user_parts = [
                types.Part.from_text(text=f"Task: {task_description}\n\nInteractive elements on page:\n{elements_text}"),
                types.Part.from_bytes(
                    data=__import__("base64").b64decode(screenshot_b64),
                    mime_type="image/png",
                ),
                types.Part.from_text(text="What action should I take? Respond with JSON only."),
            ]
        else:
            user_parts = [
                types.Part.from_text(text=f"Action executed. Updated interactive elements:\n{elements_text}"),
                types.Part.from_bytes(
                    data=__import__("base64").b64decode(screenshot_b64),
                    mime_type="image/png",
                ),
                types.Part.from_text(text="What next? JSON only."),
            ]

        history.append(types.Content(role="user", parts=user_parts))

        response = client.models.generate_content(
            model=settings.computer_use_model,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

        if response.usage_metadata:
            total_input_tokens += response.usage_metadata.prompt_token_count or 0
            total_output_tokens += response.usage_metadata.candidates_token_count or 0

        response_text = response.text or ""
        history.append(types.Content(role="model", parts=[types.Part.from_text(text=response_text)]))

        print(f"[iter {iteration}] Gemini: {response_text[:200]}", flush=True)

        try:
            action = _parse_action(response_text)
        except (json.JSONDecodeError, ValueError):
            print(f"[iter {iteration}] Parse failed: {response_text[:200]}", flush=True)
            final_text = f"Failed to parse AI response: {response_text[:200]}"
            break

        action_type = action.get("action")
        print(f"[iter {iteration}] Action: {action}", flush=True)

        if action == last_action:
            hint = types.Content(
                role="user",
                parts=[types.Part.from_text(
                    text="That's the same action as last time and it didn't work. Try a different element or approach."
                )],
            )
            history.append(hint)
            last_action = action
            continue

        last_action = action

        if action_type == "done":
            final_text = action.get("message", "Task completed")
            success = True
            break
        elif action_type == "error":
            final_text = action.get("message", "Task failed")
            break
        elif action_type == "click":
            element_id = action.get("element_id")
            el = next((e for e in elements if e["id"] == element_id), None)
            if el:
                await browser_service.click_element(account_id, username, el["x"], el["y"])
            else:
                print(f"[iter {iteration}] Element {element_id} not found", flush=True)
        elif action_type == "type":
            text = action.get("text", "")
            await browser_service.type_text(account_id, username, text)
        elif action_type == "key":
            key = action.get("key", "Enter")
            await browser_service.press_key(account_id, username, key)
        elif action_type == "scroll":
            direction = action.get("direction", "down")
            await browser_service.scroll_page(account_id, username, direction)

        actions_count += 1

        import asyncio
        await asyncio.sleep(1)

        screenshot_b64 = await browser_service.take_screenshot_b64(account_id, username)
        elements = await browser_service.get_interactive_elements(account_id, username)

    duration_ms = int((time.time() - start_time) * 1000)

    flash_input_cost = total_input_tokens * 0.15 / 1_000_000
    flash_output_cost = total_output_tokens * 0.60 / 1_000_000
    cost_cents = (flash_input_cost + flash_output_cost) * 100

    async with async_session() as session:
        log_entry = ComputerUseLog(
            account_id=account_id,
            task=task_description[:200],
            actions_count=actions_count,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            cost_cents=cost_cents,
            success=success,
            duration_ms=duration_ms,
            created_at=datetime.utcnow(),
        )
        session.add(log_entry)
        await session.commit()

    return {
        "success": success,
        "message": final_text,
        "actions_count": actions_count,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "cost_cents": round(cost_cents, 4),
        "duration_ms": duration_ms,
    }
