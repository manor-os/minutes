from api.services.summarization_service import SummarizationService


def test_accepts_injected_client_and_model():
    sentinel_client = object()
    svc = SummarizationService(client=sentinel_client, model="injected-model")
    assert svc.client is sentinel_client
    assert svc.model == "injected-model"
