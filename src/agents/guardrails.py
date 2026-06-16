import os
from concurrent.futures import ThreadPoolExecutor
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from src.agents.prompts import (
    OFFENSIVE_GUARDRAIL_PROMPT,
    PROMPT_INJECTION_GUARDRAIL_PROMPT,
    WAR_TOPICS_GUARDRAIL_PROMPT,
)


def _evaluate(prompt: str, message: str, model: str) -> bool:
    llm = ChatOpenAI(
        model=model,
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://api.openai.com/v1",
    )
    result = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=message),
    ])
    return result.content.strip().lower() == "true"


def run_guardrails(message: str, model: str) -> dict:
    """Run all 3 guardrail evaluators in parallel. Returns dict with is_offensive, is_prompt_injection, is_war_topic."""
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_offensive = executor.submit(_evaluate, OFFENSIVE_GUARDRAIL_PROMPT, message, model)
        future_injection = executor.submit(_evaluate, PROMPT_INJECTION_GUARDRAIL_PROMPT, message, model)
        future_war = executor.submit(_evaluate, WAR_TOPICS_GUARDRAIL_PROMPT, message, model)

    return {
        "is_offensive": future_offensive.result(),
        "is_prompt_injection": future_injection.result(),
        "is_war_topic": future_war.result(),
    }
