"""Prompt adaptation helper placeholder."""

from langchain_core.messages import HumanMessage,SystemMessage,AIMessage

def build_messages(system_prompt:str,user_text:str):
    return [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_text)
    ]