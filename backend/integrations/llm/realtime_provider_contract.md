# Realtime Provider Contract

`RealtimeLLMProvider` is the stable interface used by `AudioSessionHandler`.
Guided-task code must depend on this interface through the WebSocket audio path,
not on a concrete vendor SDK.

A provider implementation must expose:

- `configured`: truthy when the provider can accept sessions.
- `build_config(system_instruction, conversation_history, tools) -> dict`.
- `connect(config) -> RealtimeSession`.
- `send_audio(session, bytes)`.
- `send_text(session, text)`.
- `receive(session) -> AsyncIterator`.
- `send_tool_response(session, responses)`.
- `disconnect(session)`.

`receive()` must yield objects whose attributes let `AudioSessionHandler` handle:
tool calls, model-turn audio in server content, input and output transcription,
and turn completion. A future provider may either emit the same attribute shape
as Gemini Live or add a thin adapter at the provider boundary.

Tool declarations come from `GeminiToolAdapter.get_declarations()`. A future
provider may accept that FunctionDeclaration dictionary shape directly or adapt
it inside its provider implementation. Keep this as the single conversion point.

Tool responses passed to `send_tool_response()` are generic dictionaries:
`{"name": str, "response": dict, "id": str | None}`. Concrete providers convert
those dictionaries into SDK-native response objects internally.
