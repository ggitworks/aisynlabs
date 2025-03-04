from typing import List, Optional

from pydantic import BaseModel


class Persona(BaseModel):
    name: str
    age: str
    gender: str
    location: str
    occupation: str
    income: str
    education: str
    personality: List[str]
    background: str
    interests: List[str]
    communication_style: List[str]
    core_values: Optional[str] = None
    knowledge_domain: List[str]


class PersonasOutput(BaseModel):
    personas: List[Persona]
