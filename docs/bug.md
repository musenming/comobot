1. get_model_cost_map.py:213 - LiteLLM: Failed to fetch remote model cost map from https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json: The read operation timed out. Falling back to local backup.  发生该报错有可能是用户没有使用代理的原因，能否有替代方案，用户无论是否使用代理都能使用和访问；
2. /home/comobot/.venv/lib/python3.11/site-packages/requests/__init__.py:113: RequestsDependencyWarning: urllib3 (2.6.3) or chardet (7.0.1)/charset_normalizer (3.4.5) doesn't match a supported version! 解决该问题。
3. 在中文输入法输入文字时按ENTER键；绑定keyup事件会将输入法中的英文文字输入到文字框并直接触发发送按钮，导致没有打完完整的prompt就发送，修复该问题
4. 前端增加展示 “使用exec 工具的过程”，可以直接嵌入一个exec 工具的窗口，并且完成后状态打钩，并且该过程在前端保留，总之 我需要一个炫酷的workflow界面，让生成结果以后，这个过程可以被折叠；
5. chat对话板块，用户如果暂时离开chat再返回，之前的对话就会消失，我需要你帮我优化为，如果用户没有新建session，该session就会一直保留在chat对话框里，用户无论什么时候回来都可以继续对话，帮我在chat对话框新增一个“+new session”按钮，只有当点击该按钮时，用户才会新建session，通过历史对话将被保存为一条session。
6. 所以，在sessions板块中存在bug，目前对话的存储方式是一个prompt一个问题，我需要你按照5中所提到的方式进行存储和展示，用户进入某个session后还可以继续对话并保存；
7. 我在chat对话中设置了一个定时任务，后台也显示“Cron: added job '该睡觉了！晚安~ 🛏️' (f228935b)”，但是前端cron jos板块中没有对该任务的展示，我需要你在前端展示出未执行的每一个cron job，包括任务开始时间、倒计时，任务摘要；
8. 把settings中default板块对model和provider的修改，位置改到provider板块中，各provider卡片的上方；
9. settings中 Agent板块添加对Agent.md的修改，三个编辑窗口优化为一个好看的markdown编辑器，然后应该先展示三个makdown中已有的内容，然后可以编辑、保存和preview；
10. 上一次对产品的memory有很大修改，包括memory的存储结构和文件结构，但是有很多用户已经提前安装comobot，如果安装新版本，老版本的存储结构是否为并行，如果是并行的方式，我需要你设立一个检查与升级机制，在用户安装新版本的时候，先对memory等文件系统进行检查，如果还是老的结构，应该新建memory存储系统，然后迁移数据，并对老的结构进行清理删除，保证新的memory结构干净、清爽并且不会受到影响。