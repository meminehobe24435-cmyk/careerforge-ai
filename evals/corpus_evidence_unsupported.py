"""The evidence-validation cases the gate must refuse — they decide ``unsafe_support_rate``.

Split out of ``corpus_evidence.py`` when that module passed the 500-line guard, and split by *intent*
rather than by size: these cases are the ones that decide the metric this project treats as its most
important, so what the gate is being asked to refuse deserves to be readable on its own.

The families:

* **fabricated metrics** — a real change with a number nothing measured attached to it
  (``优化算法性能，提升 70%``); the rule layer rejects these before any model is consulted.
* **fabricated technologies** — a technology that appears nowhere in the material, sometimes beside
  one that does (``熟练使用 Redis 与 Kafka…`` with only Redis evidenced).
* **fabricated roles and scope** — ownership or company-wide reach asserted over evidence of
  participation (``作为技术负责人管理 20 人研发团队``, ``主导了公司级的技术选型``).
* **fabricated achievements** — a level or rank the evidence contradicts (a school-level second
  prize claimed as a national first prize).
* **quantities that do not exist** — six modules in three months when the evidence says two; a 90%
  coverage figure whose own evidence says coverage was never measured.

Two cases in the *accepted* module are the ones that still get through, and they are named in
``docs/QUALITY.md``: ``ev-0036`` (``吞吐提升明显``) and ``ev-0039`` (``整机调试``) are vagueness and
scope cases with no keyword to hang a rule on.
"""

from __future__ import annotations

__all__ = ["REFUSED"]

