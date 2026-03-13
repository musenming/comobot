# comobot 升级方案新增：Session 渠道视图 & Know-how 经验学习系统

## 1. Session 渠道视图与多端同步

### 1.1 现状与目标

**目标(已更新)**：Web UI 在chat视窗中以渠道树形结构展示 Session，外部渠道消息实时同步到 Web 端对应视窗，SessionsView更改为KnowhowView详细设计见*1.4 Web UI 侧边栏重构*



### 1.3 实时同步机制

**关键设计决策**：

| 决策点 | 方案 | 理由 |
|:---|:---|:---|
| 推送时机 | `_save_turn()` 之后，**并且要及时推送到前端web UI进行前端展示** | 确保消息已持久化，避免幽灵消息；**确保消息能够及时在前端呈现** |
| 推送粒度 | 单条消息 | 避免推送整个 session 历史，Web 端增量追加 |
| Web → 外部渠道 | 不支持（一期） | 在 Web 查看外部渠道消息为只读；双向需引入回复路由，复杂度高，二期考虑 |


### 1.4 Web UI 侧边栏重构

```
┌──────────────────┬─────────────────────────────────——————————————————————————————————┐
│ ComoBot          │     （chat view）                                                  ｜ 
│                  │                                          对话视窗                   ｜            
│    Chat          │                                 generate Knowhow button           ｜
│    Creflow       │                        |                                          ｜
│    Knowhow       │   session 1             |                       帮我查一下天气：Use｜  │
│    Skills        │    - web UI             |   asistant：今天晴...                    ｜│
│    Cron Jobs     │    - abstract           |                                          ｜
│    BrainCopy     │    - timestamp          |                                          ｜
│    ----------    │    - 群聊            |                                          ｜
│                  │    session 2           |                                          ｜
│    Dashboard     │    - telegram          |                                          ｜
│    Channels      │    - abstract          |                                          ｜
│    Providers     │    - timestamp         ｜                                           ｜
│    logs          │    - 单对话             ｜                                          ｜
│    Settings      │                                                                    ｜
│                  │                                                                    ｜
│                  │                                   ┌──────────────────————————————┬ ｜                    
│                  │                                   └─——————————————————————————————┘｜                    
│                  │                                                          
└──────────────────┴──────────────────────────────————————————————————————————————————───┘

┌──────────────────┬─────────────────────────────────————————————————————————————————————————┐
│ ComoBot          │     （Knowhow view）                                                   ｜ 
│                  │                                          对话视窗                       ｜            
│    Chat          │    search 栏                                                           ｜
│    Creflow       │    --------------------                                                ｜
│    Knowhow       │   Knowhow 1                |                       帮我查一下天气：User  │
│    Skills        │    - function abstract     |   asistant：今天晴...                      │
│    Cron Jobs     │    - update time           |                                          ｜
│    BrainCopy     │   ——————————————————————   |                                          ｜
│    ----------    │   Knowhow 1                |                                          ｜
│                  │    - function abstract     |                                          ｜
│    Dashboard     │    - update time           |                                          ｜
│    Channels      │    ——————————————————      |                                          ｜
│    Providers     │                                                                       ｜
│    logs          │                                                                       ｜
│    Settings      │                                                                       ｜
│                  │                                                                       ｜
│                  │                                   ┌──────────────────————————————┬ ｜                    
│                  │                                   └─——————————————————————————————┘｜                    
│                  │                                                          
└──────────────────┴──────────────────────────────————————————————————————————————————───┘

```
