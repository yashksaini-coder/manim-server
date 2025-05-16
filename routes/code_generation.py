from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os
from openai import OpenAI
from groq import Groq

router = APIRouter()

class CodeGenRequest(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"

@router.post("/v1/generate/code")
async def generate_code(body: CodeGenRequest) -> dict:
    """
    Generate Manim code using an LLM (OpenAI or Groq) based on the provided prompt and model.
    """
    prompt_content = body.prompt
    model = body.model

    general_system_prompt = (
        """
You are an assistant that knows about Manim. Manim is a mathematical animation engine that is used to create videos programmatically.

The following is an example of the code:

```python
from manim import *
from math import *

class GenScene(Scene):
    def construct(self):
        c = Circle(color=BLUE)
        self.play(Create(c))
```

# Rules
1. Always use GenScene as the class name, otherwise, the code will not work.
2. Always use self.play() to play the animation, otherwise, the code will not work.
3. Do not use text to explain the code, only the code.
4. Do not explain the code, only the code.
5. You are strictly prohibited from explaining the code.
6. Do not use any other text than the code.
        """
    )

    try:
        messages = [
            {"role": "system", "content": general_system_prompt},
            {"role": "user", "content": prompt_content},
        ]

        if model.startswith("openai-"):
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
            code = response.choices[0].message.content
            return {"code": code}
        else:
            client = Groq(api_key=os.getenv("GROQ_API_KEY"))
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=1000,
            )
            code = response.choices[0].message.content
            return {"code": code}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

