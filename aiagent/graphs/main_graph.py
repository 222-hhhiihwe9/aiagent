from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aiagent.graphs.llm_graph import LLMRunner
from aiagent.graphs.planner_graph import PlannerRunner
from aiagent.graphs.state_graph import StateRunner
from aiagent.persona.persona_runtime import PersonaRuntime
from aiagent.schemas.inputs import InputEvent
from aiagent.schemas.outputs import EmotionLabel, ResponsePacket


class MainGraphState(TypedDict, total=False):
    input_event: InputEvent
    persona_runtime: PersonaRuntime

    history: list[str]
    retrieved_context: list[str]

    state_result: Any
    planner_result: Any
    llm_result: Any

    response_packet: ResponsePacket
    metadata: dict[str, str]


class MainRunner:
    def __init__(
        self,
        state_runner: StateRunner,
        planner_runner: PlannerRunner,
        llm_runner: LLMRunner,
    ) -> None:
        self.state_runner = state_runner
        self.planner_runner = planner_runner
        self.llm_runner = llm_runner
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(MainGraphState)

        graph.add_node("prepare_context", self._prepare_context_node)
        graph.add_node("run_state_graph", self._run_state_graph_node)
        graph.add_node("run_planner_graph", self._run_planner_graph_node)
        graph.add_node("run_llm_graph", self._run_llm_graph_node)
        graph.add_node("build_response_packet", self._build_response_packet_node)

        graph.add_edge(START, "prepare_context")
        graph.add_edge("prepare_context", "run_state_graph")
        graph.add_edge("run_state_graph", "run_planner_graph")
        graph.add_edge("run_planner_graph", "run_llm_graph")
        graph.add_edge("run_llm_graph", "build_response_packet")
        graph.add_edge("build_response_packet", END)

        return graph.compile()

    def run(
        self,
        event: InputEvent,
        persona_runtime: PersonaRuntime,
        history: list[str] | None = None,
        retrieved_context: list[str] | None = None,
    ) -> ResponsePacket:
        result = self.graph.invoke(
            {
                "input_event": event,
                "persona_runtime": persona_runtime,
                "history": history or [],
                "retrieved_context": retrieved_context or [],
            }
        )

        return result["response_packet"]

    def _prepare_context_node(self, state: MainGraphState) -> dict[str, object]:
        history = list(state.get("history", []))
        retrieved_context = list(state.get("retrieved_context", []))

        return {
            "history": history,
            "retrieved_context": retrieved_context,
            "metadata": {
                "main_graph": "started",
                "history_count": str(len(history)),
                "retrieved_context_count": str(len(retrieved_context)),
            },
        }

    def _run_state_graph_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"] # type: ignore
        persona_runtime = state["persona_runtime"]# type: ignore
        history = state.get("history", [])

        state_result = self.state_runner.run(
            user_text=event.text,
            user_name=event.user_name,
            persona_runtime=persona_runtime,
            history=history,
        )

        metadata = dict(state.get("metadata", {}))
        metadata["state_graph"] = "done"

        return {
            "state_result": state_result,
            "metadata": metadata,
        }

    def _run_planner_graph_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"] #type: ignore
        persona_runtime = state["persona_runtime"] #type: ignore
        state_result = state["state_result"] #type: ignore

        planner_result = self.planner_runner.run(
            user_text=event.text,
            user_name=event.user_name,
            state_result=state_result,
            persona_runtime=persona_runtime,
        )

        metadata = dict(state.get("metadata", {}))
        metadata["planner_graph"] = "done"

        return {
            "planner_result": planner_result,
            "metadata": metadata,
        }

    def _run_llm_graph_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"] #type: ignore
        persona_runtime = state["persona_runtime"] #type: ignore
        state_result = state["state_result"] #type: ignore
        planner_result = state["planner_result"] #type: ignore
        retrieved_context = state.get("retrieved_context", [])

        llm_result = self.llm_runner.run(
            thread_id=event.user_id,
            user_text=event.text,
            user_name=event.user_name,
            state_result=state_result,
            planner_result=planner_result,
            persona_runtime=persona_runtime,
            retrieved_context=retrieved_context,
        )

        metadata = dict(state.get("metadata", {}))
        metadata["llm_graph"] = "done"

        return {
            "llm_result": llm_result,
            "metadata": metadata,
        }

    def _build_response_packet_node(self, state: MainGraphState) -> dict[str, object]:
        llm_result = state["llm_result"]  #type: ignore

        metadata = dict(state.get("metadata", {}))
        metadata.update(llm_result.metadata)

        response_packet = ResponsePacket(
            reply_text=llm_result.reply_text,
            base_reply_text=llm_result.reply_text,
            emotion=self._to_emotion_label(llm_result.target_emotion),
            should_speak=llm_result.should_speak,
            should_store_memory=llm_result.should_store_memory,
            motion=llm_result.target_motion,
            expression=llm_result.target_expression,
            metadata=metadata,
        )

        return {
            "response_packet": response_packet,
        }

    def clear_thread(self, thread_id: str) -> None:
        self.llm_runner.clear_thread(thread_id)

    def clear_all_threads(self) -> None:
        self.llm_runner.clear_all_threads()

    def _to_emotion_label(self, emotion: str) -> EmotionLabel:
        normalized = (emotion or "").strip().lower()

        if normalized == EmotionLabel.HAPPY.value:
            return EmotionLabel.HAPPY

        if normalized == EmotionLabel.EXCITED.value:
            return EmotionLabel.EXCITED

        if normalized == EmotionLabel.CALM.value:
            return EmotionLabel.CALM

        if normalized == EmotionLabel.ANGRY.value:
            return EmotionLabel.ANGRY

        return EmotionLabel.NEUTRAL
