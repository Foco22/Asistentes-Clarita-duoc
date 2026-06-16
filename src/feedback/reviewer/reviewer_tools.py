import os
import base64
import requests
from langchain_core.tools import tool
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

REPO = os.getenv("GITHUB_REPO")
GITHUB_API = os.getenv("GITHUB_API_URL", "https://api.github.com")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_BASE_PATH = os.getenv("GITHUB_BASE_PATH", "")

# Set by ConversationReviewerAgent before running the graph
_reviewer_model: str = "unknown"

def set_reviewer_model(model: str) -> None:
    global _reviewer_model
    _reviewer_model = model

def _github_headers() -> dict:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

_supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


@tool
def get_bad_conversations() -> list[dict]:
    """
    Fetches all conversations evaluated as bad from Supabase.
    Returns a list with session_id, score, evaluation reason, and messages.
    """
    evals = (
        _supabase.table("evaluations")
        .select("session_id, score, reason")
        .eq("verdict", "bad")
        .execute()
    )

    result = []
    for ev in evals.data:
        messages = (
            _supabase.table("messages")
            .select("role, content, blocked")
            .eq("session_id", ev["session_id"])
            .order("created_at")
            .execute()
        )
        result.append({
            "session_id": ev["session_id"],
            "score": ev["score"],
            "evaluation_reason": ev["reason"],
            "messages": messages.data,
        })
    return result


@tool
def list_repo_files(path: str = "") -> list[str]:
    """
    Lists files and folders in the GitHub repository at the given path.
    Use an empty string for the root. Example paths: "src/agents", "src/feedback".
    Returns entries as "file: path" or "dir: path".
    """
    full_path = f"{GITHUB_BASE_PATH}/{path}".strip("/") if path else GITHUB_BASE_PATH
    url = f"{GITHUB_API}/repos/{REPO}/contents/{full_path}"
    print(f"  [GitHub] GET {url}")
    response = requests.get(url, headers=_github_headers())
    if response.status_code != 200:
        return [f"Error {response.status_code}: {url} — {response.json().get('message', response.text)}"]
    items = response.json()
    # Return paths relative to base_path so the agent doesn't duplicate it
    def relative(p):
        return p[len(GITHUB_BASE_PATH):].lstrip("/") if GITHUB_BASE_PATH and p.startswith(GITHUB_BASE_PATH) else p
    return [f"{item['type']}: {relative(item['path'])}" for item in items]


@tool
def read_repo_file(file_path: str) -> str:
    """
    Reads the content of a specific file from the GitHub repository.
    Example: read_repo_file("src/agents/prompts.py")
    """
    # Avoid duplicating base path if the agent passes the full path from list_repo_files
    if GITHUB_BASE_PATH and not file_path.startswith(GITHUB_BASE_PATH):
        full_path = f"{GITHUB_BASE_PATH}/{file_path}".strip("/")
    else:
        full_path = file_path.strip("/")
    url = f"{GITHUB_API}/repos/{REPO}/contents/{full_path}"
    print(f"  [GitHub] GET {url}")
    response = requests.get(url, headers=_github_headers())
    if response.status_code != 200:
        return f"Error {response.status_code}: could not read {file_path}"
    content_b64 = response.json().get("content", "")
    return base64.b64decode(content_b64).decode("utf-8")


@tool
def save_suggestion(session_id: str, diagnosed_file: str, suggestion: str) -> str:
    """
    Saves the code improvement suggestion for a bad conversation into Supabase.
    Call this after reading the file and writing the suggestion.
    """
    from datetime import datetime, timezone
    _supabase.table("evaluations").update({
        "diagnosed_file": diagnosed_file,
        "suggestion": suggestion,
        "reviewer_model": _reviewer_model,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("session_id", session_id).execute()
    return f"Suggestion saved for session {session_id}."