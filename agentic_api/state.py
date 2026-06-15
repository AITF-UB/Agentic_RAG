from typing import TypedDict, Any, Dict, List, Optional

class AgentState(TypedDict):
    """Shared state for the beta-agentic LangGraph state machine."""
    
    # 1. Inputs & Configuration
    request_params: dict
    tipe: str
    level: Optional[str]
    
    # 2. Context from RAG
    rag_context: str
    sumber_text: str
    image_context: str        # Text descriptions of images from RAG
    visual_assets: List[str]  # Base64 data URLs for frontend rendering
    
    # 2.5 Revision
    instruksi_revisi: Optional[str]
    
    # 3. Generation Process
    generated_content: Any    # Raw output from the generator node
    evaluator_result: Any     # Output from the evaluator node
    revision_count: int       # Tracks how many times it has looped for revision
    
    # 5. Output
    final_payload: dict       # The structured data to be returned via the API
