import os
import uuid
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from src.agents.agent import app as agent, MODEL
from src.agents.prompts import TELEGRAM_START_MESSAGE
from src.observability.supabase_logger import SupabaseLogger


def _get_company(model: str) -> str:
    if model.startswith(("gpt-", "o1", "o3", "o4")):
        return "openai"
    elif model.startswith("claude"):
        return "anthropic"
    return "unknown"

load_dotenv()


class TelegramBot:
    def __init__(self):
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

        self._sessions: dict[int, dict] = {}
        self._logger = SupabaseLogger()
        self._app = Application.builder().token(token).build()
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

    def run(self):
        print("Bot running... Press Ctrl+C to stop.")
        self._app.run_polling()

    def _get_or_create_session(self, chat_id: int) -> dict:
        if chat_id not in self._sessions:
            thread_id = str(uuid.uuid4())
            session_id = self._logger.create_session(chat_id, thread_id)
            self._sessions[chat_id] = {"session_id": session_id, "thread_id": thread_id}
        return self._sessions[chat_id]

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        thread_id = str(uuid.uuid4())
        session_id = self._logger.create_session(chat_id, thread_id)
        self._sessions[chat_id] = {"session_id": session_id, "thread_id": thread_id}
        await update.message.reply_text(TELEGRAM_START_MESSAGE)

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user_text = update.message.text

        session = self._get_or_create_session(chat_id)
        session_id = session["session_id"]
        thread_id = session["thread_id"]

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")

        message_id = self._logger.log_message(session_id, "user", user_text)

        # Mirror thread_id (and chat_id) into metadata so LangSmith's Threads view
        # can group turns; configurable.thread_id alone only drives the checkpointer.
        config = {
            "configurable": {"thread_id": thread_id},
            "metadata": {"thread_id": thread_id, "chat_id": chat_id},
            "run_name": "asistente_clarita",
        }
        model = config["configurable"].get("model", MODEL)
        company = _get_company(model)

        # Stream the graph — each chunk is one node completing
        step_order = 0
        final_state = None
        node_start = SupabaseLogger.now()

        for chunk in agent.stream(
            {"messages": [HumanMessage(content=user_text)]},
            config=config,
            stream_mode="updates",
        ):
            node_end = SupabaseLogger.now()

            for node_name, state in chunk.items():
                tool_name = None
                input_data = {"content": user_text}
                output_data = {}
                prompt_tokens = None
                completion_tokens = None

                messages = state.get("messages", [])

                for msg in messages:
                    if isinstance(msg, AIMessage) and msg.tool_calls:
                        tool_name = msg.tool_calls[0]["name"] if len(msg.tool_calls) == 1 else None
                        output_data["tool_calls"] = [
                            {"name": tc["name"], "args": tc.get("args", {})}
                            for tc in msg.tool_calls
                        ]
                    elif isinstance(msg, ToolMessage):
                        tool_name = msg.name
                        # Split RAG chunks — each document separated by double newline
                        chunks = msg.content.split("\n\n")
                        output_data["chunks_count"] = len(chunks)
                        output_data["chunks"] = chunks
                        output_data["full_result"] = msg.content
                    elif isinstance(msg, AIMessage) and not msg.tool_calls:
                        output_data["content"] = msg.content

                    # Extract token usage from any AIMessage that has it
                    if isinstance(msg, AIMessage) and msg.usage_metadata:
                        prompt_tokens = msg.usage_metadata.get("input_tokens")
                        completion_tokens = msg.usage_metadata.get("output_tokens")

                # Capture guardrail flags
                if node_name == "check_guardrails":
                    output_data = {
                        "is_offensive": state.get("is_offensive"),
                        "is_prompt_injection": state.get("is_prompt_injection"),
                        "is_war_topic": state.get("is_war_topic"),
                    }

                # Capture reformulated query from generate_query node
                if node_name == "generate_query":
                    for msg in messages:
                        if isinstance(msg, AIMessage) and msg.tool_calls:
                            output_data["reformulated_query"] = msg.tool_calls[0].get("args", {}).get("query", "")

                trace_id = self._logger.log_trace(
                    session_id=session_id,
                    message_id=message_id,
                    step_order=step_order,
                    node_name=node_name,
                    tool_name=tool_name,
                    started_at=node_start,
                    ended_at=node_end,
                    input=input_data,
                    output=output_data,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    company=company,
                    model=model,
                )

                if prompt_tokens is not None and completion_tokens is not None:
                    self._logger.log_cost(
                        session_id=session_id,
                        message_id=message_id,
                        trace_id=trace_id,
                        company=company,
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )

                step_order += 1
                final_state = state

            node_start = node_end  # next node starts where this one ended

        is_blocked = bool(
            final_state and (
                final_state.get("is_offensive") or
                final_state.get("is_prompt_injection") or
                final_state.get("is_war_topic")
            )
        )

        # Get final answer from last agent invocation
        result = agent.get_state(config)
        answer = result.values["messages"][-1].content

        self._logger.log_message(session_id, "assistant", answer, blocked=is_blocked)

        await update.message.reply_text(answer)


if __name__ == "__main__":
    TelegramBot().run()
