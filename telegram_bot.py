import os
import uuid
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from langchain_core.messages import HumanMessage
from agent_app.agent import app as agent

load_dotenv()

# Maps Telegram chat_id -> LangGraph thread_id for per-user memory
chat_threads: dict[int, str] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    chat_threads[chat_id] = str(uuid.uuid4())
    await update.message.reply_text(
        "Hola! Soy el asistente del profesor Francisco Macaya para la asignatura "
        "'Ingeniería de Soluciones con Inteligencia Artificial'. "
        "Puedes preguntarme sobre el contenido del curso."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text

    if chat_id not in chat_threads:
        chat_threads[chat_id] = str(uuid.uuid4())
    thread_id = chat_threads[chat_id]

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    config = {"configurable": {"thread_id": thread_id}}
    result = agent.invoke(
        {"messages": [HumanMessage(content=user_text)]},
        config=config,
    )

    answer = result["messages"][-1].content
    await update.message.reply_text(answer)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running...")
    application.run_polling()


if __name__ == "__main__":
    main()
