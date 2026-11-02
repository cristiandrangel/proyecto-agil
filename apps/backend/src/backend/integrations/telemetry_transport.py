"""Reach the local MinIO upload endpoint from inside Docker without changing SigV4."""

from urllib.parse import urlsplit

import httpx


class LocalMediaTransport(httpx.BaseTransport):
    def __init__(self, transport=None, *, media_public_endpoint="http://localhost:9090"):
        public = urlsplit(media_public_endpoint)
        if (
            public.scheme != "http"
            or public.hostname != "localhost"
            or not public.port
            or public.path not in ("", "/")
            or public.username
            or public.password
            or public.query
            or public.fragment
        ):
            raise ValueError("Local media endpoint must be an explicit localhost HTTP origin")
        self.public_port = public.port
        self.transport = transport or httpx.HTTPTransport()

    def handle_request(self, request):
        # Langfuse signs a browser-reachable localhost URL. Inside the backend
        # that address is another container. Route only signed media PUTs to
        # MinIO, preserving the signed Host, path, query and body exactly.
        if (
            request.method == "PUT"
            and request.url.scheme == "http"
            and request.url.host == "localhost"
            and request.url.port == self.public_port
            and request.url.path.startswith("/langfuse/media/")
            and "X-Amz-Signature" in request.url.params
            and "X-Amz-Credential" in request.url.params
        ):
            headers = {
                k: v
                for k, v in request.headers.items()
                if k.lower() not in {"authorization", "cookie"}
            }
            headers["host"] = request.url.netloc.decode("ascii")
            request = httpx.Request(
                request.method,
                request.url.copy_with(host="langfuse-minio", port=9000),
                headers=headers,
                stream=request.stream,
                extensions=request.extensions,
            )
        return self.transport.handle_request(request)

    def close(self):
        self.transport.close()


def langfuse_http_client(settings):
    if urlsplit(settings.langfuse_base_url).hostname == "langfuse-web":
        return httpx.Client(
            transport=LocalMediaTransport(
                media_public_endpoint=getattr(
                    settings, "langfuse_media_public_endpoint", "http://localhost:9090"
                )
            ),
            timeout=20,
        )
    return None
