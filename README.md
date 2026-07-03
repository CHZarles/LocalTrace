# LocalTrace

LocalTrace 是给 Windows agent 使用的本地活动上下文工具。它记录前台应用、浏览器标签页活动和非浏览器音频，把原始事件保存在本机，并提供一个本地 Web UI 查看当天活动。

## 先让 Agent 安装 Skill

如果你是在给 agent 配 LocalTrace，先让 agent 安装 LocalTrace Skill。用户不需要手动运行安装命令。

你可以直接对 agent 说：

> 请在当前仓库安装 LocalTrace Skill。只使用仓库 skill 目录里的安装器完成安装，不要让我手动运行命令；安装后检查 skill 已经可用，并打开 LocalTrace Web UI。

安装入口只有一个：仓库 skill 目录里的安装器。agent 应该自己执行安装器，把 skill 放到本地 skill 目录，并创建它自己的调用入口。

安装完成后，agent 可以通过这个 skill 打开 Web UI、检查 LocalTrace 状态、
读取最近活动、汇总一天活动、查看过去 3 天的焦点切换事实，或解释一段
时间里的活动空白。用户不需要读取数据库，也不需要导出事件文件。

常用子能力包括 dashboard、focus-switches、health、recent-events、
day-summary 和 explain-gap。`focus-switches` 只提供切换次数、目标时长、
未知/空闲时长、切换列表和 `prompt_context`；它不自带评分，agent 可以
结合你提供的 prompt 再做评价。

## Web UI

![LocalTrace Web UI 截图](docs/assets/localtrace-web-ui.png)

Web UI 默认在本机 `127.0.0.1` 上打开。它分成两个页面：

- **Metrics**：当前活动、今日汇总、时间轴、Top 应用/网站、Health。
- **Settings**：采集设置和隐私规则。

## 它记录什么

LocalTrace 只记录用于回看活动轨迹的本地信号：

- Windows 前台应用焦点。
- 非浏览器后台音频。
- Chrome / Edge 标签页焦点和标签页音频。
- 保存在本机的原始事件。

它不做日报生成、任务规划、review 工作流或云同步。Web UI 里的视图都从本机原始事件即时计算。

## 隐私边界

LocalTrace 不记录网页正文，不截图，不记录键盘输入，不上传到云端，也不提供局域网访问服务。

如果需要进一步收紧记录范围，可以在 Web UI 的 Settings 页面调整采集选项，或添加隐私规则，对指定应用或域名进行隐藏或丢弃。

## Windows 运行时

LocalTrace Skill 负责让 agent 查询活动记录；Windows 运行时负责真正采集和保存事件。

发布包是 `LocalTrace-windows.zip`。解压后，使用包内安装器安装 Windows 运行时。浏览器扩展也包含在发布包里，解压后在 Chrome 或 Edge 的扩展管理页面加载即可。

## 开发者文档

根目录 README 只保留用户和 agent 安装入口。开发、打包、架构和测试资料仍保留在这些文档中：

- [DEVELOPING.md](DEVELOPING.md)
- [WINDOWS_DEV.md](WINDOWS_DEV.md)
- [RELEASING.md](RELEASING.md)
- [docs/](docs)
- [web/README.md](web/README.md)
- [extension/README.md](extension/README.md)
- [skill/README.md](skill/README.md)

## English

LocalTrace is a local activity context tool for a Windows agent. It records
foreground app focus, browser tab activity, and non-browser audio as raw events
on the local machine, then shows the current day in a local Web UI.

If you are setting it up for an agent, ask the agent to install the LocalTrace
Skill from this repository. The agent should use the bundled installer itself,
verify the skill, and open the Web UI without asking you to run shell commands.

The skill can open the dashboard, check health, read recent activity, summarize
a day, report focus-switch facts for the past 3 days, and explain activity
gaps. `focus-switches` returns factual data and `prompt_context`; it does not
produce a built-in rating.

LocalTrace does not capture page bodies, screenshots, keyboard input, cloud
sync, or LAN access. You can tighten capture settings and privacy rules in the
Settings page.
