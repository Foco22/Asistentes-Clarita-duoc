import os
import json
from dataclasses import dataclass
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

from src.feedback.prompts import EVALUATION_PROMPT

load_dotenv()


@dataclass
class EvaluationResult:
    session_id: str
    verdict: str
    score: int
    reason: str


class ConversationEvaluator:
    def __init__(self, model: str = "gpt-4o-mini"):
        self._model = model
        self._supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )
        self._openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def run(self) -> list[EvaluationResult]:
        """Evaluates all sessions that don't have an evaluation yet."""
        sessions = self._get_unevaluated_sessions()

        if not sessions:
            print("No new sessions to evaluate.")
            return []

        print(f"Found {len(sessions)} session(s) to evaluate.")
        results = []

        for session in sessions:
            session_id = session["id"]
            messages = self._get_messages(session_id)

            if not messages:
                print(f"  Skipping session {session_id} — no messages.")
                continue

            conversation_text = self._format_conversation(messages)
            evaluation = self._call_llm(conversation_text)

            self._save_evaluation(session_id, evaluation)

            result = EvaluationResult(
                session_id=session_id,
                verdict=evaluation["verdict"],
                score=int(evaluation["score"]),
                reason=evaluation["reason"],
            )
            results.append(result)
            print(f"  Session {session_id}: {result.verdict} (score={result.score}) — {result.reason}")

        return results

    def _get_unevaluated_sessions(self) -> list[dict]:
        evaluated = self._supabase.table("evaluations").select("session_id").execute()
        evaluated_ids = {row["session_id"] for row in evaluated.data}

        sessions = self._supabase.table("sessions").select("id, telegram_chat_id, created_at").execute()
        return [s for s in sessions.data if s["id"] not in evaluated_ids]

    def _get_messages(self, session_id: str) -> list[dict]:
        result = (
            self._supabase.table("messages")
            .select("role, content, blocked, created_at")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return result.data

    def _format_conversation(self, messages: list[dict]) -> str:
        lines = []
        for msg in messages:
            prefix = f"[{msg['role'].upper()}]"
            if msg.get("blocked"):
                prefix += " [BLOCKED BY GUARDRAILS]"
            lines.append(f"{prefix}: {msg['content']}")
        return "\n".join(lines)

    def _call_llm(self, conversation_text: str) -> dict:
        response = self._openai.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "user", "content": EVALUATION_PROMPT + conversation_text}
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    def _save_evaluation(self, session_id: str, evaluation: dict) -> str:
        result = self._supabase.table("evaluations").insert({
            "session_id": session_id,
            "verdict": evaluation["verdict"],
            "score": int(evaluation["score"]),
            "reason": evaluation["reason"],
            "evaluator_model": self._model,
        }).execute()
        return result.data[0]["id"]


if __name__ == "__main__":
    evaluator = ConversationEvaluator(model="gpt-4o-mini")
    evaluator.run()