1. cron job修复（**严重bug**）：
   - 定好的cron jobs，我强烈需要在cron jobs view中进行展示，需要系统自动读取～/.comobot/cron/jobs.json的数据，筛选出还没到点执行的定时任务在前端进行展示；
   - 到点的定时任务必须在对应的前端chat框里发送对应的消息给用户，在CLI中也有response
2. settings中 Agent板块编辑器板块，实现读取～/.comobot下三个对应文件内容时报错api/settings:1  Failed to load resource: the server responded with a status of 401 (Unauthorized)；
3.  chat框中的workfow执行框修改为执行完不折叠；

