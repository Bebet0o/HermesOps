"""Minimal OpenAI-compatible chat completions adapter."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Mapping

from .contract import (
    ModelProviderError,
    ModelProviderErrorKind,
    ModelRequest,
    ModelResult,
)


_DEFAULT_MAX_REQUEST_BYTES = 8 * 1024 * 1024
_DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_EMPTY_REQUEST_SIZE = len(b'{"model":"","messages":[]}')
_EMPTY_MESSAGE_SIZE = len(b'{"role":"","content":""}')


class _ResponseTooLarge(Exception):
    pass


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass(frozen=True)
class _TransportResponse:
    status: int
    body: bytes
    content_length: str | None = None


_TransportResult = _TransportResponse | tuple[int, Mapping[str, str], bytes]
_Transport = Callable[[urllib.request.Request, int | float, int], _TransportResult]


@dataclass(frozen=True)
class OpenAICompatibleConfig:
    endpoint_url: str = field(repr=False)
    api_key: str | None = field(default=None, repr=False)
    max_request_bytes: int = _DEFAULT_MAX_REQUEST_BYTES
    max_response_bytes: int = _DEFAULT_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        if type(self.endpoint_url) is not str:
            raise TypeError("Model provider endpoint must be a string")
        if (
            not self.endpoint_url
            or len(self.endpoint_url) > 2048
            or not self.endpoint_url.isascii()
            or any(ord(character) < 32 or ord(character) == 127 for character in self.endpoint_url)
        ):
            raise ValueError("Model provider endpoint is invalid")
        try:
            parsed = urllib.parse.urlsplit(self.endpoint_url)
            port = parsed.port
        except ValueError:
            raise ValueError("Model provider endpoint is invalid") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or parsed.query
            or not parsed.path
            or port is None and parsed.netloc.endswith(":")
        ):
            raise ValueError("Model provider endpoint must be an exact HTTP(S) URL")
        if self.api_key is not None:
            if type(self.api_key) is not str:
                raise TypeError("Model provider API key must be a string or None")
            if (
                not self.api_key
                or len(self.api_key) > 4096
                or any(ord(character) < 33 or ord(character) > 126 for character in self.api_key)
            ):
                raise ValueError("Model provider API key is invalid")
            if parsed.scheme != "https":
                raise ValueError("Model provider API keys require HTTPS")
        for value, description in (
            (self.max_request_bytes, "request"),
            (self.max_response_bytes, "response"),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"Model provider {description} limit must be a positive integer")
        if self.max_response_bytes > _DEFAULT_MAX_RESPONSE_BYTES:
            raise ValueError("Model provider response limit exceeds the adapter ceiling")


def _bounded_content_length_value(raw_length: str | None, maximum: int) -> None:
    if raw_length is None:
        return
    if (
        type(raw_length) is not str
        or not raw_length
        or any(character < "0" or character > "9" for character in raw_length)
    ):
        raise _ResponseTooLarge
    significant = raw_length.lstrip("0") or "0"
    maximum_text = str(maximum)
    if len(significant) > len(maximum_text) or (
        len(significant) == len(maximum_text) and significant > maximum_text
    ):
        raise _ResponseTooLarge


def _mapping_content_length(headers: Mapping[str, str]) -> str | None:
    try:
        raw_length = headers.get("Content-Length")
        if raw_length is None:
            raw_length = headers.get("content-length")
    except Exception:
        raise _ResponseTooLarge
    return raw_length


def _urllib_content_length(headers: object) -> str | None:
    get_all = getattr(headers, "get_all", None)
    if not callable(get_all):
        raise _ResponseTooLarge
    values = get_all("Content-Length", [])
    if type(values) is not list or len(values) > 1:
        raise _ResponseTooLarge
    if not values:
        return None
    value = values[0]
    if type(value) is not str:
        raise _ResponseTooLarge
    return value


def _minimum_request_size(request: ModelRequest, maximum: int) -> int:
    size = _EMPTY_REQUEST_SIZE + len(request.model)
    for index, message in enumerate(request.messages):
        size += (
            _EMPTY_MESSAGE_SIZE
            + len(message.role.value)
            + len(message.content)
            + (1 if index else 0)
        )
        if size > maximum:
            return size
    return size


def _stdlib_transport(
    request: urllib.request.Request,
    timeout_seconds: int | float,
    max_response_bytes: int,
) -> _TransportResponse:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _NoRedirectHandler(),
    )
    try:
        response = opener.open(request, timeout=timeout_seconds)
    except urllib.error.HTTPError as error:
        try:
            status = error.code
            if type(status) is not int:
                raise TypeError("Invalid HTTP status")
            return _TransportResponse(status=status, body=b"")
        finally:
            error.close()
    with response:
        status = response.status
        if type(status) is not int:
            raise TypeError("Invalid HTTP status")
        content_length = _urllib_content_length(response.headers)
        _bounded_content_length_value(content_length, max_response_bytes)
        body = response.read(max_response_bytes + 1)
        if type(body) is not bytes:
            raise TypeError("Invalid HTTP response body")
    if len(body) > max_response_bytes:
        raise _ResponseTooLarge
    return _TransportResponse(
        status=status,
        body=body,
        content_length=content_length,
    )


def _normalize_transport_result(result: object) -> _TransportResponse | None:
    if type(result) is _TransportResponse:
        response = result
    elif (
        type(result) is tuple
        and len(result) == 3
        and type(result[0]) is int
        and isinstance(result[1], Mapping)
        and type(result[2]) is bytes
    ):
        try:
            content_length = _mapping_content_length(result[1])
        except _ResponseTooLarge:
            return None
        response = _TransportResponse(result[0], result[2], content_length)
    else:
        return None
    if (
        type(response.status) is not int
        or type(response.body) is not bytes
        or (
            response.content_length is not None
            and type(response.content_length) is not str
        )
    ):
        return None
    return response


class OpenAICompatibleProvider:
    def __init__(
        self,
        config: OpenAICompatibleConfig,
        *,
        transport: _Transport | None = None,
    ) -> None:
        if type(config) is not OpenAICompatibleConfig:
            raise TypeError("OpenAI-compatible provider requires its typed configuration")
        if transport is not None and not callable(transport):
            raise TypeError("Model provider transport must be callable")
        self._config = config
        self._transport = transport or _stdlib_transport

    def __repr__(self) -> str:
        return "OpenAICompatibleProvider()"

    def generate(self, request: ModelRequest) -> ModelResult:
        if type(request) is not ModelRequest:
            raise TypeError("OpenAI-compatible provider requires a ModelRequest")
        if _minimum_request_size(request, self._config.max_request_bytes) > (
            self._config.max_request_bytes
        ):
            raise ModelProviderError(
                ModelProviderErrorKind.REQUEST_REJECTED,
                "Model request exceeds the provider adapter limit",
            )
        document = {
            "model": request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
        }
        payload = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(payload) > self._config.max_request_bytes:
            raise ModelProviderError(
                ModelProviderErrorKind.REQUEST_REJECTED,
                "Model request exceeds the provider adapter limit",
            )
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
        }
        if self._config.api_key is not None:
            headers["Authorization"] = f"Bearer {self._config.api_key}"
        http_request = urllib.request.Request(
            self._config.endpoint_url,
            data=payload,
            headers=headers,
            method="POST",
        )
        normalized_error: ModelProviderError | None = None
        transport_result: object = None
        try:
            transport_result = self._transport(
                http_request,
                request.timeout_seconds,
                self._config.max_response_bytes,
            )
        except (socket.timeout, TimeoutError):
            normalized_error = ModelProviderError(
                ModelProviderErrorKind.TIMEOUT,
                "Model provider request timed out",
            )
        except urllib.error.URLError as error:
            if isinstance(error.reason, (socket.timeout, TimeoutError)):
                normalized_error = ModelProviderError(
                    ModelProviderErrorKind.TIMEOUT,
                    "Model provider request timed out",
                )
            else:
                normalized_error = ModelProviderError(
                    ModelProviderErrorKind.UNAVAILABLE,
                    "Model provider is unavailable",
                )
        except _ResponseTooLarge:
            normalized_error = ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider response exceeds the adapter limit",
            )
        except OSError:
            normalized_error = ModelProviderError(
                ModelProviderErrorKind.UNAVAILABLE,
                "Model provider is unavailable",
            )
        except Exception:
            normalized_error = ModelProviderError(
                ModelProviderErrorKind.PROVIDER_FAILED,
                "Model provider transport failed",
            )
        if normalized_error is not None:
            raise normalized_error

        response = _normalize_transport_result(transport_result)
        if response is None:
            raise ModelProviderError(
                ModelProviderErrorKind.PROVIDER_FAILED,
                "Model provider transport returned an invalid response",
            )
        status = response.status
        body = response.body
        if 300 <= status < 400:
            raise ModelProviderError(
                ModelProviderErrorKind.PROVIDER_FAILED,
                "Model provider redirect was refused",
            )
        if 400 <= status < 500:
            raise ModelProviderError(
                ModelProviderErrorKind.REQUEST_REJECTED,
                "Model provider rejected the request",
            )
        if 500 <= status < 600:
            raise ModelProviderError(
                ModelProviderErrorKind.PROVIDER_FAILED,
                "Model provider failed to complete the request",
            )
        if status != 200:
            raise ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider returned an unsupported status",
            )
        normalized_error = None
        try:
            _bounded_content_length_value(
                response.content_length,
                self._config.max_response_bytes,
            )
        except _ResponseTooLarge:
            normalized_error = ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider response exceeds the adapter limit",
            )
        if normalized_error is not None:
            raise normalized_error
        if len(body) > self._config.max_response_bytes:
            raise ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider response exceeds the adapter limit",
            )
        normalized_error = None
        try:
            decoded = body.decode("utf-8")
            response_document = json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            normalized_error = ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider returned invalid JSON",
            )
        if normalized_error is not None:
            raise normalized_error
        if type(response_document) is not dict:
            raise ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider response structure is invalid",
            )
        choices = response_document.get("choices")
        if type(choices) is not list or not choices or type(choices[0]) is not dict:
            raise ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider response structure is invalid",
            )
        message = choices[0].get("message")
        if type(message) is not dict or type(message.get("content")) is not str:
            raise ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider response structure is invalid",
            )
        output_text = message["content"]
        normalized_error = None
        try:
            output_text.encode("utf-8")
        except UnicodeEncodeError:
            normalized_error = ModelProviderError(
                ModelProviderErrorKind.INVALID_RESPONSE,
                "Model provider response structure is invalid",
            )
        if normalized_error is not None:
            raise normalized_error
        return ModelResult(output_text=output_text)
