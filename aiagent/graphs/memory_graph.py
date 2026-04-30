from __future__ import annotations

from typing import Any,TypedDict

from langgraph.graph import START,END,StateGraph

from aiagent.memory.mem0_memory import Mem0LongTermMemory,MemoryHit
from aiagent.schemas.memory import MemoryWriteDecision
from aiagent.services.memory_policy_llm_service import MemoryPolicyLLMService

class MemoryGraphState(TypedDict,total=False):
    user_id:str
    user_name:str
    agent_id:str
    session_id:str
    turn_id:str
    user_text:str
    assistant_text:str
    retrieval_query:str
    planner_should_store_memory:bool
    memory_hits:list[MemoryHit]
    memory_prompt_context:str
    write_decision:MemoryWriteDecision
    store_result:dict[str,Any]
    metadata:dict[str,Any]

class MemoryRunner:
    def __init__(
            self,
            memory:Mem0LongTermMemory,
            policy_service:MemoryPolicyLLMService,
            default_agent_id:str = "yzl",
            retrieval_limit:int =6
    ) ->None:
        self.memory = memory
        self.policy_service = policy_service
        self.default_agent_id = default_agent_id
        self.retrieval_limit = retrieval_limit
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(MemoryGraphState)
        graph.add_node("retrieve",self._retrieve_node)
        graph.add_node("decide_write",self._decide_write_node)
        graph.add_node("store",self._store_node)

        graph.add_edge(START,"retrieve")
        graph.add_edge("retrieve","decide_write")
        graph.add_conditional_edges(
            "decide_write",
            self._route_after_decision,
            {"store":"store","end":END}
        )
        graph.add_edge("store",END)
        return graph.compile()

    def retrieve_before_reply(
        self,
        user_id:str,
        user_text:str,
        retrieval_query:str = "",
        agent_id:str|None = None
    ) ->MemoryGraphState:
        return self._retrieve_node(
            {
                "user_id":user_id,
                "user_text":user_text,
                "retrieval_query":retrieval_query,
                "agent_id":agent_id or self.default_agent_id
            }
        )
    
    def run_after_reply(
            self,
            user_id:str,
            user_name:str,
            session_id:str,
            turn_id:str,
            user_text:str,
            assistant_text:str,
            retrieval_query:str,
            planner_should_store_memory:bool,
            memory_prompt_context:str = "",
            metadata:dict[str,Any] |None = None,
            agent_id:str|None = None
    ) ->MemoryGraphState:
        return self.graph.invoke( # type: ignore
            {
                "user_id": user_id,
                "user_name": user_name,
                "agent_id": agent_id or self.default_agent_id,
                "session_id": session_id,
                "turn_id": turn_id,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "retrieval_query": retrieval_query or user_text,
                "planner_should_store_memory": planner_should_store_memory,
                "memory_prompt_context": memory_prompt_context,
                "metadata": metadata or {},
            }
        )
    
    def _retrieve_node(self,state:MemoryGraphState) ->MemoryGraphState:
        query = state.get("retrieval_query","") or state.get("user_text","")
        hits = self.memory.search( 
            query=query,
            user_id=state["user_id"],# type: ignore
            agent_id=state.get("agent_id") or self.default_agent_id,
            limit=self.retrieval_limit
        )

        return {
            "memory_hits":hits,
            "memory_prompt_context":self.memory.format_for_prompt(hits=hits),
            "metadata":{
                **(state.get("metadata") or {}),
                "memory_retrieval_query":query,
                "memory_hit_count":len(hits),
            }
        }
    

    def _decide_write_node(self,state:MemoryGraphState) ->MemoryGraphState:
        decision = self.policy_service.decide_write(
            user_text= state.get("user_text",""),# type: ignore
            assistant_text= state.get("assistant_text",""),# type: ignore
            existing_memory_context= state.get("memory_prompt_context",""),# type: ignore
            planner_should_store_memory=bool(state.get("planner_should_store_memory",False)),# type: ignore
        )

        return{
            "write_decision":decision,
            "metadata":{
                **(state.get("metadata") or {}),
                "memory_write_should_store": decision.should_store,
                "memory_write_category": decision.category.value,
                "memory_write_importance": decision.importance.value,
                "memory_write_reason": decision.reason,
            }
        }
    
    def _route_after_decision(self,state:MemoryGraphState) ->str:
        decision = state.get("write_decision") # type: ignore
        return "store" if decision and decision.should_store else "end"
    
    def _store_node(self,state:MemoryGraphState) ->MemoryGraphState:
        decision = state["write_decision"] # type: ignore

        metadata = {
            **(state.get("metadata") or {}),
            "category": decision.category.value,
            "importance": decision.importance.value,
            "policy_reason": decision.reason,
            "memory_hint": decision.memory_hint,
        }

        result = self.memory.add_turn(
            user_id=state["user_id"], # type: ignore
            user_name=state.get("user_name", ""),
            user_text=state.get("user_text", ""),
            assistant_text=state.get("assistant_text", ""),
            session_id=state.get("session_id", ""),
            turn_id=state.get("turn_id", ""),
            agent_id=state.get("agent_id") or self.default_agent_id,
            metadata=metadata,
        )

        return {
            "store_result": result,
            "metadata": {
                **metadata,
                "memory_store_status": "stored",
            },
        }