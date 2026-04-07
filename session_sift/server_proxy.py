from __future__ import annotations

import asyncio

from aiohttp import ClientSession, ClientTimeout, web

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.providers import extract_stream_text, extract_text_from_json, normalize_request, resolve_provider


CONFIG_KEY = web.AppKey("session_sift_config", SessionSiftConfig)
ENGINE_KEY = web.AppKey("session_sift_engine", SessionSiftEngine)
SESSION_FACTORY_KEY = web.AppKey("session_factory", object)


def _sanitize_headers(headers: web.BaseRequest.headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in {"host", "content-length"}
    }


async def proxy_handler(request: web.Request) -> web.StreamResponse:
    config = request.app[CONFIG_KEY]
    engine = request.app[ENGINE_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    body = await request.json()
    refined, report = await engine.refine(body.get("messages", []))
    body["messages"] = refined
    provider = resolve_provider(
        request.headers.get("X-Session-Sift-Upstream-Provider", config.upstream_provider)
    )
    upstream_path, payload = normalize_request(provider, request.path, body)
    headers = _sanitize_headers(request.headers)
    timeout = ClientTimeout(total=config.request_timeout_secs)
    async with session_factory(timeout=timeout) as session:
        async with session.post(
            f"{config.upstream_url.rstrip('/')}{upstream_path}",
            json=payload,
            headers=headers,
        ) as upstream_response:
            if body.get("stream"):
                response = web.StreamResponse(
                    status=upstream_response.status,
                    headers={
                        "Content-Type": "text/event-stream",
                        "Cache-Control": "no-cache",
                        "X-Session-Sift-Savings": f"{report.savings_pct:.1f}%",
                    },
                )
                await response.prepare(request)
                full_content: list[str] = []
                pending_event = ""
                async for chunk in upstream_response.content.iter_any():
                    decoded = chunk.decode("utf-8", errors="replace")
                    pending_event += decoded
                    while "\n\n" in pending_event:
                        event, pending_event = pending_event.split("\n\n", 1)
                        extracted = extract_stream_text(provider, f"{event}\n\n")
                        if extracted:
                            full_content.append(extracted)
                    await response.write(chunk)
                if pending_event.strip():
                    extracted = extract_stream_text(provider, pending_event)
                    if extracted:
                        full_content.append(extracted)
                full_text = "".join(part for part in full_content if part)
                if full_text:
                    asyncio.create_task(
                        engine.append_turn({"role": "assistant", "content": full_text})
                    )
                await response.write_eof()
                return response

            raw_payload = await upstream_response.read()
            try:
                response_json = await upstream_response.json()
            except Exception:
                response_json = None
            if response_json is not None:
                content = extract_text_from_json(provider, response_json)
                if content:
                    await engine.append_turn({"role": "assistant", "content": content})
            return web.Response(
                body=raw_payload,
                status=upstream_response.status,
                headers={
                    "Content-Type": upstream_response.headers.get(
                        "Content-Type", "application/json"
                    ),
                    "X-Session-Sift-Savings": f"{report.savings_pct:.1f}%",
                },
            )


def create_app(
    config: SessionSiftConfig | None = None,
    engine: SessionSiftEngine | None = None,
    session_factory=ClientSession,
) -> web.Application:
    runtime_config = config or SessionSiftConfig()
    runtime_engine = engine or SessionSiftEngine(runtime_config)
    app = web.Application()
    app[CONFIG_KEY] = runtime_config
    app[ENGINE_KEY] = runtime_engine
    app[SESSION_FACTORY_KEY] = session_factory
    app.router.add_post("/v1/chat/completions", proxy_handler)
    app.router.add_post("/v1/messages", proxy_handler)
    return app


if __name__ == "__main__":
    runtime_config = SessionSiftConfig()
    web.run_app(
        create_app(runtime_config),
        host=runtime_config.proxy_host,
        port=runtime_config.proxy_port,
    )