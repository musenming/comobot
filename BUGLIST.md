1. chat窗口，发送消息，返回：Error: Agent error: AgentLoop.run() got an unexpected keyword argument 'session_key'；控制台报错：index-COBAgXK_.js:15 [naive/getFirstSlotVNode]: slot[trigger] should have exactly one child
Qg	@	index-COBAgXK_.js:15

index-COBAgXK_.js:2 Error: [vueuc/follower]: slot[default] should have exactly one child.
    at ot (Popover-CImGxKox.js:1:2833)
    at Proxy.render (Popover-CImGxKox.js:1:4981)
    at Ol (index-COBAgXK_.js:2:43051)
    at oa.R [as fn] (index-COBAgXK_.js:2:52696)
    at oa.run (index-COBAgXK_.js:2:5950)
    at oe (index-COBAgXK_.js:2:53081)
    at V (index-COBAgXK_.js:2:51766)
    at ee (index-COBAgXK_.js:2:51537)
    at m (index-COBAgXK_.js:2:48237)
    at M (index-COBAgXK_.js:2:49838)
lf	@	index-COBAgXK_.js:2


2. 创建新的workflow报错：RROR:    Exception in ASGI application
Traceback (most recent call last):
  File "/home/comobot/.venv/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 416, in run_asgi
    result = await app(  # type: ignore[func-returns-value]
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/comobot/.venv/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
    return await self.app(scope, receive, send)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/comobot/.venv/lib/python3.11/site-packages/fastapi/applications.py", line 1160, in __call__
    await super().__call__(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/applications.py", line 107, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/middleware/errors.py", line 186, in __call__
    raise exc
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/middleware/errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/middleware/cors.py", line 95, in __call__
    await self.simple_response(scope, receive, send, request_headers=headers)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/middleware/cors.py", line 153, in simple_response
    await self.app(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/comobot/.venv/lib/python3.11/site-packages/fastapi/middleware/asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/routing.py", line 716, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/routing.py", line 736, in app
    await route.handle(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/routing.py", line 290, in handle
    await self.app(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/fastapi/routing.py", line 130, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/home/comobot/.venv/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/home/comobot/.venv/lib/python3.11/site-packages/fastapi/routing.py", line 116, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/home/comobot/.venv/lib/python3.11/site-packages/fastapi/routing.py", line 670, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/comobot/.venv/lib/python3.11/site-packages/fastapi/routing.py", line 324, in run_endpoint_function
    return await dependant.call(**values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/comobot/comobot/api/routes/workflows.py", line 138, in create_workflow
    cursor = await db.execute(
             ^^^^^^^^^^^^^^^^^
  File "/home/comobot/comobot/db/connection.py", line 50, in execute
    cursor = await self.conn.execute(sql, params)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/comobot/.venv/lib/python3.11/site-packages/aiosqlite/core.py", line 223, in execute
    cursor = await self._execute(self._conn.execute, sql, parameters)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/comobot/.venv/lib/python3.11/site-packages/aiosqlite/core.py", line 160, in _execute
    return await future
           ^^^^^^^^^^^^
  File "/home/comobot/.venv/lib/python3.11/site-packages/aiosqlite/core.py", line 63, in _connection_worker_thread
    result = function()
             ^^^^^^^^^^
sqlite3.IntegrityError: UNIQUE constraint failed: workflows.name

3. 通过UI窗口配置channel时报错：GET chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/extensionState.js net::ERR_FILE_NOT_FOUND
我需要你自动扫描config.json中的channel，并在前端进行展示

4. Providers窗口信息错误：需要实现的功能是，自动扫描config.json中的model，把已经配置完成的model展现在前端；

5.前端中漏掉一个板块，Memory & Cognition (知识与认知沉淀)，具体功能如下：
* **ComoBrain (动态认知中枢)**：点击入口后，页面平滑展开基于 WebGL 渲染的动态球状矢量图。球体的旋转与光晕映射系统当前的思考或检索状态。该模块具象化了智能体长期沉淀的专属认知模型，是用户管理个人数字认知特征与创作风格的核心视觉锚点。
* **对话回溯 (Sessions)**：左侧展示历史对话脉络，右侧展示详情，通过轻量级 Badge 突出系统提取的关键记忆节点。
* **个性化知识库 (Knowledge Base)**：管理 Agent 沉淀的用户画像与项目维度事实。界面参考 Notion 极简文档树，支持手动微调，作为底层 RAG 高质量数据源，大幅减少多轮对话冗余 Token 消耗。

5. chat窗口，type栏下有一段空白，需要去掉
