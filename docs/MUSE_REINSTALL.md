# Muse: reinstall and prepare acceptance of Focu main

请直接执行以下任务：把我现有的 Focu 更新到 https://github.com/ialchemist-dev/focu 的最新 main，准备好由我亲自测试。按功能依赖推进，不要按第一天、第二天排期，也不要停在安装建议。

## 1. 保留现场并安装

- 定位当前 Focu/the-few checkout、启动方式、研究 SQLite、daily 管线数据库、sources.yaml、历史 deliveries/episodes、TTS 配置、Open Notebook 地址和已有 profiles。只报告路径和配置是否存在，不输出密钥、cookie 或数据库私密内容。
- 修改前备份用户配置与数据。SQLite 用 backup API 或在停掉相关 writer 后一致性复制；备份目录仅当前用户可读。只暂停会与升级冲突的 Focu writer，不停止无关任务，不清理历史数据，不新建或扩大定时任务。
- 工作区若有未提交改动，保留原目录，在新的独立目录 clone；不要 reset --hard、clean、覆盖 sources.yaml 或删除旧环境。干净 checkout 可以 fetch 后切换并快进 main。旧 origin 若还是 the-few，改为上述 focu URL。
- 用 Python 3.10+ 在目标 checkout 建立 .venv，执行 `bash scripts/bootstrap.sh`，再 `.venv/bin/python -m pip install -e '.[daily]'` 安装可选采集依赖。若可选依赖安装失败，保留已安装核心并明确报告。
- 先读 `SKILL.md`、`docs/AGENT_INSTALL.md`、`docs/READER_APP.md`、`docs/PERSISTENT_PIPELINE.md`、`docs/MUSE_DELIVERY.md`。复用现有 TTS/Open Notebook 密钥和配置，不索要已有密钥，不创建新的付费服务。
- 显式确定研究数据库的绝对路径，并始终用 `.venv/bin/focu --db ABS_DB ...`。保留 FOCU_DB/THE_FEW_DB 兼容选择，不能悄悄切到空库。daily 的 `<data-dir>/few.sqlite3` 是另一种 schema，不能并入研究库。
- 检查 HEAD 等于安装时远端 main，并记录完整 SHA；检查 `.venv/bin/focu --version` 为 0.4.0，确认 `focu.__file__` 指向本次 checkout。

## 2. 验证合并后的功能

运行以下离线验证，并报告数量、失败和跳过原因：

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m unittest discover -s tests/unit -v
.venv/bin/focu --version
.venv/bin/focu --help
.venv/bin/focu --db ABS_DB doctor
.venv/bin/focu tts status
.venv/bin/focu podcast doctor
```

ABS_DB 必须替换成实际绝对路径。Open Notebook doctor 不能替代 worker 或真实生成验证。检查 API、worker、已有 episode/speaker profiles；缺失时先诊断现有部署，避免再装一个互相冲突的实例。不要凭空假设默认 profile 名。

在临时隔离目录验证 `focu daily run --text-only --dry-run`、`daily status` 和显式反馈记录/读取；使用临时 DB，避免把测试反馈写成我的真实偏好。不要擅自把旧 v0.1 数据 import 为已覆盖。需要迁移时按 PERSISTENT_PIPELINE.md 操作，目的地必须独立，不能默认使用 `--register-coverage`。

阅读界面的完成、收藏、撤销、有限批次，抓取快照与 SHA 验证，YouTube/LinkedIn collector 的离线行为都应通过现有测试。不要为了通过测试去伪造在线成功。

## 3. 准备真实阅读和播客批次

优先复用已有的完成研究、Evidence Pack、文章和 MP3，保留真实 ID 与来源关联。目标是先准备 3–5 张可读卡片，其中至少一张可播放已有播客；已有材料不足时，以我的已订阅源补足一次有上限的研究，而不是填入假内容。

我授权在本次验收中订阅 `anthropic-personal-blogs` 的仓库当前版本并进行一次显式采集。先在源包详情核对版本，再运行相应 subscribe、sources、collect 命令。此包目前有 6 位作者、4 个可用 RSS；失效或禁用的源如实保留。不是完整员工名单，不自动扩展其他订阅，不自动开启循环任务。

如果需要补充研究，读取原文，按 Evidence Pack provenance 合约创建真正有来源的小文章（保留原文语言，新写内容默认英文，除非我要求其他语言），保留引用与局限；按现有 capture -> start -> ingest-evidence -> report 流程入库。采集队列是原始素材，不是已验证结论。

播客优先使用已有的成功产物。若不足，使用现有已配置的 Open Notebook 和 profiles，最多新生成一集 5–7 分钟播客（默认英文，除非我指定其他语言）来验收；检查真实任务完成和 MP3，再通过 `focu deliver` 归档 research.md、transcript.json、podcast.mp3。不猜 episode ID，不将逐字稿代替研究报告。缺少服务/凭据时交付文章并报告音频阻塞，不伪造音频、不新开付费账户。

先准备好要发布的全部媒体，再运行 `reader publish`：一个 Evidence Pack 共用一张卡片，`--media-json` 填写相对于 media root 的真实音频/视频文件路径。批次 ID 唯一、内容固定、上限 5 条；不把旧未关联的 MP3 随意绑定给新的证据。发布后只 acknowledge 实际被覆盖的 raw record IDs。

## 4. 启动并交付给我测试

用实际数据库与媒体根目录启动 `.venv/bin/focu --db ABS_DB reader serve --media-root ABS_MEDIA_ROOT --port 8765`，通过现有进程管理方式保持运行，避免重复实例。

验证首页、批次切换、文章引用、音频播放/拖动、收藏、已读移出、撤销恢复和重启后状态。改写测试状态前明确选择验收内容，完成后恢复为待读。刷完显示终点，刷新不会触发生成。

本地服务仅监听 127.0.0.1。若已有我授权的带鉴权 HTTPS 反向代理，可复用该入口；上游 Host 需正确传为 127.0.0.1:8765，并按同源部署处理 Origin。不能通过关闭校验或向公网开放无鉴权服务来伪造手机可用。若没有适合的 HTTPS 入口，先给我本机访问/SSH 转发方式，明确 iPhone 添加主屏幕的剩余前提。不要把远程机器的 localhost 当成我手机能打开的地址。

最终给我：
- 安装目录、版本、完整 main SHA、备份位置；
- 可以实际访问的入口，或准确的访问前提；
- 3–5 条待测真实内容、文章和音频路径；
- 测试结果与已知限制；
- 最短的手动验收步骤，以及停止、重启、回滚命令。

全程不要打印密钥，不删除旧数据，不替我宣称已经完成手机安装或主观音质验收。

## Durable storage and private access

For Drive/Git state sync and Tailscale deployment, execute docs/MUSE_DATA_SYNC_DEPLOY.md using the delivered `focu sync` and `focu host` commands. Do not redevelop these adapters in Muse.
