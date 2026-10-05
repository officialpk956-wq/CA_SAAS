import pytest
from backend.gst_copilot.model_gateway.categorization import CategoryRequest, MockCategoryGateway, validated_suggestion, CATEGORIES

@pytest.mark.parametrize("description,expected", [("Corrugated cartons", "Packaging"), ("printer paper", "Office supplies"), ("courier charges", "Transport"), ("Scenario 1", None), ("printer paper and courier charges", None)])
def test_mock_categories(description, expected):
    request = CategoryRequest(request_id="synthetic-1", description=description, allowed_categories=list(CATEGORIES))
    result = validated_suggestion(MockCategoryGateway(), request)
    assert result.category == expected
    assert result.status == ("suggested" if expected else "needs_review")

@pytest.mark.parametrize("change", [{"request_id":"wrong"}, {"category":"Invented"}, {"evidence_text":"not in input"}, {"extra":"field"}, {"status":"needs_review"}, {"schema_version":"2"}])
def test_invalid_gateway_output_abstains(change):
    request = CategoryRequest(request_id="synthetic-1", description="corrugated cartons", allowed_categories=list(CATEGORIES))
    class Gateway:
        def suggest(self, request):
            return dict(MockCategoryGateway().suggest(request), **change)
    result = validated_suggestion(Gateway(), request)
    assert result.category is None
    assert result.model_version == "gateway-fallback-v1"

def test_gateway_failure_abstains():
    class Gateway:
        def suggest(self, request): raise TimeoutError("Unavailable")
    result = validated_suggestion(Gateway(), CategoryRequest(request_id="1", description="cartons", allowed_categories=list(CATEGORIES)))
    assert result.status == "needs_review"
