1. 刚登陆时收到的报错信息：Uncaught (in promise) FrameIsBrowserFrameError: Frame 288 in tab 473487353 is a browser frame.
    at Frame.setUpContentScript (background.js:1:50484)
    at Frame.readyToReceiveMessages (background.js:1:51048)
    at Tab.frameIsReadyToReceiveMessages (background.js:1:52965)
    at TabMonitor.frameIsReadyToReceiveMessages (background.js:1:55545)
    at background.js:1:70621了解此错误
background.js:1 Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'href')
    at #$ (background.js:1:58973)
    at async #q (background.js:1:58118)了解此错误
10Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
Unchecked runtime.lastError: Could not establish connection. Receiving end does not exist.了解此错误
background.js:1 Uncaught (in promise) TypeError: Cannot read properties of undefined (reading 'href')
    at #$ (background.js:1:58973)
    at async #H (background.js:1:58332)了解此错误
Error in event handler: TypeError: Cannot read properties of null (reading 'postMessage')
    at #J (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:58472)
    at #x (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:57904)了解此错误
chrome-extension://p…laj/background.js:1 Uncaught (in promise) Error: Could not establish connection. Receiving end does not exist.了解此错误
Error in event handler: TypeError: Cannot read properties of null (reading 'postMessage')
    at #J (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:58472)
    at #x (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:57904)了解此错误
Error in event handler: TypeError: Cannot read properties of null (reading 'postMessage')
    at #J (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:58472)
    at #x (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:57904)了解此错误
Error in event handler: TypeError: Cannot read properties of null (reading 'postMessage')
    at #J (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:58472)
    at #z (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:58454)
    at #x (chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/background.js:1:57696)

GET chrome-extension://pejdijmoenmkgeppbflobdenhhabjlaj/extensionState.js net::ERR_FILE_NOT_FOUND
2. cron job修复（**严重bug**）：
   - 执行完的cron job，status调整为offline，cron jobs的排列顺序为online在最上面，offline自动往下调整；
   - cron job不稳定：
     - 这是在CLI中的定时任务出发回复，但是在前端chat窗口仍然没有收到消息：2026-03-12 12:23:08.018 | INFO     | comobot.agent.loop:_process_message:496 - Processing message from web:user: 40秒后提醒我吃饭
2026-03-12 12:23:11.092 | INFO     | comobot.agent.loop:_run_agent_loop:319 - Tool call: cron({"action": "add", "at": "2026-03-12T12:23:40", "message": "提醒吃饭时间到啦！🍚"})
2026-03-12 12:23:11.094 | INFO     | comobot.cron.service:add_job:404 - Cron: added job '提醒吃饭时间到啦！🍚' (524da39e)
2026-03-12 12:23:12.250 | INFO     | comobot.agent.loop:_process_message:619 - Response to web:user: 已设置40秒后提醒你吃饭！🍚
2026-03-12 12:23:40.005 | INFO     | comobot.cron.service:_execute_job:321 - Cron: executing job '提醒吃饭时间到啦！🍚' (524da39e)
2026-03-12 12:23:40.006 | INFO     | comobot.agent.loop:_process_message:496 - Processing message from web:user: [Scheduled Task] Timer finished.

Task '提醒吃饭时间到啦！🍚' has been triggered.
Schedule...
2026-03-12 12:23:44.315 | INFO     | comobot.agent.loop:_run_agent_loop:319 - Tool call: message({"channel": "web", "chat_id": "6d34785161e4", "content": "🍚 提醒吃饭时间到啦！\n\n中午好~ 该吃午饭咯！好好犒劳一下自己吧～ 🥢"})
2026-03-12 12:23:44.317 | WARNING  | comobot.channels.manager:_dispatch_outbound:163 - Unknown channel: web
2026-03-12 12:23:46.049 | INFO     | comobot.agent.loop:_process_message:619 - Response to web:user: 已经提醒你吃饭啦！🍚 中午好，记得按时吃饭哦~
     - 有些任务不会被触发：2026-03-12 12:31:31.088 | INFO     | comobot.agent.loop:_process_message:496 - Processing message from web:user: 30秒后提醒我
2026-03-12 12:31:33.680 | INFO     | comobot.agent.loop:_run_agent_loop:319 - Tool call: cron({"action": "add", "at": "2026-03-12T12:31:30", "message": "🐈 提醒：时间到啦！"})
2026-03-12 12:31:33.682 | INFO     | comobot.cron.service:add_job:404 - Cron: added job '🐈 提醒：时间到啦！' (acce6661)
2026-03-12 12:31:34.785 | INFO     | comobot.agent.loop:_process_message:619 - Response to web:user: 好嘞！30秒后提醒你 ⏰

