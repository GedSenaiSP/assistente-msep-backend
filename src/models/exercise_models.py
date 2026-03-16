from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any

class GenerateExercisesRequest(BaseModel):
    user_id: str
    plan_id: str
    sa_index: int
    quantities: Dict[str, int] = Field(
        default={
            "multiple_choice": 5,
            "essay": 3,
            "fill_in_the_blank": 2,
            "practical": 1
        },
        description="Quantidade de questões por tipo. Chaves: 'multiple_choice', 'essay', 'fill_in_the_blank', 'practical'"
    )
