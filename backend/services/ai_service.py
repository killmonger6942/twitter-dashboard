import json
from typing import Optional

from google import genai
from google.genai import types

from backend.config import settings

client = genai.Client(api_key=settings.gemini_api_key)


TWEET_CATEGORIES = {
    "observation": "Write a casual observation about patterns you've noticed in AI/LLM usage — something a developer would notice from daily use",
    "hot_take": "Write a mildly spicy, contrarian opinion about AI tools, workflows, or the AI industry — something that might get quote-tweeted",
    "question": "Write an engaging question to your followers about their experience with AI tools, prompting, or building with LLMs",
    "tip": "Share a practical tip or technique about prompt engineering, token optimization, or working with LLMs effectively",
    "personal_experience": "Write a short 'I just...' or 'spent the morning...' story about your experience building with or using AI tools",
    "meta": "Write a philosophical or big-picture observation about AI, language models, or how they're changing software development",
}


async def generate_categorized_tweet(
    system_prompt: str,
    category: str,
) -> str:
    direction = TWEET_CATEGORIES.get(category, TWEET_CATEGORIES["observation"])
    tweets = await generate_tweets(system_prompt, direction=direction, count=1)
    return tweets[0] if tweets else ""


async def generate_reply(
    system_prompt: str,
    tweet_text: str,
    author_handle: str,
) -> str:
    user_msg = (
        f"Someone (@{author_handle}) just tweeted:\n\n"
        f'"{tweet_text}"\n\n'
        "Write a reply that is either 1 word or 1 short sentence max. "
        "Examples: 'facts', 'this', 'exactly lol', 'been there', 'underrated take', 'the debugging part hits hard'. "
        "Casual and low-effort like a friend reacting in a group chat. "
        "No hashtags, no emojis unless ironic. Return ONLY the reply text, nothing else."
    )
    response = client.models.generate_content(
        model=settings.content_model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=user_msg)])],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.9,
            max_output_tokens=256,
        ),
    )
    text = (response.text or "").strip().strip('"')
    return text[:280]


async def generate_tweets(
    system_prompt: str,
    direction: Optional[str] = None,
    count: int = 3,
) -> list[str]:
    user_msg = f"Generate exactly {count} tweet drafts."
    if direction:
        user_msg += f" Topic/direction: {direction}"
    user_msg += (
        "\n\nReturn ONLY a JSON array of strings, no markdown, no backticks. "
        "Each tweet must be under 280 characters. Make each one distinct in angle or framing."
    )

    response = client.models.generate_content(
        model=settings.content_model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=user_msg)])],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.9,
            max_output_tokens=1024,
        ),
    )

    text = (response.text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()

    tweets = json.loads(text)
    return [t for t in tweets if isinstance(t, str) and len(t) <= 280]


async def generate_persona(description: str) -> dict:
    user_msg = (
        f"Create a Twitter persona based on this description:\n\n"
        f'"{description}"\n\n'
        "Return ONLY a JSON object with these exact fields:\n"
        '{\n'
        '  "name": "short catchy persona name (2-4 words)",\n'
        '  "tone": "describe the voice and tone in a phrase",\n'
        '  "topics": ["topic1", "topic2", "topic3", "topic4", "topic5"],\n'
        '  "style_guide": "2-3 sentences describing how this persona writes, what makes their voice unique, and any quirks",\n'
        '  "posting_frequency": "X-Y per day",\n'
        '  "example_tweets": ["tweet1", "tweet2", "tweet3", "tweet4", "tweet5"]\n'
        '}\n\n'
        "Rules for the persona:\n"
        "- Example tweets must be under 280 characters each\n"
        "- Example tweets should feel authentic, not generic or corporate\n"
        "- Topics should be specific enough to guide content but broad enough for variety\n"
        "- The tone should be distinctive and memorable\n"
        "- Never include specific AI model names (GPT-4, Claude, etc.) in examples\n"
        "- No hashtags or emojis in example tweets\n"
        "Return ONLY the JSON, no markdown, no backticks."
    )

    response = client.models.generate_content(
        model=settings.content_model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=user_msg)])],
        config=types.GenerateContentConfig(
            temperature=0.9,
            max_output_tokens=1024,
        ),
    )

    text = (response.text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()

    return json.loads(text)
