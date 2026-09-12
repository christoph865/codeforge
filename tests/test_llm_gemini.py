from types import SimpleNamespace

from codeforge.llm.gemini import GeminiClient, _clean_schema


def _make_client() -> GeminiClient:
    client = GeminiClient.__new__(GeminiClient)  # bypass __init__, no real genai.Client needed
    client._model = "gemini-test"
    return client


def test_clean_schema_strips_unsupported_keys_recursively():
    schema = {
        "title": "TechnicalSpec",
        "type": "object",
        "additionalProperties": False,
        "$schema": "http://json-schema.org/draft-07/schema#",
        "properties": {
            "summary": {"title": "Summary", "type": "string"},
            "test_cases": {
                "title": "Test cases",
                "type": "array",
                "items": {"title": "Item", "type": "string"},
            },
        },
        "required": ["summary"],
    }

    cleaned = _clean_schema(schema)

    assert "title" not in cleaned
    assert "additionalProperties" not in cleaned
    assert "$schema" not in cleaned
    assert "title" not in cleaned["properties"]["summary"]
    assert "title" not in cleaned["properties"]["test_cases"]
    assert "title" not in cleaned["properties"]["test_cases"]["items"]
    assert cleaned["required"] == ["summary"]


def test_create_message_parses_text_and_function_call():
    client = _make_client()

    function_call = SimpleNamespace(id="call-1", name="submit_technical_spec", args={"summary": "x"})
    part_text = SimpleNamespace(text="thinking...", function_call=None)
    part_call = SimpleNamespace(text=None, function_call=function_call)
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[part_text, part_call]),
        finish_reason=SimpleNamespace(value="STOP"),
    )
    fake_response = SimpleNamespace(candidates=[candidate])

    captured = {}

    def fake_generate_content(**kwargs):
        captured.update(kwargs)
        return fake_response

    client._client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate_content))

    result = client.create_message(
        system="sys prompt",
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "name": "submit_technical_spec",
                "description": "d",
                "input_schema": {"type": "object", "properties": {}},
            }
        ],
    )

    assert result.text == "thinking..."
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "submit_technical_spec"
    assert result.tool_calls[0].input == {"summary": "x"}
    assert result.stop_reason == "STOP"
    assert captured["model"] == "gemini-test"


def test_create_message_with_no_tool_calls():
    client = _make_client()
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[SimpleNamespace(text="just text", function_call=None)]),
        finish_reason=None,
    )
    client._client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(candidates=[candidate])
        )
    )

    result = client.create_message(system="sys", messages=[{"role": "user", "content": "hi"}])

    assert result.text == "just text"
    assert result.tool_calls == []
    assert result.stop_reason is None
