from pydantic import BaseModel, Field
from typing import List, Literal

class LinkedInPost(BaseModel):
    titel: str
    text: str

class LinkedInResearchOutput(BaseModel):
    posts: List[LinkedInPost]

class TextTransformRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Der zu transformierende Text")
    transformation: Literal["extend", "shorten", "rephrase"] = Field(
        ..., 
        description="Art der gewünschten Transformation"
    )

class TextTransformResponse(BaseModel):
    transformed_text: str = Field(..., description="Der transformierte Text")
 