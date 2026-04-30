from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from aiagent.graphs.llm_graph import LLMRunner
from aiagent.graphs.memory_graph import MemoryRunner
from aiagent.graphs.planner_graph import PlannerRunner
from aiagent.graphs.rag_graph import RAGRunner
from aiagent.graphs.state_graph import StateRunner
from aiagent.persona.persona_runtime import PersonaRuntime
from aiagent.schemas.inputs import InputEvent
from aiagent.schemas.outputs import EmotionLabel, ResponsePacket

NO_LONG_TERM_MEMORY_TEXT = "无长期记忆。"

class MainGraphState(TypedDict, total=False):
    input_event: InputEvent
    persona_runtime: PersonaRuntime
    session_id: str
    history: list[str]

    memory_hits: list[Any]
    memory_prompt_context: str
    memory_write_result: dict[str, Any]

    state_result: Any
    planner_result: Any
    rag_result: Any
    llm_result: Any

    response_packet: ResponsePacket
    metadata: dict[str, Any]


class MainRunner:
    def __init__(
        self,
        state_runner: StateRunner,
        planner_runner: PlannerRunner,
        rag_runner: RAGRunner,
        llm_runner: LLMRunner,
        memory_runner: MemoryRunner,
    ) -> None:
        self.state_runner = state_runner
        self.planner_runner = planner_runner
        self.rag_runner = rag_runner
        self.llm_runner = llm_runner
        self.memory_runner = memory_runner
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(MainGraphState)

        graph.add_node("prepare_context", self._prepare_context_node)
        graph.add_node("retrieve_memory", self._retrieve_memory_node)
        graph.add_node("run_state_graph", self._run_state_graph_node)
        graph.add_node("run_planner_graph", self._run_planner_graph_node)
        graph.add_node("run_rag_graph", self._run_rag_graph_node)
        graph.add_node("run_llm_graph", self._run_llm_graph_node)
        graph.add_node("store_memory", self._store_memory_node)
        graph.add_node("build_response_packet", self._build_response_packet_node)

        graph.add_edge(START, "prepare_context")
        graph.add_edge("prepare_context", "retrieve_memory")
        graph.add_edge("retrieve_memory", "run_state_graph")
        graph.add_edge("run_state_graph", "run_planner_graph")
        graph.add_edge("run_planner_graph", "run_rag_graph")
        graph.add_edge("run_rag_graph", "run_llm_graph")
        graph.add_edge("run_llm_graph", "store_memory")
        graph.add_edge("store_memory", "build_response_packet")
        graph.add_edge("build_response_packet", END)
        return graph.compile()

    def run(
        self,
        event: InputEvent,
        persona_runtime: PersonaRuntime,
        history: list[str] | None = None,
        session_id: str = "",
    ) -> ResponsePacket:
        return self.run_debug(
            event=event,
            persona_runtime=persona_runtime,
            history=history,
            session_id=session_id,
        )["response_packet"]

    def run_debug(
        self,
        event: InputEvent,
        persona_runtime: PersonaRuntime,
        history: list[str] | None = None,
        session_id: str = "",
    ) -> dict[str, Any]:
        return self.graph.invoke(
            {
                "input_event": event,
                "persona_runtime": persona_runtime,
                "session_id": session_id or event.user_id,
                "history": history or [],
            }
        )

    def clear_thread(self, thread_id: str) -> None:
        self.llm_runner.clear_thread(thread_id)

    def clear_all_threads(self) -> None:
        self.llm_runner.clear_all_threads()

    def _prepare_context_node(self, state: MainGraphState) -> dict[str, object]:
        history = list(state.get("history", []))
        return {
            "history": history,
            "metadata": {
                "main_graph": "started",
                "history_count": str(len(history)),
            },
        }

    def _retrieve_memory_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"]# type: ignore

        result = self.memory_runner.retrieve_before_reply(
            user_id=event.user_id,
            user_text=event.text,
            retrieval_query=event.text,
        )

        metadata = dict(state.get("metadata", {}))
        metadata.update(result.get("metadata", {}))

        return {
            "memory_hits": result.get("memory_hits", []),
            "memory_prompt_context": result.get("memory_prompt_context",  NO_LONG_TERM_MEMORY_TEXT),
            "metadata": metadata,
        }

    def _run_state_graph_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"]# type: ignore

        state_result = self.state_runner.run(
            user_text=event.text,
            user_name=event.user_name,
            persona_runtime=state["persona_runtime"],# type: ignore
            history=state.get("history", []),
        )

        metadata = dict(state.get("metadata", {}))
        metadata["state_graph"] = "done"
        return {"state_result": state_result, "metadata": metadata}

    def _run_planner_graph_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"]# type: ignore

        planner_result = self.planner_runner.run(
            user_text=event.text,
            user_name=event.user_name,
            state_result=state["state_result"],# type: ignore
            persona_runtime=state["persona_runtime"],# type: ignore
        )

        metadata = dict(state.get("metadata", {}))
        metadata["planner_graph"] = "done"
        metadata["planner_retrieval_query"] = getattr(planner_result, "retrieval_query", "")
        metadata["planner_should_retrieve"] = str(getattr(planner_result, "should_retrieve", False))
        return {"planner_result": planner_result, "metadata": metadata}

    def _run_rag_graph_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"]# type: ignore
        state_result = state["state_result"]# type: ignore
        planner_result = state["planner_result"]# type: ignore

        rag_result = self.rag_runner.run(
            user_text=event.text,
            state_intent=getattr(state_result, "intent", ""),
            state_topic=getattr(state_result, "topic", ""),
            planner_query=getattr(planner_result, "retrieval_query", ""),
            planner_should_retrieve=bool(getattr(planner_result, "should_retrieve", False)),
        )

        metadata = dict(state.get("metadata", {}))
        metadata.update(rag_result.metadata)
        metadata["rag_query"] = rag_result.query
        metadata["rag_should_inject"] = str(rag_result.should_inject)
        metadata["rag_context_count"] = str(len(rag_result.context))
        return {"rag_result": rag_result, "metadata": metadata}

    def _run_llm_graph_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"]# type: ignore
        rag_result = state["rag_result"]# type: ignore

        llm_result = self.llm_runner.run(
            thread_id=event.user_id,
            user_text=event.text,
            user_name=event.user_name,
            state_result=state["state_result"],# type: ignore
            planner_result=state["planner_result"],# type: ignore
            persona_runtime=state["persona_runtime"],# type: ignore
            retrieved_context=list(rag_result.context),
            long_term_memory_context=state.get("memory_prompt_context",NO_LONG_TERM_MEMORY_TEXT ),
        )

        metadata = dict(state.get("metadata", {}))
        metadata["llm_graph"] = "done"
        return {"llm_result": llm_result, "metadata": metadata}

    def _store_memory_node(self, state: MainGraphState) -> dict[str, object]:
        event = state["input_event"]# type: ignore
        planner_result = state["planner_result"]# type: ignore
        llm_result = state["llm_result"]# type: ignore

        result = self.memory_runner.run_after_reply(
            user_id=event.user_id,
            user_name=event.user_name,
            session_id=state.get("session_id", event.user_id),
            turn_id=event.event_id,
            user_text=event.text,
            assistant_text=llm_result.reply_text,
            retrieval_query=getattr(planner_result, "retrieval_query", "") or event.text,
            planner_should_store_memory=bool(getattr(planner_result, "should_store_memory", False)),
            memory_prompt_context=state.get("memory_prompt_context", NO_LONG_TERM_MEMORY_TEXT),
            metadata={
                "input_source": str(event.source),
                "persona_id": state["persona_runtime"].persona_id,# type: ignore
            },
        )

        metadata = dict(state.get("metadata", {}))
        metadata.update(result.get("metadata", {}))
        return {
            "memory_write_result": result.get("store_result", {}),
            "metadata": metadata,
        }

    def _build_response_packet_node(self, state: MainGraphState) -> dict[str, object]:
        llm_result = state["llm_result"]# type: ignore
        metadata = dict(state.get("metadata", {}))
        metadata.update(llm_result.metadata)

        live2d = self._build_live2d_payload(
            emotion=self._to_emotion_label(llm_result.target_emotion),
            motion = llm_result.target_motion or "idle",
            expression = llm_result.target_expression or "neutral",
            audio_url = "",
        )

        packet = ResponsePacket(
            reply_text=llm_result.reply_text,
            base_reply_text=llm_result.reply_text,
            emotion=self._to_emotion_label(llm_result.target_emotion),
            should_speak=llm_result.should_speak,
            should_store_memory=llm_result.should_store_memory,
            motion=llm_result.target_motion or "idle",
            expression=llm_result.target_expression or "neutral",
            live2d=live2d,
            metadata={str(key): str(value) for key, value in metadata.items()},
        )
        return {"response_packet": packet}
    
    def _build_live2d_payload(
        self,
        emotion: EmotionLabel,
        motion: str,
        expression: str,
        audio_url: str = "",
    ) -> dict[str, Any]:
        return {
            "character": {
                "character_id": "yzl",
                "model_id": "yzl_v1",
                "emotion": str(emotion),
                "expression": expression or "neutral",
                "motion": motion or "idle",
                "motion_priority": 1,
                "mouth": {
                    "mode": "audio" if audio_url else "idle",
                    "audio_url": audio_url,
                },
                "eye": {
                    "blink": True,
                    "look_at": "user",
                },
            },
            "scene": {
                "background_id": "room_default",
                "lighting": "normal",
                "effect": "none",
            },
        }
    def _to_emotion_label(self, emotion: str) -> EmotionLabel:
        try:
            return EmotionLabel((emotion or "").strip().lower())
        except ValueError:
            return EmotionLabel.NEUTRAL
