from __future__ import annotations

import dataclasses
import http.server
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import traceback
import urllib.error
import urllib.request
import unittest
from email.message import Message
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from model_provider import (  # noqa: E402
    FakeModelProvider,
    FakeModelProviderOutcome,
    ModelMessage,
    ModelMessageRole,
    ModelProvider,
    ModelProviderError,
    ModelProviderErrorKind,
    ModelRequest,
    ModelResult,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from model_provider.openai_compatible import _TransportResponse  # noqa: E402


class CaptureTransport:
    def __init__(
        self,
        response: tuple[int, dict[str, str], bytes] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response or (
            200,
            {},
            b'{"choices":[{"message":{"content":"ok"}}]}',
        )
        self.error = error
        self.calls: list[tuple[urllib.request.Request, int | float, int]] = []

    def __call__(
        self,
        request: urllib.request.Request,
        timeout: int | float,
        maximum: int,
    ) -> tuple[int, dict[str, str], bytes]:
        self.calls.append((request, timeout, maximum))
        if self.error is not None:
            raise self.error
        return self.response


class _LoopbackServer:
    def __init__(
        self,
        status: int,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                owner.hits += 1
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.hits = 0
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1/chat/completions"

    def __enter__(self) -> "_LoopbackServer":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class ModelProviderTestCase(unittest.TestCase):
    def request(self, **overrides: object) -> ModelRequest:
        values: dict[str, object] = {
            "model": "opaque-model-v1",
            "messages": (
                ModelMessage(ModelMessageRole.SYSTEM, "System secret"),
                ModelMessage(ModelMessageRole.USER, "User prompt"),
            ),
            "timeout_seconds": 30,
        }
        values.update(overrides)
        return ModelRequest(**values)


class ModelProviderContractTest(ModelProviderTestCase):

    def test_contract_is_frozen_typed_minimal_and_secret_safe(self) -> None:
        message = ModelMessage(ModelMessageRole.USER, "prompt-secret")
        request = self.request(messages=(message,))
        result = ModelResult("output-secret")
        self.assertEqual(
            {item.name for item in dataclasses.fields(request)},
            {"model", "messages", "timeout_seconds"},
        )
        self.assertEqual(
            {role.value for role in ModelMessageRole},
            {"system", "user", "assistant"},
        )
        self.assertNotIn("prompt-secret", repr(message))
        self.assertNotIn("prompt-secret", repr(request))
        self.assertNotIn("output-secret", repr(result))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            message.content = "changed"

    def test_request_strictness_rejects_coercion_controls_and_bad_timeout(self) -> None:
        for model in (
            None,
            "",
            "   ",
            "bad\nmodel",
            "bad\u2028model",
            "bad\ud800model",
            "x" * 257,
        ):
            with self.subTest(model=model), self.assertRaises((TypeError, ValueError)):
                self.request(model=model)
        for messages in (None, [], (), ({"role": "user"},)):
            with self.subTest(messages=messages), self.assertRaises((TypeError, ValueError)):
                self.request(messages=messages)
        for timeout in (True, None, 0, -1, math.nan, math.inf, 601):
            with self.subTest(timeout=timeout), self.assertRaises((TypeError, ValueError)):
                self.request(timeout_seconds=timeout)

        class StrangeInt(int):
            pass

        with self.assertRaises(TypeError):
            self.request(timeout_seconds=StrangeInt(3))

    def test_message_result_and_error_types_are_strict(self) -> None:
        with self.assertRaises(TypeError):
            ModelMessage("user", "text")
        with self.assertRaises(TypeError):
            ModelMessage(ModelMessageRole.USER, None)
        with self.assertRaises(ValueError):
            ModelMessage(ModelMessageRole.USER, "bad\ud800content")
        self.assertEqual(ModelResult("").output_text, "")
        with self.assertRaises(TypeError):
            ModelResult(None)
        error = ModelProviderError(
            ModelProviderErrorKind.TIMEOUT,
            "Model provider request timed out",
        )
        self.assertEqual(error.kind, ModelProviderErrorKind.TIMEOUT)
        self.assertNotIn("Model provider request timed out", repr(error))
        with self.assertRaises(TypeError):
            ModelProviderError("timeout", "failed")
        with self.assertRaises(TypeError):
            ModelProviderError(ModelProviderErrorKind.TIMEOUT, None)

    def test_provider_protocol_and_public_exports_are_bounded(self) -> None:
        fake = FakeModelProvider([FakeModelProviderOutcome.success("ok")])
        self.assertIsInstance(fake, ModelProvider)
        import model_provider

        self.assertEqual(
            set(model_provider.__all__),
            {
                "FakeModelProvider",
                "FakeModelProviderOutcome",
                "ModelMessage",
                "ModelMessageRole",
                "ModelProvider",
                "ModelProviderError",
                "ModelProviderErrorKind",
                "ModelRequest",
                "ModelResult",
                "OpenAICompatibleConfig",
                "OpenAICompatibleProvider",
            },
        )


class FakeModelProviderTest(ModelProviderTestCase):
    def test_fake_success_error_recording_and_exhaustion(self) -> None:
        expected_error = ModelProviderError(
            ModelProviderErrorKind.REQUEST_REJECTED,
            "Primary test rejection",
        )
        fake = FakeModelProvider(
            [
                FakeModelProviderOutcome.success("first"),
                FakeModelProviderOutcome.failure(expected_error),
            ]
        )
        request = self.request()
        self.assertEqual(fake.generate(request).output_text, "first")
        with self.assertRaises(ModelProviderError) as caught:
            fake.generate(request)
        self.assertIsNot(caught.exception, expected_error)
        self.assertEqual(caught.exception.kind, expected_error.kind)
        self.assertEqual(str(caught.exception), str(expected_error))
        with self.assertRaises(ModelProviderError) as exhausted:
            fake.generate(request)
        self.assertEqual(exhausted.exception.kind, ModelProviderErrorKind.UNAVAILABLE)
        self.assertEqual(fake.requests, [request, request, request])

    def test_fake_reused_error_source_produces_fresh_deterministic_errors(self) -> None:
        source = ModelProviderError(ModelProviderErrorKind.TIMEOUT, "stable failure")
        fake = FakeModelProvider(
            [
                FakeModelProviderOutcome.failure(source),
                FakeModelProviderOutcome.failure(source),
            ]
        )
        caught: list[ModelProviderError] = []
        for _ in range(2):
            with self.assertRaises(ModelProviderError) as raised:
                fake.generate(self.request())
            caught.append(raised.exception)
        self.assertIsNot(caught[0], caught[1])
        self.assertIsNot(caught[0], source)
        self.assertEqual(
            [(error.kind, str(error)) for error in caught],
            [(source.kind, str(source)), (source.kind, str(source))],
        )
        self.assertIsNone(source.__traceback__)
        self.assertEqual(
            len(traceback.extract_tb(caught[0].__traceback__)),
            len(traceback.extract_tb(caught[1].__traceback__)),
        )

    def test_fake_rejects_malformed_outcomes_and_requests(self) -> None:
        with self.assertRaises(ValueError):
            FakeModelProviderOutcome()
        with self.assertRaises(ValueError):
            FakeModelProviderOutcome(
                result=ModelResult("x"),
                error=ModelProviderError(ModelProviderErrorKind.TIMEOUT, "x"),
            )
        with self.assertRaises(TypeError):
            FakeModelProvider(["not-an-outcome"])
        with self.assertRaises(TypeError):
            FakeModelProvider([]).generate("request")


class OpenAICompatibleProviderTest(ModelProviderTestCase):
    def provider(
        self,
        transport: CaptureTransport,
        **config_overrides: object,
    ) -> OpenAICompatibleProvider:
        values: dict[str, object] = {
            "endpoint_url": "https://models.example/v1/chat/completions",
        }
        values.update(config_overrides)
        return OpenAICompatibleProvider(
            OpenAICompatibleConfig(**values),
            transport=transport,
        )

    def assert_provider_error(
        self,
        transport: CaptureTransport,
        kind: ModelProviderErrorKind,
    ) -> ModelProviderError:
        with self.assertRaises(ModelProviderError) as caught:
            self.provider(transport).generate(self.request())
        self.assertEqual(caught.exception.kind, kind)
        return caught.exception

    def test_request_serialization_is_minimal_utf8_and_single_attempt(self) -> None:
        transport = CaptureTransport()
        request = self.request(
            messages=(
                ModelMessage(ModelMessageRole.SYSTEM, "réponse concise"),
                ModelMessage(ModelMessageRole.USER, "line 1\n{\"x\": 1}"),
                ModelMessage(ModelMessageRole.ASSISTANT, "prior"),
            ),
            timeout_seconds=12.5,
        )
        result = self.provider(transport).generate(request)
        self.assertEqual(result.output_text, "ok")
        self.assertEqual(len(transport.calls), 1)
        sent, timeout, maximum = transport.calls[0]
        self.assertEqual(timeout, 12.5)
        self.assertEqual(maximum, 8 * 1024 * 1024)
        self.assertEqual(
            json.loads(sent.data.decode("utf-8")),
            {
                "model": "opaque-model-v1",
                "messages": [
                    {"role": "system", "content": "réponse concise"},
                    {"role": "user", "content": "line 1\n{\"x\": 1}"},
                    {"role": "assistant", "content": "prior"},
                ],
            },
        )
        self.assertNotIn("stream", sent.data.decode("utf-8"))
        self.assertNotIn("tools", sent.data.decode("utf-8"))

    def test_api_key_header_is_explicit_and_secret_safe(self) -> None:
        key = "provider-api-key-secret"
        authenticated = CaptureTransport()
        provider = self.provider(authenticated, api_key=key)
        provider.generate(self.request())
        sent = authenticated.calls[0][0]
        self.assertEqual(sent.get_header("Authorization"), f"Bearer {key}")
        self.assertNotIn(key, repr(provider))
        self.assertNotIn(key, repr(provider._config))

        anonymous = CaptureTransport()
        self.provider(anonymous).generate(self.request())
        self.assertIsNone(anonymous.calls[0][0].get_header("Authorization"))

    def test_endpoint_key_and_limit_validation_fail_closed(self) -> None:
        with self.assertRaises(TypeError):
            OpenAICompatibleConfig(None)
        invalid_endpoints = (
            "file:///tmp/model",
            "ftp://models.example/generate",
            "data:text/plain,x",
            "https:///missing-host",
            "https://user:password@models.example/generate",
            "https://models.example/generate#fragment",
            "https://models.example/generate?token=secret",
            "https://models.example/generate\r\nInjected: x",
        )
        for endpoint in invalid_endpoints:
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                OpenAICompatibleConfig(endpoint)
        with self.assertRaises(ValueError):
            OpenAICompatibleConfig("http://models.example/generate", api_key="secret")
        with self.assertRaises(TypeError):
            OpenAICompatibleConfig("https://models.example/generate", api_key=7)
        for key in ("", "bad key", "bad\r\nkey", "bad\x00key", "clé"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                OpenAICompatibleConfig("https://models.example/generate", api_key=key)
        for limit in (True, 0, -1, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                OpenAICompatibleConfig(
                    "https://models.example/generate",
                    max_response_bytes=limit,
                )

    def test_response_limit_configuration_has_hard_ceiling(self) -> None:
        ceiling = 8 * 1024 * 1024

        class IntSubclass(int):
            pass

        for value in (1, ceiling - 1, ceiling):
            self.assertEqual(
                OpenAICompatibleConfig(
                    "https://models.example/generate",
                    max_response_bytes=value,
                ).max_response_bytes,
                value,
            )
        rejected = (
            ("bool", True),
            ("subclass", IntSubclass(1)),
            ("float", 1.0),
            ("string", "1"),
            ("none", None),
            ("zero", 0),
            ("negative", -1),
            ("max-plus-one", ceiling + 1),
            ("4301-digits", 10**4300),
            ("10001-digits", 10**10000),
        )
        for label, value in rejected:
            with self.subTest(label=label), self.assertRaises(ValueError) as caught:
                OpenAICompatibleConfig(
                    "https://models.example/generate",
                    max_response_bytes=value,
                )
            self.assertNotIn("4300 digits", str(caught.exception))

        valid_document = b'{"choices":[{"message":{"content":"ok"}}]}'
        exact_ceiling_body = valid_document + b" " * (ceiling - len(valid_document))
        self.assertEqual(
            self.provider(
                CaptureTransport((200, {}, exact_ceiling_body)),
                max_response_bytes=ceiling,
            ).generate(self.request()).output_text,
            "ok",
        )
        ceiling_error = self.assert_provider_error_with_config(
            CaptureTransport((200, {}, exact_ceiling_body + b" ")),
            ModelProviderErrorKind.INVALID_RESPONSE,
            max_response_bytes=ceiling,
        )
        self.assertIn("exceeds", str(ceiling_error))

        smaller_limit = 1024
        exact_small_body = valid_document + b" " * (
            smaller_limit - len(valid_document)
        )
        self.assertEqual(
            self.provider(
                CaptureTransport((200, {}, exact_small_body)),
                max_response_bytes=smaller_limit,
            ).generate(self.request()).output_text,
            "ok",
        )
        self.assert_provider_error_with_config(
            CaptureTransport((200, {}, exact_small_body + b" ")),
            ModelProviderErrorKind.INVALID_RESPONSE,
            max_response_bytes=smaller_limit,
        )
        self.assert_provider_error_with_config(
            CaptureTransport(
                (200, {"Content-Length": "1025"}, valid_document)
            ),
            ModelProviderErrorKind.INVALID_RESPONSE,
            max_response_bytes=smaller_limit,
        )

    def test_valid_response_extra_fields_and_empty_content(self) -> None:
        body = json.dumps(
            {
                "id": "ignored",
                "choices": [
                    {"message": {"content": "", "role": "assistant"}, "extra": 1}
                ],
                "usage": {"tokens": 1},
            }
        ).encode()
        result = self.provider(CaptureTransport((200, {}, body))).generate(self.request())
        self.assertEqual(result.output_text, "")

    def test_invalid_json_utf8_and_raw_body_are_normalized_without_leak(self) -> None:
        bodies = (
            b"not-json secret=provider-token",
            b'\xffsecret=provider-token',
        )
        for body in bodies:
            with self.subTest(body=body):
                error = self.assert_provider_error(
                    CaptureTransport((200, {}, body)),
                    ModelProviderErrorKind.INVALID_RESPONSE,
                )
                rendered = str(error) + repr(error)
                self.assertNotIn("provider-token", rendered)
                self.assertNotIn("JSONDecodeError", rendered)
                self.assertIsNone(error.__context__)
                self.assertIsNone(error.__cause__)
                rendered += "".join(traceback.format_exception(error))
                self.assertNotIn("provider-token", rendered)

    def test_invalid_response_structures_fail_closed(self) -> None:
        invalid = (
            None,
            [],
            {},
            {"choices": None},
            {"choices": {}},
            {"choices": []},
            {"choices": [None]},
            {"choices": [{}]},
            {"choices": [{"message": None}]},
            {"choices": [{"message": {}}]},
            {"choices": [{"message": {"content": None}}]},
            {"choices": [{"message": {"content": 7}}]},
            {"choices": [{"message": {"content": "\ud800"}}]},
        )
        for document in invalid:
            with self.subTest(document=document):
                error = self.assert_provider_error(
                    CaptureTransport((200, {}, json.dumps(document).encode())),
                    ModelProviderErrorKind.INVALID_RESPONSE,
                )
                self.assertEqual(str(error), "Model provider response structure is invalid")

    def test_http_status_mapping_redirect_and_no_retry(self) -> None:
        cases = (
            (302, ModelProviderErrorKind.PROVIDER_FAILED, "redirect was refused"),
            (400, ModelProviderErrorKind.REQUEST_REJECTED, "rejected the request"),
            (429, ModelProviderErrorKind.REQUEST_REJECTED, "rejected the request"),
            (500, ModelProviderErrorKind.PROVIDER_FAILED, "failed to complete"),
            (599, ModelProviderErrorKind.PROVIDER_FAILED, "failed to complete"),
            (204, ModelProviderErrorKind.INVALID_RESPONSE, "unsupported status"),
        )
        for status, kind, message in cases:
            with self.subTest(status=status):
                transport = CaptureTransport(
                    (status, {}, b"secret=provider-token")
                )
                error = self.assert_provider_error(transport, kind)
                self.assertIn(message, str(error))
                self.assertNotIn("provider-token", str(error))
                self.assertEqual(len(transport.calls), 1)

    def test_timeout_connection_and_hostile_transport_errors_are_safe(self) -> None:
        timeout_errors = (
            socket.timeout("secret timeout"),
            TimeoutError("secret timeout"),
            urllib.error.URLError(socket.timeout("secret timeout")),
        )
        for secondary in timeout_errors:
            with self.subTest(error=type(secondary).__name__):
                error = self.assert_provider_error(
                    CaptureTransport(error=secondary),
                    ModelProviderErrorKind.TIMEOUT,
                )
                self.assertEqual(str(error), "Model provider request timed out")
                self.assertIsNone(error.__context__)
                self.assertIsNone(error.__cause__)

        unavailable = (
            ConnectionRefusedError("[Errno 111] secret"),
            urllib.error.URLError("DNS secret"),
        )
        for secondary in unavailable:
            with self.subTest(error=type(secondary).__name__):
                error = self.assert_provider_error(
                    CaptureTransport(error=secondary),
                    ModelProviderErrorKind.UNAVAILABLE,
                )
                self.assertEqual(str(error), "Model provider is unavailable")
                self.assertNotIn("secret", str(error))
                self.assertIsNone(error.__context__)
                self.assertIsNone(error.__cause__)

        hostile_errors = (
            type("TransportFailure\nsecret=token", (Exception,), {})(
                "message secret"
            ),
            ModelProviderError(
                ModelProviderErrorKind.REQUEST_REJECTED,
                "hostile internal provider secret",
            ),
        )
        for hostile in hostile_errors:
            with self.subTest(hostile=type(hostile).__name__):
                error = self.assert_provider_error(
                    CaptureTransport(error=hostile),
                    ModelProviderErrorKind.PROVIDER_FAILED,
                )
                self.assertEqual(str(error), "Model provider transport failed")
                self.assertNotIn("secret", str(error) + repr(error))
                self.assertIsNone(error.__context__)
                self.assertIsNone(error.__cause__)

        key = "explicit-test-key"
        prompt = "private-test-prompt"
        with self.assertRaises(ModelProviderError) as caught:
            self.provider(
                CaptureTransport(error=RuntimeError(f"{key} {prompt}")),
                api_key=key,
            ).generate(
                self.request(
                    messages=(ModelMessage(ModelMessageRole.USER, prompt),)
                )
            )
        rendered = str(caught.exception) + repr(caught.exception)
        self.assertNotIn(key, rendered)
        self.assertNotIn(prompt, rendered)
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)

    def test_transport_base_exceptions_are_not_swallowed(self) -> None:
        for secondary in (KeyboardInterrupt(), SystemExit(7)):
            with self.subTest(error=type(secondary).__name__):
                with self.assertRaises(type(secondary)):
                    self.provider(CaptureTransport(error=secondary)).generate(
                        self.request()
                    )

    def test_request_and_response_limits_are_enforced(self) -> None:
        transport = CaptureTransport()
        provider = self.provider(transport, max_request_bytes=32)
        with mock.patch(
            "model_provider.openai_compatible.json.dumps"
        ) as json_dumps, self.assertRaises(ModelProviderError) as request_error:
            provider.generate(self.request())
        self.assertEqual(
            request_error.exception.kind,
            ModelProviderErrorKind.REQUEST_REJECTED,
        )
        json_dumps.assert_not_called()
        self.assertEqual(transport.calls, [])

        oversized = CaptureTransport(
            (200, {}, b"x" * 65)
        )
        error = self.assert_provider_error_with_config(
            oversized,
            ModelProviderErrorKind.INVALID_RESPONSE,
            max_response_bytes=64,
        )
        self.assertIn("exceeds", str(error))

        declared = CaptureTransport(
            (200, {"Content-Length": "65"}, b"{}")
        )
        declared_error = self.assert_provider_error_with_config(
            declared,
            ModelProviderErrorKind.INVALID_RESPONSE,
            max_response_bytes=64,
        )
        self.assertIsNone(declared_error.__context__)
        self.assertIsNone(declared_error.__cause__)

    def assert_provider_error_with_config(
        self,
        transport: CaptureTransport,
        kind: ModelProviderErrorKind,
        **config: object,
    ) -> ModelProviderError:
        with self.assertRaises(ModelProviderError) as caught:
            self.provider(transport, **config).generate(self.request())
        self.assertEqual(caught.exception.kind, kind)
        return caught.exception

    def test_default_transport_disables_environment_proxies_and_redirects(self) -> None:
        response = mock.MagicMock()
        response.status = 200
        response.headers = Message()
        response.read.return_value = b'{"choices":[{"message":{"content":"ok"}}]}'
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch(
            "model_provider.openai_compatible.urllib.request.build_opener",
            return_value=opener,
        ) as build_opener:
            result = OpenAICompatibleProvider(
                OpenAICompatibleConfig("http://127.0.0.1/v1/chat/completions")
            ).generate(self.request())
        self.assertEqual(result.output_text, "ok")
        self.assertEqual(opener.open.call_count, 1)
        response.read.assert_called_once_with(8 * 1024 * 1024 + 1)
        handlers = build_opener.call_args.args
        proxy_handler = next(
            item for item in handlers if isinstance(item, urllib.request.ProxyHandler)
        )
        redirect_handler = next(
            item for item in handlers if isinstance(item, urllib.request.HTTPRedirectHandler)
        )
        self.assertEqual(proxy_handler.proxies, {})
        self.assertIsNone(
            redirect_handler.redirect_request(None, None, 302, "", {}, "https://other")
        )

    def test_default_transport_rejects_declared_oversize_without_body_read(self) -> None:
        response = mock.MagicMock()
        response.status = 200
        response.headers = Message()
        response.headers["Content-Length"] = "65"
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch(
            "model_provider.openai_compatible.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ModelProviderError) as caught:
                OpenAICompatibleProvider(
                    OpenAICompatibleConfig(
                        "http://127.0.0.1/v1/chat/completions",
                        max_response_bytes=64,
                    )
                ).generate(self.request())
        self.assertEqual(caught.exception.kind, ModelProviderErrorKind.INVALID_RESPONSE)
        response.read.assert_not_called()

    def test_default_transport_rejects_duplicate_content_length(self) -> None:
        response = mock.MagicMock()
        response.status = 200
        response.headers = Message()
        response.headers["Content-Length"] = "2"
        response.headers["Content-Length"] = "2"
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch(
            "model_provider.openai_compatible.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ModelProviderError) as caught:
                OpenAICompatibleProvider(
                    OpenAICompatibleConfig("http://127.0.0.1/model")
                ).generate(self.request())
        self.assertEqual(caught.exception.kind, ModelProviderErrorKind.INVALID_RESPONSE)
        response.read.assert_not_called()

    def test_content_length_is_ascii_bounded_without_integer_conversion(self) -> None:
        valid_body = b'{"choices":[{"message":{"content":"ok"}}]}'
        accepted = (None, "0", "1", "8388608", ("0" * 5000) + "1")
        rejected = (
            "8388609",
            "-1",
            "+1",
            " 1",
            "1 ",
            "abc",
            "1,1",
            "9" * 5000,
            "١٢٣",
            "１２３",
        )
        for content_length in accepted:
            with self.subTest(accepted=content_length):
                headers = (
                    {} if content_length is None else {"Content-Length": content_length}
                )
                for transport_result in (
                    (200, headers, valid_body),
                    _TransportResponse(200, valid_body, content_length),
                ):
                    provider = self.provider(CaptureTransport())
                    provider._transport = (
                        lambda request, timeout, maximum, value=transport_result: value
                    )
                    self.assertEqual(
                        provider.generate(self.request()).output_text,
                        "ok",
                    )

        for content_length in rejected:
            with self.subTest(rejected=content_length[:20]):
                for transport_result in (
                    (200, {"Content-Length": content_length}, valid_body),
                    _TransportResponse(200, valid_body, content_length),
                ):
                    provider = self.provider(CaptureTransport())
                    provider._transport = (
                        lambda request, timeout, maximum, value=transport_result: value
                    )
                    with self.assertRaises(ModelProviderError) as caught:
                        provider.generate(self.request())
                    self.assertEqual(
                        caught.exception.kind,
                        ModelProviderErrorKind.INVALID_RESPONSE,
                    )
                    self.assertEqual(
                        str(caught.exception),
                        "Model provider response exceeds the adapter limit",
                    )
                    self.assertIsNone(caught.exception.__cause__)
                    self.assertIsNone(caught.exception.__context__)

        response = mock.MagicMock()
        response.status = 200
        response.headers = Message()
        response.headers["Content-Length"] = "9" * 5000
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch(
            "model_provider.openai_compatible.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ModelProviderError) as caught:
                OpenAICompatibleProvider(
                    OpenAICompatibleConfig("http://127.0.0.1/model")
                ).generate(self.request())
        self.assertEqual(caught.exception.kind, ModelProviderErrorKind.INVALID_RESPONSE)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        response.read.assert_not_called()
        response.__exit__.assert_called_once()

    def test_transport_shape_and_hostile_headers_fail_closed(self) -> None:
        malformed = (
            None,
            [],
            (True, {}, b"{}"),
            (200, [], b"{}"),
            (200, {}, bytearray(b"{}")),
        )
        for transport_result in malformed:
            with self.subTest(transport_result=transport_result):
                provider = self.provider(CaptureTransport())
                provider._transport = lambda request, timeout, maximum: transport_result
                with self.assertRaises(ModelProviderError) as caught:
                    provider.generate(self.request())
                self.assertEqual(
                    caught.exception.kind,
                    ModelProviderErrorKind.PROVIDER_FAILED,
                )

        class HostileHeaders(dict[str, str]):
            def get(self, key: str, default: object = None) -> str | None:
                raise RuntimeError("secret header failure")

        error = self.assert_provider_error(
            CaptureTransport((200, HostileHeaders(), b"{}")),
            ModelProviderErrorKind.PROVIDER_FAILED,
        )
        self.assertNotIn("secret", str(error) + repr(error))

    def test_real_urllib_loopback_success_and_status_mapping(self) -> None:
        valid = b'{"choices":[{"message":{"content":"real-ok"}}]}'
        cases = (
            (200, valid, None, "real-ok"),
            (302, b"secret", ModelProviderErrorKind.PROVIDER_FAILED, None),
            (400, b"secret", ModelProviderErrorKind.REQUEST_REJECTED, None),
            (401, b"secret", ModelProviderErrorKind.REQUEST_REJECTED, None),
            (500, b"secret", ModelProviderErrorKind.PROVIDER_FAILED, None),
            (503, b"secret", ModelProviderErrorKind.PROVIDER_FAILED, None),
        )
        for status, body, kind, output in cases:
            headers = {"Content-Type": "application/json"}
            if status == 302:
                headers["Location"] = "http://127.0.0.1:1/leak"
            with self.subTest(status=status), _LoopbackServer(
                status, body, headers
            ) as server:
                provider = OpenAICompatibleProvider(OpenAICompatibleConfig(server.url))
                if kind is None:
                    self.assertEqual(provider.generate(self.request()).output_text, output)
                else:
                    with self.assertRaises(ModelProviderError) as caught:
                        provider.generate(self.request())
                    self.assertEqual(caught.exception.kind, kind)
                self.assertEqual(server.hits, 1)

    def test_real_urllib_ignores_environment_proxy_without_no_proxy_help(self) -> None:
        body = b'{"choices":[{"message":{"content":"direct"}}]}'
        with _LoopbackServer(200, body) as target, _LoopbackServer(502) as proxy:
            with mock.patch.dict(
                os.environ,
                {"HTTP_PROXY": proxy.url, "HTTPS_PROXY": proxy.url, "NO_PROXY": ""},
                clear=False,
            ):
                result = OpenAICompatibleProvider(
                    OpenAICompatibleConfig(target.url)
                ).generate(self.request())
        self.assertEqual(result.output_text, "direct")
        self.assertEqual(target.hits, 1)
        self.assertEqual(proxy.hits, 0)

    def test_http_errors_are_closed_without_reading_body(self) -> None:
        for status in (302, 400, 500):
            with self.subTest(status=status):
                file_object = mock.Mock()
                http_error = urllib.error.HTTPError(
                    "http://127.0.0.1/model",
                    status,
                    "secret",
                    Message(),
                    file_object,
                )
                opener = mock.Mock()
                opener.open.side_effect = http_error
                with mock.patch(
                    "model_provider.openai_compatible.urllib.request.build_opener",
                    return_value=opener,
                ):
                    with self.assertRaises(ModelProviderError):
                        OpenAICompatibleProvider(
                            OpenAICompatibleConfig("http://127.0.0.1/model")
                        ).generate(self.request())
                file_object.read.assert_not_called()
                file_object.close.assert_called_once_with()

    def test_default_and_injected_statuses_are_strict_without_coercion(self) -> None:
        for status in (True, "200", 200.0):
            with self.subTest(injected=status):
                provider = self.provider(CaptureTransport())
                provider._transport = lambda request, timeout, maximum, value=status: (
                    value,
                    {},
                    b'{"choices":[{"message":{"content":"bad"}}]}',
                )
                with self.assertRaises(ModelProviderError) as caught:
                    provider.generate(self.request())
                self.assertEqual(caught.exception.kind, ModelProviderErrorKind.PROVIDER_FAILED)

        response = mock.MagicMock()
        response.status = "200"
        response.headers = Message()
        response.__enter__.return_value = response
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch(
            "model_provider.openai_compatible.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ModelProviderError) as caught:
                OpenAICompatibleProvider(
                    OpenAICompatibleConfig("http://127.0.0.1/model")
                ).generate(self.request())
        self.assertEqual(caught.exception.kind, ModelProviderErrorKind.PROVIDER_FAILED)

        file_object = mock.Mock()
        malformed_http_error = urllib.error.HTTPError(
            "http://127.0.0.1/model",
            "500",
            "secret",
            Message(),
            file_object,
        )
        opener = mock.Mock()
        opener.open.side_effect = malformed_http_error
        with mock.patch(
            "model_provider.openai_compatible.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ModelProviderError) as caught:
                OpenAICompatibleProvider(
                    OpenAICompatibleConfig("http://127.0.0.1/model")
                ).generate(self.request())
        self.assertEqual(caught.exception.kind, ModelProviderErrorKind.PROVIDER_FAILED)
        file_object.close.assert_called_once_with()

    def test_installed_copy_imports_without_repository_or_developer_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copied_scripts = Path(temporary) / "installed" / "scripts"
            shutil.copytree(
                SCRIPTS / "model_provider",
                copied_scripts / "model_provider",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    (
                        "import sys; sys.path.insert(0, sys.argv[1]); "
                        "import model_provider; "
                        "assert model_provider.ModelProvider is not None"
                    ),
                    str(copied_scripts),
                ],
                cwd=temporary,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_has_no_environment_secret_discovery_or_runtime_dependency(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((SCRIPTS / "model_provider").glob("*.py"))
        )
        self.assertNotIn("agent_runtime", source)
        self.assertNotIn("OPENAI_API_KEY", source)
        self.assertNotIn("os.environ", source)
        self.assertNotIn("stream\"", source)
        self.assertNotIn("tool_calls", source)


if __name__ == "__main__":
    unittest.main()
