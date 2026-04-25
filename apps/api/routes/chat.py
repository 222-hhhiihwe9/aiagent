from __future__ import annotations

import json
import logging
import traceback

from fastapi import APIRouter, Response
from pydantic import BaseModel

from apps.core.runtime_registry import get_runtime, get_runtime_error
from aiagent.schemas.events import SystemEvent, SystemEventType
from aiagent.schemas.inputs import InputEvent, InputSource
from aiagent.schemas.outputs import OutputEvent, ResponsePacket

router = APIRouter()
logger = logging.getLogger("aiagent.api.chat")


class ChatRequest(BaseModel):
    user_id: str
    username: str
    text: str


def _handle_chat_with_debug(runtime, req: ChatRequest) -> dict:
    dispatcher = runtime.dispatcher
    event = InputEvent(
        source=InputSource.CHAT,
        user_id=req.user_id,
        user_name=req.username,
        text=req.text,
    )

    session_id = dispatcher.session_manager.resolve_session_id(event)
    dispatcher.agent_state.current_session_id = session_id

    accepted, reason = dispatcher.dialogue_manager.should_accept(event)
    if not accepted:
        raise ValueError(reason)

    interrupt_reason = dispatcher.interrupt_manager.consume_interrupt()
    if interrupt_reason:
        dispatcher.event_bus.publish(
            SystemEvent(
                event_type=SystemEventType.ERROR,
                payload={"interrupt_reason": interrupt_reason},
            )
        )

    dispatcher.conversation_state.add_input(event)

    dispatcher.event_bus.publish(
        SystemEvent(
            event_type=SystemEventType.INPUT_RECEIVED,
            payload={"event_id": event.event_id, "text": event.text},
        )
    )

    if not dispatcher.scheduler.should_process_now(event):
        raise ValueError("Empty input event cannot be processed.")

    persona_runtime = dispatcher.persona_manager.get_active_persona()
    main_runner = dispatcher.agent_core.main_runner

    history = dispatcher.agent_core._build_history_lines()
    retrieved_context: list[str] = []

    state_result = main_runner.state_runner.run(
        user_text=event.text,
        user_name=event.user_name,
        persona_runtime=persona_runtime,
        history=history,
    )

    planner_result = main_runner.planner_runner.run(
        user_text=event.text,
        user_name=event.user_name,
        state_result=state_result,
        persona_runtime=persona_runtime,
    )

    llm_result = main_runner.llm_runner.run(
        thread_id=event.user_id,
        user_text=event.text,
        user_name=event.user_name,
        state_result=state_result,
        planner_result=planner_result,
        persona_runtime=persona_runtime,
        retrieved_context=retrieved_context,
    )

    packet_metadata = {}
    packet_metadata.update(getattr(state_result, "metadata", {}))
    packet_metadata.update(getattr(planner_result, "metadata", {}))
    packet_metadata.update(getattr(llm_result, "metadata", {}))
    packet_metadata["main_graph"] = "done"

    packet = ResponsePacket(
        reply_text=llm_result.reply_text,
        base_reply_text=llm_result.reply_text,
        emotion=main_runner._to_emotion_label(llm_result.target_emotion),
        should_speak=llm_result.should_speak,
        should_store_memory=llm_result.should_store_memory,
        motion=llm_result.target_motion,
        expression=llm_result.target_expression,
        metadata=packet_metadata,
    )

    output = OutputEvent(packet=packet)
    output = dispatcher.output_broadcaster.broadcast(output)
    dispatcher._store_memories(event, output)

    dispatcher.agent_state.last_output_id = output.output_id
    dispatcher.conversation_state.add_output(output)
    dispatcher.dialogue_manager.record_turn(
        session_id=session_id,
        event=event,
        output=output,
    )

    dispatcher.event_bus.publish(
        SystemEvent(
            event_type=SystemEventType.RESPONSE_READY,
            payload={
                "output_id": output.output_id,
                "reply_text": packet.reply_text,
                "base_reply_text": packet.base_reply_text or "",
                "audio_path": packet.audio_path or "",
                "audio_segments": packet.audio_segments,
            },
        )
    )

    return {
        "output": output,
        "state_result": state_result.model_dump(mode="json"),
        "planner_result": planner_result.model_dump(mode="json"),
        "llm_result": llm_result.model_dump(mode="json"),
        "history": history,
        "retrieved_context": retrieved_context,
    }


@router.post("/chat")
def chat(req: ChatRequest):
    try:
        runtime = get_runtime()
    except Exception as exc:
        logger.exception("Runtime init failed in /chat: %s", exc)
        body = json.dumps(
            {
                "ok": False,
                "stage": "runtime_init",
                "error": str(exc),
                "runtime_error": get_runtime_error(),
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            status_code=500,
        )

    try:
        result = _handle_chat_with_debug(runtime, req)
        output = result["output"]
        packet = output.packet

        body = json.dumps(
            {
                "ok": True,
                "output_id": output.output_id,
                "reply": packet.reply_text,
                "base_reply_text": packet.base_reply_text,
                "emotion": packet.emotion,
                "motion": packet.motion,
                "expression": packet.expression,
                "audio_path": packet.audio_path,
                "audio_segments": packet.audio_segments,
                "audio_segment_texts": packet.audio_segment_texts,
                "live2d_command_path": packet.live2d_command_path,
                "metadata": packet.metadata,
                "debug": {
                    "history": result["history"],
                    "retrieved_context": result["retrieved_context"],
                    "state_result": result["state_result"],
                    "planner_result": result["planner_result"],
                    "llm_result": result["llm_result"],
                },
            },
            ensure_ascii=False,
            default=str,
        )

        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            status_code=200,
        )

    except Exception as exc:
        logger.exception("Chat route failed: %s", exc)
        body = json.dumps(
            {
                "ok": False,
                "stage": "chat_handler",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            status_code=500,
        )
