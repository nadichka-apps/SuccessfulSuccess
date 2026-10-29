"""Small local smoke call to Amazon Nova through Bedrock Converse."""

import boto3

from app.config import settings


def main() -> None:
    client = boto3.client("bedrock-runtime", region_name=settings.parser_region)
    message = client.converse(
        modelId=settings.parser_model,
        inferenceConfig={"maxTokens": 128, "temperature": 0},
        messages=[{"role": "user", "content": [{"text": "In one sentence: what is an ISO week?"}]}],
    )
    print(next(block["text"] for block in message["output"]["message"]["content"] if "text" in block))
    print(f"stop_reason={message['stopReason']} input_tokens={message['usage']['inputTokens']} output_tokens={message['usage']['outputTokens']}")


if __name__ == "__main__":
    main()
