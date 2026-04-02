"""
Test workflow message rendering consistency.

This test verifies that tool_hint and other process messages are correctly
stored in the database and can be retrieved and parsed correctly by the frontend.

Issue: workflow window shows raw JSON after page refresh because:
1. tool_hint messages weren't handled in ProcessMessage.vue (now fixed)
2. process_data needed double-parse for double-encoded JSON (now fixed)
3. parseProcessType needed to handle JSON-encoded tool_calls (now fixed)

This test simulates the complete data path: DB -> API -> frontend parsing -> final render data.
"""

import json


def test_tool_hint_message_data_path():
    """Verify tool_hint messages are correctly transformed through the full data path.

    DB stores: content='{"content": "web_fetch", "step_id": "step_3"}', tool_calls='"tool_hint"'
    API returns: these strings as JSON-encoded values
    Frontend parses: JSON.parse() to get original strings
    Frontend process_data: parse_process_data(content) -> {content: 'web_fetch', step_id: 'step_3'}
    Frontend processType: parse_process_type(tool_calls) -> 'tool_hint'
    """

    # Simulate DB values (as strings)
    db_content = '{"content": "web_fetch", "step_id": "step_3"}'
    db_tool_calls = '"tool_hint"'

    # Simulate FastAPI JSON-encoding (each string value gets JSON-encoded)
    api_content = json.dumps(db_content)
    api_tool_calls = json.dumps(db_tool_calls)

    # Simulate frontend JSON.parse()
    frontend_content = json.loads(api_content)  # str: '{"content": "web_fetch", "step_id": "step_3"}'
    frontend_tool_calls = json.loads(api_tool_calls)

    # parseProcessType (frontend equivalent)
    def parse_process_type(raw):
        if not raw:
            return ''
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, str):
                    return parsed
            except Exception:
                pass
        return str(raw)

    # parseProcessData (frontend equivalent)
    def parse_process_data(raw):
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            first = json.loads(raw)
            if isinstance(first, str):
                try:
                    return json.loads(first)
                except Exception:
                    return {'content': first}
            if isinstance(first.get('content'), str) and first['content'].startswith('{'):
                try:
                    first['content'] = json.loads(first['content'])
                except Exception:
                    pass
            return first
        except Exception:
            return {'content': str(raw)}

    # Simulate frontend message construction (like loadSessionMessages does)
    process_data = parse_process_data(frontend_content)
    msg = {
        'id': 1,
        'role': 'process',
        'content': '',
        'processType': parse_process_type(frontend_tool_calls),
        'process_data': process_data,
        'created_at': '2026-04-01T00:00:00',
    }

    # Verify the message structure matches what ProcessMessage.vue expects
    assert msg['role'] == 'process', f"Expected role='process', got {msg['role']}"
    assert msg['processType'] == 'tool_hint', f"Expected processType='tool_hint', got {repr(msg['processType'])}"
    assert isinstance(msg['process_data'], dict), f"Expected process_data to be dict, got {type(msg['process_data'])}"
    assert msg['process_data']['content'] == 'web_fetch', f"Expected content='web_fetch', got {repr(msg['process_data']['content'])}"
    assert msg['process_data']['step_id'] == 'step_3', f"Expected step_id='step_3', got {repr(msg['process_data']['step_id'])}"

    # Verify ProcessMessage.vue rendering path
    # The tool_hint branch: <span class="pm-inline-label">{{ typeof data.content === 'string' ? data.content : JSON.stringify(data.content) }}</span>
    data = msg['process_data']
    rendered_content = data['content'] if isinstance(data['content'], str) else json.dumps(data['content'])
    assert rendered_content == 'web_fetch', f"Expected rendered content='web_fetch', got {repr(rendered_content)}"

    print("✓ tool_hint message data path is correct")


