# 给 Muse 的指令（可直接复制）

> 把下面整段发给 Muse。链接指向 FOCU 仓库 `main`。在 PR 合并前，这些链接还打不开。

---

以后我让你做研究报告或日报时，按 FOCU 的研究报告流程来做，交付一页自包含的响应式 HTML。

先读：
- 流程与契约：https://github.com/ialchemist-dev/focu/blob/main/docs/research-reports/README.md
- 英文研究任务模板：https://github.com/ialchemist-dev/focu/blob/main/docs/research-reports/templates/research-mission.md
- 页面构建说明：https://github.com/ialchemist-dev/focu/blob/main/docs/research-reports/templates/page-builder-brief.md
- HTML 模板：https://github.com/ialchemist-dev/focu/blob/main/docs/research-reports/kit/template.html
- 通过检查的完整示例（虚构数据）：https://github.com/ialchemist-dev/focu/tree/main/docs/research-reports/fixture/sample

步骤：
1. 用一句话写清我的目的和问题。只从当前对话中选出相关的范围和偏好，并写下偏好 ID。这些 ID 是你本次手工选的，不是自动记忆。不要附上我的原始资料。
2. 按模板写一份自包含的英文研究任务（mission.md），列出编号问题、指标、单位、日期和比较口径。搜索默认用英文。
3. 产出 report.md、notes/sources-key.md、claims.json。每个数字都要标明类别（事实 / 估计 / 厂商说法 / 派生），并给出来源和简短引文。派生值写出公式和输入。不编造。完成后用 frozen.sha256 冻结，之后不再修改。
4. 复制 template.html，做成 page/index.html：先放一分钟自上而下的图文总览，再放各节的表格、图表、结论，最后是局限和来源。数字图表只能用 claims.json 里的数。需要补充事实时，放进新的 addenda/addendum-N/ 并登记来源，不要改原文件。
5. 检查。在仓库根目录运行：
   ```
   python3 docs/research-reports/kit/check_report.py <research_dir>
   ```
   必须通过。如果环境里已经有 Playwright 和浏览器，再运行 `node docs/research-reports/kit/render_qa.mjs <本地URL> <仓库外目录>`，覆盖 390px 和 1440px。没有就在 run.json 里记 not_run，不要安装任何东西。
6. 在 run.json 中如实记录：实际用了哪些工具；每层 QA 的状态（passed / failed / not_run）；语义审阅是你自己做的（same_worker）还是独立审阅（independent）；我的验收状态是 pending。结构检查和截图都不能证明内容正确。
7. 交付 HTML 链接或文件，并附一句话结论。研究用的 markdown 是内部记录，不用发给我。

日报轻量版：所有采集到的条目都要覆盖，不编造。数字照样要有引用和类别。跨条目的叙事必须标注为“叙事综合”，并且只能基于已引用的条目。

不要：说自己在沙箱里，或说已经和我的账户隔离；改动 FOCU 的定时日报或生产管线；整段复制外部文章；把截图或我的私人资料放进 Git；使用新的付费服务。
