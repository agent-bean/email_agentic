"""Check a gateway using LLM_BASE_URL, LLM_API_KEY and LLM_MODEL from the environment."""
import json
import os
import sys
import urllib.error
import urllib.request

USER_AGENT = 'email-agentic/0.1'


def main():
    required = ['LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL']
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        print('Missing environment variables: ' + ', '.join(missing))
        return 2
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
              'required': ['ok'], 'additionalProperties': False}
    headers = {'Authorization': 'Bearer ' + os.environ['LLM_API_KEY'],
               'Content-Type': 'application/json', 'User-Agent': USER_AGENT}
    results = []
    for kind in ['structured', 'structured', 'structured', 'tool']:
        body = {'model': os.environ['LLM_MODEL'], 'messages': [
            {'role': 'system', 'content': 'Follow the JSON schema exactly. Return only JSON without Markdown. Use the requested function when tools are provided.'},
            {'role': 'user', 'content': 'Return ok=true.' if kind == 'structured' else 'Call connection_check with ok=true.'}]}
        if kind == 'structured':
            body['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'connection_check', 'strict': True, 'schema': schema}}
        else:
            body['tools'] = [{'type': 'function', 'function': {'name': 'connection_check',
                'description': 'Harmless connection check.', 'parameters': schema, 'strict': True}}]
            body['tool_choice'] = {'type': 'function', 'function': {'name': 'connection_check'}}
        try:
            request = urllib.request.Request(os.environ['LLM_BASE_URL'].rstrip('/') + '/chat/completions',
                                             data=json.dumps(body).encode(), headers=headers)
            with urllib.request.urlopen(request, timeout=45) as response:
                data = json.load(response)
            message = data['choices'][0]['message']
            if kind == 'structured':
                value = json.loads(message['content'])
                passed = type(value) is dict and set(value) == {'ok'} and value['ok'] is True
            else:
                calls = message.get('tool_calls', [])
                passed = len(calls) == 1 and calls[0]['function']['name'] == 'connection_check'
                value = json.loads(calls[0]['function']['arguments']) if passed else None
                passed = passed and type(value) is dict and set(value) == {'ok'} and value['ok'] is True
            results.append({'kind': kind, 'passed': passed,
                'usage_present': isinstance(data.get('usage', {}).get('total_tokens'), int)})
        except urllib.error.HTTPError as error:
            results.append({'kind': kind, 'passed': False, 'http_status': error.code})
        except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
            results.append({'kind': kind, 'passed': False, 'error_type': type(error).__name__})
    print(json.dumps(results, indent=2))
    return 0 if all(r['passed'] and r.get('usage_present') for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
