"""Small local smoke call to Claude through Amazon Bedrock Mantle."""

from anthropic import AnthropicBedrockMantle

from app.config import settings


def main() -> None:
    client = AnthropicBedrockMantle(aws_region=settings.parser_region)
    message = client.messages.create(
        model=settings.parser_model,
        max_tokens=128,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": "In one sentence: what is an ISO week?"}],
    )
    print(next(block.text for block in message.content if block.type == "text"))
    print(f"stop_reason={message.stop_reason} input_tokens={message.usage.input_tokens} output_tokens={message.usage.output_tokens}")


if __name__ == "__main__":
    main()
