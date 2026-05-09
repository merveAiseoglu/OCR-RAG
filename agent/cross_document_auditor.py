from typing import TypedDict, List
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END

# 1. State Definition
class AuditorState(TypedDict):
    doc1_text: str
    doc2_text: str
    comparison_results: dict
    executive_summary: str

# 2. Structured Output Schema
class ComparisonResult(BaseModel):
    changed_clauses: List[str] = Field(
        description="Clauses that were altered between doc1 and doc2."
    )
    discrepancies: List[str] = Field(
        description="Mismatches in prices, ratios, or dates."
    )
    missing_sections: List[str] = Field(
        description="Parts present in doc1 but missing in doc2."
    )
    risk_score: int = Field(
        description="A score from 1 to 10 indicating the level of risk/discrepancy."
    )

# 3. Node Function 1: Compare Documents
def compare_documents(state: AuditorState) -> dict:
    """
    Compares two document texts using gpt-4o and structured output.
    Returns the comparison result as a dictionary to update the state.
    """
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    structured_llm = llm.with_structured_output(ComparisonResult)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an analytical auditor. Your task is to strictly compare two versions of a document and identify changed clauses, discrepancies (like prices, ratios, or dates), and missing sections. Provide a risk score from 1 to 10 based on the severity of the differences."),
        ("user", "Please compare the following documents.\n\nDocument 1:\n{doc1_text}\n\nDocument 2:\n{doc2_text}")
    ])
    
    chain = prompt | structured_llm
    
    # Execute the chain
    result = chain.invoke({
        "doc1_text": state["doc1_text"],
        "doc2_text": state["doc2_text"]
    })
    
    if hasattr(result, "model_dump"):
        comp_res = result.model_dump()
    elif hasattr(result, "dict"):
        comp_res = result.dict()
    elif isinstance(result, dict):
        comp_res = result
    else:
        comp_res = dict(result)
        
    # Return as a dictionary to update AuditorState's comparison_results
    return {"comparison_results": comp_res}

# 4. Node Function 2: Generate Summary
def generate_summary(state: AuditorState) -> dict:
    """
    Reads the comparison results and generates a 2-3 sentence executive summary
    using gpt-4o-mini. Returns the summary string to update the state.
    """
    llm = ChatOpenAI(model="gpt-4o-mini")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an executive assistant. Your task is to write a concise 2-3 sentence executive summary for top management based on document comparison results. Ensure you mention the risk score and major discrepancies/changes clearly."),
        ("user", "Comparison Results:\n{comparison_results}")
    ])
    
    chain = prompt | llm
    
    # Execute the chain
    result = chain.invoke({
        "comparison_results": state["comparison_results"]
    })
    
    # Return the summary content to update AuditorState's executive_summary
    return {"executive_summary": str(result.content)}

# 5. Build the StateGraph
workflow = StateGraph(AuditorState)

# Add nodes
workflow.add_node("compare_documents", compare_documents)
workflow.add_node("generate_summary", generate_summary)

# Add edges to define the sequential flow
workflow.add_edge(START, "compare_documents")
workflow.add_edge("compare_documents", "generate_summary")
workflow.add_edge("generate_summary", END)

# Compile the graph
auditor_app = workflow.compile()

