"""
Summarization Evaluation Module
Evaluates the quality of summarization in the AI's answer
"""

import os
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Use global OpenAI client
try:
    from ...core.openai_manager import get_openai_client
    client = get_openai_client()
except ImportError:
    # Fallback for backward compatibility
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def evaluate_summarization(query: str, answer: str, user_id: str = None, session_id: str = None) -> dict:
    """
    Evaluate the quality of summarization in the answer
    
    Args:
        query: The original question or prompt
        answer: The AI's response to evaluate
        user_id: User ID for tracking
        session_id: Session ID for tracking
        
    Returns:
        dict: {"score": float, "reasoning": str}
    """
    
    prompt = f"""
    You are an expert evaluator assessing the summarization quality of AI responses.
    
    Evaluate the following answer for summarization quality:
    
    Query: {query}
    Answer: {answer}
    
    Consider the following criteria for good summarization:
    1. Conciseness - Information is presented efficiently without unnecessary verbosity
    2. Completeness - Key points are not omitted despite being concise
    3. Clarity - The summary is easy to understand and well-structured
    4. Accuracy - The summarized information correctly represents the source material
    5. Coherence - Ideas flow logically and connections are clear
    6. Appropriate length - The summary length is suitable for the content and context
    7. Key information retention - Most important points are preserved and emphasized
    
    Note: If the query doesn't explicitly ask for summarization, evaluate how well the answer 
    summarizes complex information or presents it in a digestible format.
    
    Provide your evaluation as a JSON object with:
    - "score": A float between 0.0 (poor summarization) and 1.0 (excellent summarization)
    - "reasoning": A detailed explanation of your evaluation
    
    Focus on how effectively the answer distills and presents information.
    """
    
    try:
        # Use global OpenAI proxy with proper service attribution
        from ...core.openai_proxy import get_openai_proxy
        proxy = get_openai_proxy()
        
        response = await proxy.chat_completion(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert AI response evaluator specializing in summarization quality. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=500,
            user_id=user_id or session_id,
            service_name="summarization_evaluation",
            operation_name="evaluate_summarization"
        )
        
        result = json.loads(response.choices[0].message.content)
        
        # Ensure score is within valid range
        score = max(0.0, min(1.0, float(result.get("score", 0.0))))
        reasoning = result.get("reasoning", "No reasoning provided")
        
        return {"score": score, "reasoning": reasoning}
        
    except Exception as e:
        return {"score": 0.0, "reasoning": f"Error during evaluation: {str(e)}"}
