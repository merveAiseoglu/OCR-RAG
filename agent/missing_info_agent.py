from typing import TypedDict, List
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

# 1. State Definition
class ValidationState(TypedDict):
    extracted_text: str
    validation_results: dict

# 2. Structured Output Schema
class ValidationResult(BaseModel):
    is_complete: bool = Field(
        description="True if the document has all standard required fields, False otherwise."
    )
    missing_fields: List[str] = Field(
        description="List of missing standard fields (e.g., 'tc_no', 'date'). Empty if is_complete is True."
    )
    document_type: str = Field(
        description="Inferred type of the document (e.g., 'Petition', 'Invoice', 'Application Form')."
    )

# 3. Node Function: Validate Document
def validate_document(state: ValidationState) -> dict:
    """
    Analyzes the extracted text to infer document type and find missing standard fields.
    """
    llm = ChatOpenAI(model="gpt-4o-mini")
    structured_llm = llm.with_structured_output(ValidationResult)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an intelligent document validator. Your task is to read the extracted text, infer the type of document it is, and check if any standard required fields for that document type are missing. Be precise."),
        ("user", "Extracted Document Text:\n{extracted_text}")
    ])
    
    chain = prompt | structured_llm
    
    # Execute the chain
    result = chain.invoke({
        "extracted_text": state["extracted_text"]
    })
    
    # Robust serialization
    if hasattr(result, "model_dump"):
        res_dict = result.model_dump()
    elif hasattr(result, "dict"):
        res_dict = result.dict()
    elif isinstance(result, dict):
        res_dict = result
    else:
        res_dict = dict(result)
        
    return {"validation_results": res_dict}

# 4. Build the StateGraph
workflow = StateGraph(ValidationState)

# Add node
workflow.add_node("validate_document", validate_document)

# Add edges
workflow.add_edge(START, "validate_document")
workflow.add_edge("validate_document", END)

# Compile the graph
validator_app = workflow.compile()