#: ``(id, claim, group, evidence, description, has_unsupported_number)``. The flag marks the
#: cases that assert a *magnitude*, which is what ``unsafe_numeric_support_rate`` counts.
REFUSED: list[tuple[str, str, str, list[tuple[str, str, str]], str, bool]] = [
    (
        "ev-0021",
        "独立负责整个飞控架构的设计与实现",
        "over_claim_scope",
        [
            ("repo_file", "flight_if.c", "飞控接口层调试：参与接口联调与参数核对。"),
            ("commit", "d6e7f8a", "fix(flight): 接口联调中的参数核对修正"),
        ],
        "Evidence shows participation in interface debugging, not ownership of the architecture. The claim is a scope inflation of real work: partial, not fabricated.  重新裁定（ev2.1）：被断言的动作（设计并拥有整套架构）没有发生：证据只到接口联调。",
        False,
    ),
    (
        "ev-0023",
        "使用 Redis 与 Kafka 构建高并发消息架构",
        "technology_inflation",
        [
            ("repo_file", "cache.py", "使用 Redis 做热点数据缓存。"),
            ("commit", "f8a9b0c", "feat(cache): Redis 热点缓存"),
        ],
        "Redis is evidenced; Kafka appears nowhere. Half the claim is unsupported, and half is real.  重新裁定（ev2.1）：Kafka 在证据中完全不存在——句子宣称的一半工作没有发生。",
        False,
    ),
    (
        "ev-0024",
        "在项目中同时使用了 STM32 与 ESP32 完成双芯片通信",
        "technology_inflation",
        [
            ("repo_file", "stm32_main.c", "STM32 主控固件：串口协议收发与状态机。"),
            ("commit", "a9b0c1d", "feat(stm32): 串口协议与状态机"),
        ],
        "Only one of the two chips is evidenced; the dual-chip communication is not.  重新裁定（ev2.1）：ESP32 在证据中完全不存在，双芯片通信无从谈起。",
        False,
    ),
    (
        "ev-0025",
        "优化了首页加载性能，首屏时间下降到 1.2 秒",
        "quantified_partial",
        [
            (
                "document_chunk",
                "perf_notes.md",
                "首页做了图片懒加载与代码分割，主观感受变快，未做正式测量。",
            ),
            ("repo_file", "home/lazy.tsx", "首页图片懒加载与路由级代码分割。"),
        ],
        "The optimisation happened; the 1.2s number is not measured anywhere. A magnitude without a benchmark is partial at best.  重新裁定（ev2.1）：1.2 秒这个数字没有任何测量支撑；数字是断言的一部分，不是措辞。",
        True,
    ),
    (
        "ev-0026",
        "负责数据库表结构设计与容量规划",
        "over_claim_scope",
        [
            ("document_chunk", "schema_review.md", "参与表结构评审，提出字段命名与索引建议。"),
            ("repo_file", "migrations/0001_init.sql", "初始表结构与索引定义。"),
        ],
        "Evidence shows review participation, not ownership of design and capacity planning.  重新裁定（ev2.1）：容量规划与表结构设计的归属未被证据支持（证据是评审参与）。",
        False,
    ),
    (
        "ev-0028",
        "把测试覆盖率提升到 90%",
        "quantified_unsupported",
        [
            ("document_chunk", "ci.md", "补充了部分单元测试并接入 CI，未统计覆盖率。"),
        ],
        "A single source, and it says coverage was never measured. The number has no basis.  重新裁定（ev2.1）：90% 覆盖率是编造的，且证据明确说明从未统计覆盖率。",
        True,
    ),
    (
        "ev-0029",
        "使用 Kubernetes 完成集群运维与故障排查",
        "technology_inflation",
        [
            ("repo_file", "Dockerfile", "单机 Docker 构建与运行说明。"),
        ],
        "Only single-machine Docker is evidenced; Kubernetes appears nowhere in the material.  重新裁定（ev2.1）：Kubernetes 在证据中完全不存在。",
        False,
    ),
    (
        "ev-0034",
        "重构了前端状态管理，把组件渲染次数减少一半",
        "quantified_unsupported",
        [
            ("repo_file", "store/query.ts", "状态管理迁移到集中式查询缓存。"),
            ("commit", "b0c1d2e", "refactor(store): 状态管理迁移"),
        ],
        "Two sources for the refactor, none for the halving. The mechanism is evidenced, the measurement is not.  重新裁定（ev2.1）：「减少一半」是一个量级断言，而证据里没有任何渲染次数测量。",
        True,
    ),
    (
        "ev-0035",
        "参与了国产化替代方案选型并输出了评估报告",
        "weak_evidence",
        [
            ("manual", "自我记录", "参与选型讨论。"),
        ],
        "Self-reported participation only, and no report is attached.  重新裁定（ev2.1）：承诺交付的评估报告不存在于任何证据中。",
        False,
    ),
    (
        "ev-0038",
        "实现了一个小型编译器前端，支持词法与语法分析",
        "side_project",
        [
            ("repo_file", "compiler/lexer.py", "词法分析器：把源码切分为 token 序列。"),
        ],
        "The lexer is evidenced; 'syntax analysis' is not mentioned anywhere.  重新裁定（ev2.1）：语法分析这一半工作没有证据（只有词法分析器）。",
        False,
    ),
    (
        "ev-0040",
        "在开源项目上提交了多个被合并的 PR",
        "weak_evidence",
        [
            ("commit", "d2e3f4a", "fix: 修正文档中的拼写错误"),
        ],
        "One commit is evidenced, and 'multiple merged PRs' is a stronger claim than one commit.  重新裁定（ev2.1）：「多个被合并的 PR」与证据（单个提交）不符：数量是断言的一部分。",
        False,
    ),
    (
        "ev-0041",
        "优化算法性能，提升 70%",
        "fabricated_metric",
        [
            ("document_chunk", "notes.md", "对控制回路做了重构，减少了单周期内的重复计算。"),
        ],
        "A refactor is described; 70% is measured nowhere. The rule layer should reject this before any model is consulted.",
        False,
    ),
    (
        "ev-0042",
        "支撑 10 万 QPS 的高并发架构设计",
        "fabricated_metric",
        [
            ("document_chunk", "arch.md", "参与后端服务架构讨论与接口设计。"),
        ],
        "No load test, no capacity figure, no architecture document with numbers.",
        False,
    ),
    (
        "ev-0043",
        "把控件的响应时间缩短了 40%",
        "fabricated_metric",
        [
            ("repo_file", "control.c", "调整了控制回路的执行顺序。"),
            ("commit", "e3f4a5b", "refactor(control): 调整执行顺序"),
        ],
        "Two sources for the change, none for the 40%. A quantified claim needs a quantified source.",
        False,
    ),
    (
        "ev-0044",
        "作为技术负责人管理 20 人研发团队",
        "fabricated_role",
        [
            ("document_chunk", "resume.md", "候选人材料中无团队管理经历。"),
            ("repo_file", "main.c", "嵌入式固件开发。"),
        ],
        "Nothing anywhere supports a management role, and the material says so explicitly.",
        False,
    ),
    (
        "ev-0045",
        "主导 AUTOSAR 架构设计与集成",
        "fabricated_technology",
        [
            ("document_chunk", "resume.md", "候选人材料中未出现 AUTOSAR 相关内容。"),
        ],
        "A technology that appears nowhere in the material.",
        False,
    ),
    (
        "ev-0046",
        "精通 Kubernetes 集群运维与故障排查",
        "fabricated_technology",
        [
            ("document_chunk", "resume.md", "候选人材料中只有单机 Docker 使用记录。"),
        ],
        "'Expert' in a technology the material never mentions.",
        False,
    ),
    (
        "ev-0047",
        "熟练使用 Redis 与 Kafka 构建高并发架构",
        "fabricated_technology",
        [
            ("document_chunk", "resume.md", "项目材料中未涉及任何消息队列或缓存组件。"),
        ],
        "Two technologies, neither present.",
        False,
    ),
    (
        "ev-0048",
        "独立完成芯片级驱动开发与流片验证",
        "fabricated_role",
        [
            ("document_chunk", "resume.md", "候选人材料中未涉及芯片设计或流片。"),
        ],
        "The chip-level work has no support at all (contrast ev-0027, where a genuine subset exists).",
        False,
    ),
    (
        "ev-0049",
        "用 Rust 重写了整个后端服务",
        "fabricated_technology",
        [
            ("repo_file", "server.py", "Python 服务端实现。"),
            ("commit", "f4a5b6c", "feat(server): Python 服务端接口"),
        ],
        "The evidence says Python; the claim says Rust. Nothing supports a rewrite.",
        False,
    ),
    (
        "ev-0050",
        "带领团队把系统可用性提升到 99.99%",
        "fabricated_metric",
        [
            ("document_chunk", "ops.md", "负责线上服务的日常维护与问题排查。"),
        ],
        "No availability measurement exists, and there is no team.",
        False,
    ),
    (
        "ev-0051",
        "设计了分布式事务框架并在生产环境验证",
        "fabricated_scope",
        [
            ("document_chunk", "notes.md", "单机服务的本地事务处理。"),
        ],
        "A local transaction implementation does not support a distributed framework.",
        False,
    ),
    (
        "ev-0052",
        "获得国家级算法竞赛一等奖",
        "fabricated_achievement",
        [
            ("achievement", "校级程序设计竞赛", "校级程序设计竞赛二等奖。"),
        ],
        "The evidence contradicts the level and the rank: provincial/national first prize vs a school-level second prize.",
        False,
    ),
    (
        "ev-0053",
        "把内存占用降低了 45%",
        "fabricated_metric",
        [
            ("document_chunk", "opt.md", "调整了缓冲区大小与任务栈配置。"),
        ],
        "A tuning change with no before/after measurement. The number is unfalsifiable as stated.",
        False,
    ),
    (
        "ev-0054",
        "使用 Kubernetes 完成了多云部署与灰度发布",
        "fabricated_technology",
        [
            ("repo_file", "deploy.sh", "单机 Docker Compose 部署脚本。"),
        ],
        "No Kubernetes, no multi-cloud, no canary mechanism.",
        False,
    ),
    (
        "ev-0055",
        "独立完成了 GPT 微调与私有化部署",
        "fabricated_technology",
        [
            ("document_chunk", "notes.md", "调用开源模型的 HTTP 接口完成问答。"),
        ],
        "Calling an API is not fine-tuning a model, and no private deployment exists.",
        False,
    ),
    (
        "ev-0056",
        "牵头制定了公司的代码安全规范并通过审计",
        "fabricated_role",
        [
            ("manual", "自我记录", "了解常见的安全编码注意事项。"),
        ],
        "Awareness is not authorship of a company standard, and no audit is referenced.",
        False,
    ),
    (
        "ev-0057",
        "在 3 个月内完成了 6 个模块的交付并提前两周上线",
        "fabricated_metric",
        [
            ("project", "内部工具", "交付了两个模块。"),
        ],
        "The evidence states two modules and gives no schedule.  重新裁定（ev2.1）：3 个月、6 个模块、提前两周三个数字都没有证据支撑。",
        True,
    ),
    (
        "ev-0058",
        "实现了基于 FPGA 的实时图像处理流水线",
        "fabricated_technology",
        [
            ("repo_file", "image.py", "使用 Python 做离线图像处理。"),
        ],
        "Python offline processing is not an FPGA pipeline.",
        False,
    ),
    (
        "ev-0059",
        "把接口响应时间从 800ms 优化到 120ms",
        "fabricated_metric",
        [
            ("document_chunk", "perf.md", "重构了接口的参数校验与查询逻辑。"),
        ],
        "The refactor is described; neither endpoint timing exists anywhere.",
        False,
    ),
    (
        "ev-0060",
        "主导了公司级的技术选型并落地到全部业务线",
        "fabricated_scope",
        [
            ("document_chunk", "notes.md", "参与了本组的技术选型讨论。"),
        ],
        "One team's discussion does not support a company-wide decision.",
        False,
    ),
]
