import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Account, Persona, get_db

router = APIRouter(prefix="/api/personas", tags=["personas"])


class PersonaRequest(BaseModel):
    name: str
    tone: str = ""
    topics: list[str] = []
    style_guide: str = ""
    posting_frequency: str = "3-5 per day"
    example_tweets: list[str] = []


class PersonaResponse(BaseModel):
    id: str
    name: str
    tone: str
    topics: list[str]
    style_guide: str
    posting_frequency: str
    example_tweets: list[str]
    system_prompt: str
    created_at: str


def _compile_system_prompt(p: PersonaRequest) -> str:
    topics_str = ", ".join(p.topics) if p.topics else "general"
    examples_str = "\n".join(f'- "{t}"' for t in p.example_tweets) if p.example_tweets else "No examples provided."

    return (
        f"You are a social media content creator with the following identity:\n\n"
        f"VOICE AND TONE: {p.tone}\n\n"
        f"TOPICS OF EXPERTISE: {topics_str}\n\n"
        f"STYLE GUIDE:\n{p.style_guide}\n\n"
        f"POSTING FREQUENCY: {p.posting_frequency}\n\n"
        f"EXAMPLE TWEETS (match this style):\n{examples_str}\n\n"
        f"RULES:\n"
        f"- Never break character\n"
        f"- Match the length and cadence of the example tweets\n"
        f"- Stay within the defined topic areas\n"
        f"- Tweets must be under 280 characters unless creating a thread\n"
        f"- Be authentic and engaging, not generic or corporate\n\n"
        f"CRITICAL CONTENT RULES:\n"
        f"- NEVER mention specific model names or versions (no 'GPT-4', 'Claude 3.5', 'Gemini 2.0', 'Llama 3', etc.)\n"
        f"- NEVER reference specific dates, years, product launches, or news events\n"
        f"- Use generic terms: 'the latest models', 'modern LLMs', 'current generation', 'the model I've been using'\n"
        f"- Focus on perpetual topics: token optimization, prompt engineering, building with AI, developer experience, AI in workflows, inference costs, local vs cloud tradeoffs\n"
        f"- Your tweets should read the same whether someone sees them today or six months from now\n\n"
        f"REPOST RULES:\n"
        f"- Only repost content related to your topics of expertise\n"
        f"- Repost things that your persona would genuinely find interesting or agree with\n"
        f"- Good reposts: practical AI/dev insights, interesting benchmarks, open-source releases, thoughtful takes on AI tooling\n"
        f"- Never repost: hype/shill content, crypto/NFT, political drama, engagement bait threads, anything with specific model version comparisons that will date quickly\n"
        f"- Prefer reposting from smaller accounts and genuine builders over big influencer accounts\n\n"
        f"LIKE RULES:\n"
        f"- Like generously but stay on-topic — AI, dev tools, software engineering, tech observations\n"
        f"- Like content you would reply to or repost, plus adjacent topics (startup life, developer humor, productivity)\n"
        f"- Do not like: promotional/ad content, outrage bait, unrelated topics (sports, politics, celebrity gossip)\n\n"
        f"REPLY RULES:\n"
        f"- Only reply to tweets within your topic areas\n"
        f"- Replies must be either 1 word or 1 short sentence — nothing longer\n"
        f"- Good replies: 'facts', 'this', 'exactly lol', 'been there', 'underrated take', 'how long did that take you', 'the debugging part hits hard'\n"
        f"- Never reply with: multiple sentences, generic praise ('great thread!'), unsolicited advice, anything that sounds automated\n"
        f"- Match the energy of the original tweet — casual and low-effort, like a friend reacting in a group chat"
    )


def _to_response(p: Persona) -> PersonaResponse:
    return PersonaResponse(
        id=p.id,
        name=p.name,
        tone=p.tone,
        topics=json.loads(p.topics) if p.topics else [],
        style_guide=p.style_guide,
        posting_frequency=p.posting_frequency,
        example_tweets=json.loads(p.example_tweets) if p.example_tweets else [],
        system_prompt=p.system_prompt,
        created_at=p.created_at.isoformat() if p.created_at else "",
    )


@router.get("")
async def list_personas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Persona).order_by(Persona.created_at))
    return [_to_response(p) for p in result.scalars().all()]


@router.post("")
async def create_persona(req: PersonaRequest, db: AsyncSession = Depends(get_db)):
    persona = Persona(
        name=req.name,
        tone=req.tone,
        topics=json.dumps(req.topics),
        style_guide=req.style_guide,
        posting_frequency=req.posting_frequency,
        example_tweets=json.dumps(req.example_tweets),
        system_prompt=_compile_system_prompt(req),
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return _to_response(persona)


@router.put("/{persona_id}")
async def update_persona(persona_id: str, req: PersonaRequest, db: AsyncSession = Depends(get_db)):
    persona = await db.get(Persona, persona_id)
    if not persona:
        raise HTTPException(404, "Persona not found")

    persona.name = req.name
    persona.tone = req.tone
    persona.topics = json.dumps(req.topics)
    persona.style_guide = req.style_guide
    persona.posting_frequency = req.posting_frequency
    persona.example_tweets = json.dumps(req.example_tweets)
    persona.system_prompt = _compile_system_prompt(req)
    await db.commit()
    return _to_response(persona)


@router.post("/{persona_id}/assign/{account_id}")
async def assign_persona(persona_id: str, account_id: str, db: AsyncSession = Depends(get_db)):
    persona = await db.get(Persona, persona_id)
    if not persona:
        raise HTTPException(404, "Persona not found")
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(404, "Account not found")

    account.persona_id = persona_id
    await db.commit()
    return {"message": f"Persona '{persona.name}' assigned to @{account.username}"}


@router.delete("/{persona_id}")
async def delete_persona(persona_id: str, db: AsyncSession = Depends(get_db)):
    persona = await db.get(Persona, persona_id)
    if not persona:
        raise HTTPException(404, "Persona not found")
    await db.delete(persona)
    await db.commit()
    return {"message": "Deleted"}
