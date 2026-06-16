from src.feedback.evaluator.evaluator import ConversationEvaluator
from src.feedback.reviewer.reviewer import ConversationReviewerAgent


def run_feedback_pipeline(evaluator_model: str = "gpt-4o-mini", reviewer_model: str = "gpt-5.5"):
    print("=" * 60)
    print("STEP 1: Evaluating new conversations...")
    print("=" * 60)
    evaluator = ConversationEvaluator(model=evaluator_model)
    results = evaluator.run()

    bad_count = sum(1 for r in results if r.verdict == "bad")
    print(f"\nEvaluated {len(results)} session(s). {bad_count} bad conversation(s) found.\n")

    if bad_count == 0:
        print("No bad conversations to review. Done.")
        return

    print("=" * 60)
    print("STEP 2: Reviewing bad conversations...")
    print("=" * 60)
    reviewer = ConversationReviewerAgent(model=reviewer_model)
    reviewer.run()


if __name__ == "__main__":
    run_feedback_pipeline()