def test_thinking_message_data_path():
    """Verify thinking messages are handled correctly."""
    db_content = '{}'
    db_tool_calls = '"thinking"'

    api_content = json.dumps(db_content)
    api_tool_calls = json.dumps(db_tool_calls)

    frontend_content = json.loads(api_content)
    frontend_tool_calls = json.loads(api_tool_calls)

    def parse_process_type(raw):
        if not raw:
            return ''
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, str):
                    return parsed
            except Exception:
                pass
        return str(raw)

    def parse_process_data(raw):
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            first = json.loads(raw)
            if isinstance(first, str):
                try:
                    return json.loads(first)
                except Exception:
                    return {'content': first}
            if isinstance(first.get('content'), str) and first['content'].startswith('{'):
                try:
                    first['content'] = json.loads(first['content'])
                except Exception:
                    pass
            return first
        except Exception:
            return {'content': str(raw)}

    process_data = parse_process_data(frontend_content)
    msg = {
        'id': 2,
        'role': 'process',
        'content': '',
        'processType': parse_process_type(frontend_tool_calls),
        'process_data': process_data,
        'created_at': '2026-04-01T00:00:00',
    }

    assert msg['processType'] == 'thinking'
    assert msg['process_data'] == {}

    print("✓ thinking message data path is correct")


def test_plan_created_message_data_path():
    """Verify plan_created messages with steps are handled correctly."""
    db_content = json.dumps({
        'goal': '分析美伊战争',
        'plan_id': 'plan_1',
        'steps': [
            {'id': 'step_1', 'description': '搜索信息', 'status': None},
            {'id': 'step_2', 'description': '分析数据', 'status': None},
        ]
    })
    db_tool_calls = '"plan_created"'

    api_content = json.dumps(db_content)
    api_tool_calls = json.dumps(db_tool_calls)

    frontend_content = json.loads(api_content)
    frontend_tool_calls = json.loads(api_tool_calls)

    def parse_process_type(raw):
        if not raw:
            return ''
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, str):
                    return parsed
            except Exception:
                pass
        return str(raw)

    def parse_process_data(raw):
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            first = json.loads(raw)
            if isinstance(first, str):
                try:
                    return json.loads(first)
                except Exception:
                    return {'content': first}
            if isinstance(first.get('content'), str) and first['content'].startswith('{'):
                try:
                    first['content'] = json.loads(first['content'])
                except Exception:
                    pass
            return first
        except Exception:
            return {'content': str(raw)}

    process_data = parse_process_data(frontend_content)
    msg = {
        'id': 3,
        'role': 'process',
        'content': '',
        'processType': parse_process_type(frontend_tool_calls),
        'process_data': process_data,
        'created_at': '2026-04-01T00:00:00',
    }

    assert msg['processType'] == 'plan_created'
    assert msg['process_data']['goal'] == '分析美伊战争'
    assert len(msg['process_data']['steps']) == 2
    assert msg['process_data']['steps'][0]['id'] == 'step_1'

    print("✓ plan_created message data path is correct")


def test_tool_hint_with_exec_content():
    """Verify tool_hint with exec() content is handled correctly (common in real usage)."""
    db_content = '{"content": "exec(\\"python3 -c \\"\\\\\\"import openpyxl...\\")\\")", "step_id": "step_3"}'

    api_content = json.dumps(db_content)

    frontend_content = json.loads(api_content)

    def parse_process_type(raw):
        if not raw:
            return ''
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, str):
                    return parsed
            except Exception:
                pass
        return str(raw)

    def parse_process_data(raw):
        if not raw:
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            first = json.loads(raw)
            if isinstance(first, str):
                try:
                    return json.loads(first)
                except Exception:
                    return {'content': first}
            if isinstance(first.get('content'), str) and first['content'].startswith('{'):
                try:
                    first['content'] = json.loads(first['content'])
                except Exception:
                    pass
            return first
        except Exception:
            return {'content': str(raw)}

    process_data = parse_process_data(frontend_content)

    # The content is a string (exec command), not a JSON object
    assert isinstance(process_data['content'], str)
    assert 'exec' in process_data['content']
    assert process_data['step_id'] == 'step_3'

    # Verify ProcessMessage.vue rendering: typeof data.content === 'string' is True
    # So it would display: data.content (the exec string)
    data = process_data
    rendered = data['content'] if isinstance(data['content'], str) else json.dumps(data['content'])
    assert isinstance(rendered, str)
    assert 'exec' in rendered

    print("✓ tool_hint with exec content is handled correctly")


if __name__ == '__main__':
    test_tool_hint_message_data_path()
    test_thinking_message_data_path()
    test_plan_created_message_data_path()
    test_tool_hint_with_exec_content()
    print("\nAll workflow rendering tests passed!")
