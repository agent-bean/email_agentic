import json
import re
import uuid

from pydantic import ValidationError

from email_agentic.integrations.http import json_request
from email_agentic.platform.errors import ProviderFailure


class LLM:
    def __init__(self, db, settings, client):
        self.db, self.settings, self.client = db, settings, client

    async def structured(self, run_id, schema, system, payload):
        if not (
            self.settings.llm_model
            and self.settings.llm_base_url
            and self.settings.llm_api_key.get_secret_value()
        ):
            raise ProviderFailure("llm", category="missing_configuration")
        result = await json_request(
            self.client,
            "llm",
            "POST",
            self.settings.llm_base_url.rstrip("/") + "/chat/completions",
            deadline_seconds=min(90, self.settings.research_timeout_seconds),
            headers={
                "Authorization": "Bearer " + self.settings.llm_api_key.get_secret_value(),
                "User-Agent": "email-agentic/0.1",
            },
            json={
                "model": self.settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": system
                        + "\nReturn one JSON object with exactly these fields and constraints:\n"
                        + json.dumps(schema.model_json_schema()),
                    },
                    {"role": "user", "content": payload},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": True,
                        "schema": schema.model_json_schema(),
                    },
                },
            },
        )
        try:
            choice = result["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ProviderFailure("llm", category="incomplete_output")
            content = choice["message"]["content"]
            # Normalize a complete Markdown wrapper, then require valid JSON and business fields.
            fenced = re.fullmatch(r"\s*```(?:json)?\s*\n(.*?)\n```\s*", content, re.S)
            if fenced:
                content = fenced.group(1)
            parsed = schema.model_validate(json.loads(content))
        except ValidationError:
            raise ProviderFailure("llm", category="schema_fields") from None
        except json.JSONDecodeError:
            raise ProviderFailure("llm", category="non_json") from None
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderFailure("llm", category="invalid_envelope") from None
        usage = result.get("usage") or {}
        await self.db.execute(
            "INSERT INTO model_usage(id,run_id,model,input_tokens,output_tokens) VALUES(%s,%s,%s,%s,%s)",
            (
                uuid.uuid4(),
                run_id,
                self.settings.llm_model,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            ),
        )
        return parsed
