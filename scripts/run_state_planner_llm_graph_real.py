from __future__ import annotations

from aiagent.cognition.planner_normalizer import PlannerNormalizer
from aiagent.cognition.planner_reply import ReplyPlanner
from aiagent.cognition.state_analyzer import StateAnalyzer
from aiagent.cognition.state_normalizer import StateNormalizer
from aiagent.graphs.llm_graph import LLMRunner
from aiagent.graphs.planner_graph import PlannerRunner
from aiagent.graphs.state_graph import StateRunner
from aiagent.persona.persona_loader import PersonaLoader
from aiagent.persona.persona_runtime import PersonaRuntime
from aiagent.services.llm_service import LLMService
from aiagent.services.planner_llm_service import PlannerLLMService
from aiagent.services.state_llm_service import StateLLMService
from config.settings import settings


def build_persona_runtime() -> PersonaRuntime:
    loader = PersonaLoader(base_dir="data/characters")
    config = loader.load_persona("yzl")
    return PersonaRuntime(config)


def build_state_runner() -> StateRunner:
    state_llm_service = StateLLMService(settings=settings)
    state_analyzer = StateAnalyzer(llm_service=state_llm_service)
    state_normalizer = StateNormalizer()

    return StateRunner(
        state_analyzer=state_analyzer,
        state_normalizer=state_normalizer,
    )


def build_planner_runner() -> PlannerRunner:
    planner_llm_service = PlannerLLMService(settings=settings)
    planner_reply = ReplyPlanner(llm_service=planner_llm_service)
    planner_normalizer = PlannerNormalizer()

    return PlannerRunner(
        planner_reply=planner_reply,
        planner_normalizer=planner_normalizer,
    )


def build_llm_runner() -> LLMRunner:
    llm_service = LLMService(settings=settings)
    return LLMRunner(
        llm_service=llm_service,
        short_term_turn_window=6,
    )


def run_turn(
    *,
    thread_id: str,
    user_name: str,
    user_text: str,
    persona: PersonaRuntime,
    state_runner: StateRunner,
    planner_runner: PlannerRunner,
    llm_runner: LLMRunner,
    history: list[str] | None = None,
    retrieved_context: list[str] | None = None,
) -> None:
    print("=" * 100)
    print("USER INPUT:")
    print(user_text)
    print()

    state_result = state_runner.run(
        user_text=user_text,
        user_name=user_name,
        persona_runtime=persona,
        history=history or [],
    )

    print("STATE RESULT:")
    print(state_result.model_dump(mode="json"))
    print()

    planner_result = planner_runner.run(
        user_text=user_text,
        user_name=user_name,
        state_result=state_result,
        persona_runtime=persona,
    )

    print("PLANNER RESULT:")
    print(planner_result.model_dump(mode="json"))
    print()

    llm_result = llm_runner.run(
        thread_id=thread_id,
        user_text=user_text,
        user_name=user_name,
        state_result=state_result,
        planner_result=planner_result,
        persona_runtime=persona,
        retrieved_context=retrieved_context or [],
    )

    print("LLM RESULT:")
    print(llm_result.model_dump(mode="json"))
    print()

    print("FINAL REPLY:")
    print(llm_result.reply_text)
    print()

    print("SHORT TERM MEMORY:")
    for line in llm_result.short_term_messages:
        print(line)

    print("=" * 100)
    print()


def main() -> None:
    persona = build_persona_runtime()
    state_runner = build_state_runner()
    planner_runner = build_planner_runner()
    llm_runner = build_llm_runner()

    thread_id = "real-graph-test-user-001"
    user_name = "小花"

    print("=== RUNTIME CONFIG ===")
    print(
        {
            "llm_provider": settings.llm_provider,
            "llm_model": settings.llm_model,
            "enable_mock_llm": settings.enable_mock_llm,
            "state_provider": settings.state_provider,
            "state_model": settings.state_model,
            "enable_mock_state": settings.enable_mock_state,
            "planner_provider": settings.planner_provider,
            "planner_model": settings.planner_model,
            "enable_mock_planner": settings.enable_mock_planner,
        }
    )
    print()

    print("=== PERSONA SUMMARY ===")
    print(persona.summary())
    print()

    test_turns = [
        {
            "user_text": "阿绫，今天下午好呀。",
            "history": [],
            "retrieved_context": [],
        },
        {
            "user_text": "阿绫我又怀念起你的演唱会了",
            "history": [],
            "retrieved_context": [],
        },
        {
            "user_text": "阿绫你真的存在吗",
            "history": [],
            "retrieved_context": [],
        },
         {
            "user_text": "阿绫，我们的相遇是否也是永别呢",
            "history": [],
            "retrieved_context": [],
        },
    ]

    for turn in test_turns:
        run_turn(
            thread_id=thread_id,
            user_name=user_name,
            user_text=turn["user_text"],
            persona=persona,
            state_runner=state_runner,
            planner_runner=planner_runner,
            llm_runner=llm_runner,
            history=turn["history"],
            retrieved_context=turn["retrieved_context"],
        )


if __name__ == "__main__":
    main()
