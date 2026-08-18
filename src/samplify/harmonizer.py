"""The model call.

This is the only module that talks to a model. Every other backend in samplify
runs offline, and the ``apply`` step never reaches this code at all.

The model is asked for one thing: a canonical name for every input name. Names
that receive the same canonical name form one group. The grouping, the review
and the application of the result all happen without the model.

Two providers answer that request. ``openrouter`` is the default and it needs an
API key. ``ollama`` runs a model on the local machine and needs no key.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from dotenv import load_dotenv
from openai import OpenAI

from . import rules

load_dotenv()

#: The services that samplify can ask.
PROVIDERS = ("openrouter", "ollama")

#: Used when the caller does not choose a provider.
DEFAULT_PROVIDER = "openrouter"

#: Used when neither the caller nor the environment names a model.
DEFAULT_MODEL = "openai/gpt-4o-mini"

#: OpenRouter speaks the OpenAI chat completions protocol.
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

#: The root of a local ollama server. The native API lives under ``/api``.
OLLAMA_BASE_URL = "http://localhost:11434"

#: Used when neither the caller nor the environment names a local model.
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"

#: A local model on a CPU answers in seconds, not in milliseconds.
DEFAULT_OLLAMA_TIMEOUT = 300.0


def build_system_prompt() -> str:
    """Build the system prompt from the shared rules.

    The normalisation rules are generated from :data:`samplify.rules.ABBREVIATIONS`
    rather than written out here, so the prompt and the offline backends cannot
    drift apart.

    Returns:
        The complete system prompt.
    """
    return f"""You are a bioinformatics sample name harmonizer.

You will be given a list of sample identifiers that refer to the same samples
but use inconsistent naming conventions across batches, files or collaborators.
Some of them contain typing errors. Your task is to:

1. Identify the components in each name, such as the sample or patient number,
   the batch, the replicate, the timepoint and the condition
2. Infer a single canonical naming format from the patterns you observe
3. Return a JSON mapping from every original name to its canonical form

Give two names the same canonical form only when you are confident they are the
same sample. Numbers carry the identity of a sample: p111 and p112 are two
different patients, however alike they look, and they must never receive the
same canonical name.

Normalisation rules to apply:
{rules.prompt_rules()}

Return ONLY valid JSON, with no markdown and no explanation, in exactly this
schema:
{{
  "canonical_pattern": "<short human-readable description of the inferred format>",
  "mapping": {{
    "<original_name>": "<canonical_name>"
  }}
}}"""


def _build_user_message(names: list[str]) -> str:
    """Format the input names as the user turn of the request.

    Args:
        names: The raw sample names.

    Returns:
        The user message.
    """
    name_list = "\n".join(f"  - {n}" for n in names)
    return f"Harmonize these sample names:\n{name_list}"


def resolve_model(model: str | None = None, *, provider: str = DEFAULT_PROVIDER) -> str:
    """Decide which model string to use.

    Args:
        model: An explicit model string, or None.
        provider: ``"openrouter"`` or ``"ollama"``.

    Returns:
        The explicit model, else the model named in the environment, else the
        default of the provider.
    """
    if provider == "ollama":
        return model or os.environ.get("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    return model or os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


def resolve_base_url(provider: str = DEFAULT_PROVIDER, base_url: str | None = None) -> str:
    """Decide which server to call.

    ``OLLAMA_HOST`` follows the convention of ollama itself, so it may arrive as
    ``localhost:11434`` with no scheme.

    Args:
        provider: ``"openrouter"`` or ``"ollama"``.
        base_url: An explicit URL, or None.

    Returns:
        The base URL of the provider.
    """
    if base_url:
        return base_url.rstrip("/")
    if provider != "ollama":
        return DEFAULT_BASE_URL

    host = os.environ.get("OLLAMA_HOST", "").strip()
    if not host:
        return OLLAMA_BASE_URL
    if not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host.rstrip("/")


def _post_json(url: str, payload: dict, timeout: float) -> dict:
    """Send one JSON request to a local server and read the JSON answer.

    Args:
        url: The full URL.
        payload: The request body.
        timeout: Seconds to wait.

    Returns:
        The decoded answer.

    Raises:
        ValueError: If the server does not answer, or answers with something
            that is not JSON.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as handle:
            return json.load(handle)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise ValueError(
            f"No usable answer from ollama at {url}: {exc}. Start the server with "
            f"'ollama serve', or choose an offline method such as --method damerau."
        ) from exc


def _ollama_thinks(base_url: str, model: str, timeout: float) -> bool:
    """Report whether a local model has the thinking capability.

    A thinking model writes a long reasoning block before the answer, and that
    block costs minutes on a CPU. samplify turns it off, but only for a model
    that has it, because the field is not valid for the other models.

    Args:
        base_url: The root of the ollama server.
        model: The model name.
        timeout: Seconds to wait.

    Returns:
        True when the model lists ``thinking`` among its capabilities.
    """
    try:
        body = _post_json(f"{base_url}/api/show", {"model": model}, timeout)
    except ValueError:
        return False
    return "thinking" in (body.get("capabilities") or [])


