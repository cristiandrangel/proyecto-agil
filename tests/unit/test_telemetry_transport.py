import httpx
import pytest
from backend.integrations.telemetry_transport import LocalMediaTransport


@pytest.mark.parametrize("public_port", [9090, 19090])
def test_signed_media_upload_reaches_internal_minio_with_original_signature_and_host(public_port):
    seen = []
    client = httpx.Client(
        transport=LocalMediaTransport(
            httpx.MockTransport(lambda request: seen.append(request) or httpx.Response(200)),
            media_public_endpoint=f"http://localhost:{public_port}",
        )
    )
    query = "X-Amz-Credential=fixture%2Fscope&X-Amz-Signature=fixture-signature"
    response = client.put(
        f"http://localhost:{public_port}/langfuse/media/fixture.png?" + query,
        content=b"fixture-image-bytes",
        headers={
            "Authorization": "Bearer must-not-forward",
            "Cookie": "private=discard",
            "x-amz-checksum-sha256": "fixture-checksum",
        },
    )
    assert response.status_code == 200
    assert seen[0].url.host == "langfuse-minio" and seen[0].url.port == 9000
    assert seen[0].headers["host"] == f"localhost:{public_port}"
    assert seen[0].url.query == query.encode()
    assert seen[0].content == b"fixture-image-bytes"
    assert "authorization" not in seen[0].headers and "cookie" not in seen[0].headers
    assert seen[0].headers["x-amz-checksum-sha256"] == "fixture-checksum"
    client.close()


@pytest.mark.parametrize(
    "method,url",
    [
        ("GET", "http://localhost:9090/langfuse/media/a?X-Amz-Signature=x&X-Amz-Credential=y"),
        ("PUT", "http://localhost:9090/langfuse/events/a?X-Amz-Signature=x&X-Amz-Credential=y"),
        ("PUT", "http://localhost:9090/langfuse/media/a"),
        ("PUT", "https://localhost:9090/langfuse/media/a?X-Amz-Signature=x&X-Amz-Credential=y"),
        ("PUT", "http://other.example:9090/langfuse/media/a?X-Amz-Signature=x&X-Amz-Credential=y"),
    ],
)
def test_transport_does_not_rewrite_other_requests(method, url):
    seen = []
    client = httpx.Client(
        transport=LocalMediaTransport(
            httpx.MockTransport(
                lambda request: seen.append(str(request.url)) or httpx.Response(200)
            )
        )
    )
    client.request(method, url)
    assert seen == [url]
    client.close()


def test_configured_guest_media_port_does_not_redirect_the_owner_minio():
    seen = []
    client = httpx.Client(
        transport=LocalMediaTransport(
            httpx.MockTransport(lambda request: seen.append(request.url) or httpx.Response(200)),
            media_public_endpoint="http://localhost:19090",
        )
    )
    client.put("http://localhost:9090/langfuse/media/a?X-Amz-Signature=x&X-Amz-Credential=y")
    assert seen[0].host == "localhost" and seen[0].port == 9090
    client.close()
