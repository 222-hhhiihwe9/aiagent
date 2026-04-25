from __future__ import annotations

from apps.core.bootstrap import build_runtime
from config.settings import settings


def print_section(title: str) -> None:
    print(f"\n{'=' * 24} {title} {'=' * 24}")


def main() -> None:
    runtime = build_runtime()

    print_section("RUNTIME CONFIG")
    print(
        {
            "state_provider": settings.state_provider,
            "state_model": settings.state_model,
            "planner_provider": settings.planner_provider,
            "planner_model": settings.planner_model,
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "tts_provider": settings.tts_provider,
            "asr_provider": settings.asr_provider,
        }
    )

    test_turns = [
        {
            "text": "阿绫，今天下午好呀。",
            "user_id": "u001",
            "username": "小花",
        },
        {
            "text": "我明天考试，有点紧张。",
            "user_id": "u001",
            "username": "小花",
        },
        {
            "text": "你还记得我刚刚在担心什么吗？",
            "user_id": "u001",
            "username": "小花",
        },
    ]

    for index, item in enumerate(test_turns, start=1):
        print_section(f"ROUND {index}")
        print("INPUT:")
        print(item)

        output = runtime.handle_chat_full(
            text=item["text"],
            user_id=item["user_id"],
            username=item["username"],
        )

        print("\nOUTPUT:")
        print(output.model_dump(mode="json"))

    print_section("CONVERSATION SNAPSHOT")
    print(runtime.conversation_state.snapshot())


if __name__ == "__main__":
    main()
