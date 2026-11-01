import httpx
import pytest
from backend.integrations.telemetry_transport import LocalMediaTransport


def test_signed_media_upload_reaches_internal_minio_with_original_signature_and_host():
    seen = []
    client = httpx.Client(transport=LocalMediaTransport(httpx.MockTransport(
        lambda request: seen.append(request) or httpx.Response(200)
    )))
    query = "X-Amz-Credential=fixture%2Fscope&X-Amz-Signature=fixture-signature"
    response = client.put(
        "http://localhost:9090/langfuse/media/fixture.png?" + query,
        content=b"fixture-image-bytes",
        headers={"Authorization": "Bearer must-not-forward", "Cookie": "private=discard",
                 "x-amz-checksum-sha256": "fixture-checksum"},
    )
    assert response.status_code == 200
    assert seen[0].url.host == "langfuse-minio" and seen[0].url.port == 9000
    assert seen[0].headers["host"] == "localhost:9090"
    assert seen[0].url.query == query.encode()
    assert seen[0].content == b"fixture-image-bytes"
    assert "authorization" not in seen[0].headers and "cookie" not in seen[0].headers
    assert seen[0].headers["x-amz-checksum-sha256"] == "fixture-checksum"
    client.close()


@pytest.mark.parametrize("method,url", [
    ("GET", "http://localhost:9090/langfuse/media/a?X-Amz-Signature=x&X-Amz-Credential=y"),
    ("PUT", "http://localhost:9090/langfuse/events/a?X-Amz-Signature=x&X-Amz-Credential=y"),
    ("PUT", "http://localhost:9090/langfuse/media/a"),
    ("PUT", "https://localhost:9090/langfuse/media/a?X-Amz-Signature=x&X-Amz-Credential=y"),
    ("PUT", "http://other.example:9090/langfuse/media/a?X-Amz-Signature=x&X-Amz-Credential=y"),
])
def test_transport_does_not_rewrite_other_requests(method, url):
    seen = []
    client = httpx.Client(transport=LocalMediaTransport(httpx.MockTransport(
        lambda request: seen.append(str(request.url)) or httpx.Response(200)
    )))
    client.request(method, url)
    assert seen == [url]
    client.close()
