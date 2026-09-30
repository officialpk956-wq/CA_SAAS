"""Local mock only. No network access, training, or tax decisions."""
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, model_validator

CATEGORIES = ('Packaging', 'Office supplies', 'Transport', 'Inventory', 'Professional services')

class CategoryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['1'] = '1'
    request_id: str
    description: str
    business_context: str = ''
    allowed_categories: list[str]

class CategoryResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal['1'] = '1'
    request_id: str
    model_version: str = Field(min_length=1)
    status: Literal['suggested', 'needs_review']
    category: str | None = None
    evidence_text: str | None = None

    @model_validator(mode='after')
    def check_status(self):
        if self.status == 'suggested' and (not self.category or not self.evidence_text):
            raise ValueError('A suggestion requires category and evidence')
        if self.status == 'needs_review' and (self.category is not None or self.evidence_text is not None):
            raise ValueError('Abstention cannot contain a category')
        return self

class CategoryGateway(Protocol):
    def suggest(self, request: CategoryRequest) -> dict: ...

class MockCategoryGateway:
    def suggest(self, request: CategoryRequest) -> dict:
        # Deliberately small examples, not a semantic model.
        terms = {'Packaging': ('corrugated cartons', 'packaging boxes'), 'Office supplies': ('printer paper', 'office stationery'), 'Transport': ('freight delivery', 'courier charges')}
        hits = [category for category, keywords in terms.items() if category in request.allowed_categories and any(k in request.description.lower() for k in keywords)]
        category = hits[0] if len(hits) == 1 else None
        return {'schema_version':'1', 'request_id':request.request_id, 'model_version':'mock-category-v1', 'status':'suggested' if category else 'needs_review', 'category':category, 'evidence_text':request.description if category else None}

def validated_suggestion(gateway: CategoryGateway, request: CategoryRequest) -> CategoryResponse:
    try:
        response = CategoryResponse.model_validate(gateway.suggest(request))
        if response.request_id != request.request_id:
            raise ValueError('Request mismatch')
        if response.category is not None and response.category not in request.allowed_categories:
            raise ValueError('Category outside taxonomy')
        if response.evidence_text and response.evidence_text not in request.description:
            raise ValueError('Evidence is not in source description')
        return response
    except Exception:
        return CategoryResponse(request_id=request.request_id, model_version='gateway-fallback-v1', status='needs_review')