def _ask_ollama(names: list[str], *, model: str, base_url: str, timeout: float) -> str | None:
    """Ask a local ollama model for the canonical names.

    The native endpoint is used rather than the OpenAI-compatible one, because
    only the native endpoint takes ``think`` and ``format``.

    Args:
        names: The raw sample names.
        model: The local model name.
        base_url: The root of the ollama server.
        timeout: Seconds to wait for the answer.

    Returns:
        The message content, which should be the requested JSON document.

    Raises:
        ValueError: If the server does not answer, or answers without a message.
    """
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": _build_user_message(names)},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }
    if _ollama_thinks(base_url, model, timeout):
        payload["think"] = False

    body = _post_json(f"{base_url}/api/chat", payload, timeout)
    message = body.get("message")
    if not isinstance(message, dict):
        raise ValueError(f"ollama answered without a message. Got the keys: {list(body)[:5]}")
    return message.get("content")


def _ask_openrouter(
    names: list[str],
    *,
    api_key: str | None,
    model: str,
    base_url: str,
    timeout: float | None,
) -> str | None:
    """Ask OpenRouter for the canonical names.

    Args:
        names: The raw sample names.
        api_key: The OpenRouter key, or None to read the environment.
        model: The model string.
        base_url: The API base URL.
        timeout: Seconds to wait, or None for the default of the client.

    Returns:
        The message content, which should be the requested JSON document.

    Raises:
        ValueError: If no API key is available.
    """
    resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not resolved_key:
        raise ValueError(
            "No API key found. Set OPENROUTER_API_KEY in your environment or .env "
            "file, choose --provider ollama, or choose an offline method such as "
            "--method levenshtein."
        )

    client = OpenAI(api_key=resolved_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": _build_user_message(names)},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        **({"timeout": timeout} if timeout is not None else {}),
    )
    return response.choices[0].message.content


def _parse_answer(raw: str | None, names: list[str]) -> dict:
    """Read the JSON document that a model returned.

    Args:
        raw: The message content.
        names: The names that were sent, so a dropped name can be restored.

    Returns:
        The result dictionary, with every input name present in ``mapping``.

    Raises:
        ValueError: If the answer is not the requested JSON document.
    """
    try:
        result = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        preview = (raw or "")[:200]
        raise ValueError(
            f"The model did not return valid JSON. First 200 characters: {preview!r}"
        ) from exc

    if not isinstance(result, dict) or "mapping" not in result:
        raise ValueError(
            f"The model returned JSON without a 'mapping' key. Got: {list(result)[:5]}"
            if isinstance(result, dict)
            else "The model returned JSON that is not an object."
        )

    # A name the model dropped keeps its original form. Losing a name here
    # would drop rows at the apply step.
    for name in names:
        if name not in result["mapping"]:
            result["mapping"][name] = name

    result.setdefault("canonical_pattern", "")
    return result


def harmonize(
    names: list[str],
    *,
    api_key: str | None = None,
    model: str | None = None,
    provider: str = DEFAULT_PROVIDER,
    base_url: str | None = None,
    timeout: float | None = None,
) -> dict:
    """Harmonize a list of inconsistent sample names with one model call.

    Args:
        names: Raw sample identifiers to normalise.
        api_key: OpenRouter API key. Falls back to the ``OPENROUTER_API_KEY``
            environment variable, which ``python-dotenv`` also loads from a
            local ``.env`` file. A local model needs no key.
        model: The model string. Falls back to ``OPENROUTER_MODEL`` or to
            ``OLLAMA_MODEL``, then to the default of the provider.
        provider: ``"openrouter"`` for the hosted service, or ``"ollama"`` for a
            model on the local machine.
        base_url: The server to call. Falls back to ``OLLAMA_HOST`` for ollama,
            then to the default of the provider.
        timeout: Seconds to wait for the answer. A local model defaults to
            :data:`DEFAULT_OLLAMA_TIMEOUT`.

    Returns:
        A dictionary with two keys. ``canonical_pattern`` holds the model's
        description of the format it inferred. ``mapping`` holds every original
        name against its canonical form, including any name the model omitted,
        which is returned unchanged.

    Raises:
        ValueError: If the provider is unknown, if no API key is available, if
            the local server does not answer, or if the model returns something
            that is not the requested JSON document.
    """
    if not names:
        return {"canonical_pattern": "", "mapping": {}}

    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider!r}. Use one of {PROVIDERS}.")

    resolved_url = resolve_base_url(provider, base_url)
    resolved_model = resolve_model(model, provider=provider)

    if provider == "ollama":
        raw = _ask_ollama(
            names,
            model=resolved_model,
            base_url=resolved_url,
            timeout=timeout if timeout is not None else DEFAULT_OLLAMA_TIMEOUT,
        )
    else:
        raw = _ask_openrouter(
            names,
            api_key=api_key,
            model=resolved_model,
            base_url=resolved_url,
            timeout=timeout,
        )

    return _parse_answer(raw, names)
