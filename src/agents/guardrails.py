import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.runnables.config import get_executor_for_config

from src.agents.prompts import (
    OFFENSIVE_GUARDRAIL_PROMPT,
    PROMPT_INJECTION_GUARDRAIL_PROMPT,
    WAR_TOPICS_GUARDRAIL_PROMPT,
)


def _evaluate(prompt: str, message: str, model: str, config: RunnableConfig) -> bool:
    llm = ChatOpenAI(
        model=model,
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url="https://api.openai.com/v1",
    )
    result = llm.invoke(
        [SystemMessage(content=prompt), HumanMessage(content=message)],
        config=config,
    )
    return result.content.strip().lower() == "true"


def run_guardrails(message: str, model: str, config: RunnableConfig) -> dict:
    """Run all 3 guardrail evaluators in parallel. Returns dict with is_offensive, is_prompt_injection, is_war_topic."""
    # get_executor_for_config propagates the parent run context so guardrail
    # LLM calls attach as child spans instead of orphan root runs.
    with get_executor_for_config(config) as executor:
        future_offensive = executor.submit(_evaluate, OFFENSIVE_GUARDRAIL_PROMPT, message, model, config)
        future_injection = executor.submit(_evaluate, PROMPT_INJECTION_GUARDRAIL_PROMPT, message, model, config)
        future_war = executor.submit(_evaluate, WAR_TOPICS_GUARDRAIL_PROMPT, message, model, config)

    return {
        "is_offensive": future_offensive.result(),
        "is_prompt_injection": future_injection.result(),
        "is_war_topic": future_war.result(),
    }
