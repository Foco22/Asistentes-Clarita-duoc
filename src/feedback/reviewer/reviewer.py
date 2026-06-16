import os
import re
from datetime import datetime, timezone
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from supabase import create_client, Client
from dotenv import load_dotenv

from src.feedback.prompts import REVIEWER_SYSTEM_PROMPT
from src.feedback.reviewer.reviewer_tools import get_bad_conversations, list_repo_files, read_repo_file, save_suggestion, set_reviewer_model

load_dotenv()

TOOLS = [get_bad_conversations, list_repo_files, read_repo_file, save_suggestion]


class ReviewerState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


class ConversationReviewerAgent:
    def __init__(self, model: str = "gpt-5.5"):
        self._model = model
        self._supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )
        self._graph = self._build_graph()

    def run(self) -> str:
        """
        Fetches all bad conversations, reads the relevant repo files,
        suggests improvements, and saves results to Supabase.
        """
        set_reviewer_model(self._model)
        result = self._graph.invoke({
            "messages": [HumanMessage(content=(
                "Fetch all bad conversations using get_bad_conversations. "
                "Then for each one, read the relevant source file from the repository and suggest a specific improvement. "
                "Process each conversation separately — do not mix issues from different sessions."
            ))]
        })
        output = result["messages"][-1].content
        print(output)
        self._save_from_output(output)
        return output

    def _save_from_output(self, output: str) -> None:
        """Fallback: parses agent output and saves suggestions not already saved by the tool."""
        blocks = re.findall(
            r"SESSION:\s*(\S+).*?FILE:\s*(.+?)\nSUGGESTION:\s*(.+?)(?=\n---|$)",
            output,
            re.DOTALL,
        )
        for session_id, diagnosed_file, suggestion in blocks:
            session_id = session_id.strip()
            # Only save if the agent didn't already call save_suggestion
            existing = self._supabase.table("evaluations").select("reviewed_at").eq("session_id", session_id).execute()
            if existing.data and existing.data[0]["reviewed_at"] is not None:
                continue
            self._supabase.table("evaluations").update({
                "diagnosed_file": diagnosed_file.strip(),
                "suggestion": suggestion.strip(),
                "reviewer_model": self._model,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("session_id", session_id).execute()
            print(f"  [Fallback saved] suggestion for session {session_id}")

    def _build_graph(self):
        llm = ChatOpenAI(model=self._model, temperature=0).bind_tools(TOOLS)
        tool_node = ToolNode(TOOLS)

        def agent_node(state: ReviewerState):
            messages = [SystemMessage(content=REVIEWER_SYSTEM_PROMPT)] + state["messages"]
            response = llm.invoke(messages)
            return {"messages": [response]}

        def should_continue(state: ReviewerState):
            last = state["messages"][-1]
            if hasattr(last, "tool_calls") and last.tool_calls:
                return "tools"
            return END

        graph = StateGraph(ReviewerState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tool_node)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
        graph.add_edge("tools", "agent")
        return graph.compile()


if __name__ == "__main__":
    agent = ConversationReviewerAgent(model="gpt-5.5")
    agent.run()