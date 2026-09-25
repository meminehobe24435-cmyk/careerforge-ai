"""The evidence-validation cases the gate must accept, and the dataset builder.

**Why this dataset exists.** The previous claim corpus was generated from templates: 120 rows held
only 22 distinct ``(claim, kind)`` pairs — one claim repeated twelve times — and every case carried a
single evidence snippet. A metric computed on that is a metric about a template. Worse, its labels
tracked the rule layer's own logic, so ``support_recall 1.0000`` showed that the gate agreed with
itself, not that it agreed with a reader. That number was replaced in PHASE 12 by this one.

**How the cases were written.** Each is a sentence a real candidate might put on a resume, paired
with the evidence that either does or does not carry it, and a label assigned by the rubric below —
read by a human, before running anything, without consulting the gate's code. Because the labels do
not come from the implementation they can be falsified by it, and the report names every case where
the gate disagrees.

**The rubric (revised in ev2.1 after the first honest run).**

* ``supported`` — every substantive element of the claim (the action, the technology, the scope and
  any magnitude) is carried by at least two *independent* evidence sources. Independence is by
  kind: two files from one repository are one source, a file and a commit are two.
* ``partially_supported`` — **everything the sentence asserts did happen**, but the role, the extent
  or the measurement is weaker than stated: a shared credit, a smaller scope, one source where
  corroboration was implied. The honest verdict for "true, but not as stated".
* ``unsupported`` — a substantive element *did not happen as stated*: a technology the evidence never
  mentions, a measurement nothing benchmarks, a deliverable that does not exist, a role or scale the
  evidence contradicts. *Unsupported* is not *false*: a claim can be true and still unevidenced, and
  the gate's job is the second question.

Twelve cases moved from ``partially_supported`` to ``unsupported`` in ev2.1, each carrying the
reason for the move. The first run of this dataset showed the gate accepting 10% of the non-supported
claims, which exposed two real defects in the gate (both fixed — see ``docs/QUALITY.md``); it also
showed that my original reading was the weaker one for sentences asserting work that never happened.

**What makes a case hard.** Several are deliberately adversarial to one layer each: synonyms the
tokeniser must connect (``实时操作系统`` for FreeRTOS), technologies that appear in the evidence but
not in the claim's action, true-but-self-reported claims (a ``manual`` entry), an invented number
attached to an otherwise well-evidenced project, and a claim whose words match the evidence while its
scope does not. A dataset of easy cases measures nothing.
"""

from __future__ import annotations

from typing import Any

from corpus_evidence_shared import evidence_rows
from corpus_evidence_unsupported import REFUSED

__all__ = ["ACCEPTED", "build_evidence_cases"]

#: ``(id, claim, group, evidence, description)``. The first twenty are ``supported``, the rest
#: ``partially_supported``; the label is attached in ``build_evidence_cases`` so a case's line
#: here stays about the case rather than about its verdict.
ACCEPTED: list[tuple[str, str, str, list[tuple[str, str, str]], str]] = [
    (
        "ev-0001",
        "基于 STM32 与 FreeRTOS 开发多任务实时控制系统",
        "firmware",
        [
            (
                "repo_file",
                "freertos_tasks.c",
                "基于 STM32 的 FreeRTOS 多任务控制：创建 4 个任务，按优先级划分，用队列在任务间传递控制指令。",
            ),
            (
                "commit",
                "a1b2c3d",
                "feat(firmware): STM32 + FreeRTOS 多任务实时控制框架，任务优先级与队列通信",
            ),
            ("readme", "README.md", "本项目使用 STM32F4 与 FreeRTOS 实现多任务实时控制。"),
        ],
        "Three independent sources, all naming STM32 and FreeRTOS and the multitasking control.",
    ),
    (
        "ev-0002",
        "使用 CAN 总线完成节点之间的通信与仲裁测试",
        "embedded_comms",
        [
            (
                "repo_file",
                "can_driver.c",
                "CAN 总线驱动：报文收发、标识符过滤、总线仲裁与错误帧计数。",
            ),
            ("commit", "b2c3d4e", "feat(can): CAN 节点通信、仲裁与错误帧监控"),
        ],
        "The claim names CAN, communication and arbitration; both sources carry them.",
    ),
    (
        "ev-0003",
        "用 Python 与 FastAPI 实现订单服务的 REST 接口",
        "backend_api",
        [
            (
                "repo_file",
                "orders/router.py",
                "使用 FastAPI 定义订单相关 REST 接口，包含创建、查询与状态流转。",
            ),
            ("commit", "c3d4e5f", "feat(api): Python FastAPI 订单服务 REST 接口与状态流转"),
        ],
        "Action, language and framework all appear in two independent sources.",
    ),
    (
        "ev-0004",
        "在 PostgreSQL 中设计并优化订单查询的索引",
        "backend_data",
        [
            (
                "repo_file",
                "migrations/0003_order_index.sql",
                "为 PostgreSQL 的 orders 表增加复合索引，覆盖按状态与创建时间的查询。",
            ),
            (
                "document_chunk",
                "query_review.md",
                "订单查询优化记录：PostgreSQL 复合索引把状态+时间查询的扫描行数降低。",
            ),
        ],
        "A file and a document: two kinds, both describing the index work.",
    ),
    (
        "ev-0005",
        "实现了基于 RAG 的文档问答流程，包含分块与检索",
        "ai_app",
        [
            (
                "repo_file",
                "rag/pipeline.py",
                "RAG 文档问答：按标题分块、向量检索与关键词检索融合后交给模型生成答案。",
            ),
            ("commit", "d4e5f6a", "feat(rag): 文档分块、混合检索与答案生成流程"),
            ("readme", "README.md", "文档问答使用 RAG（检索增强生成）流程。"),
        ],
        "Chunking and retrieval are both evidenced, in three sources.",
    ),
    (
        "ev-0006",
        "用 Docker Compose 编排本地开发环境",
        "devops",
        [
            (
                "repo_file",
                "docker-compose.yml",
                "Docker Compose 定义 api、web 与 PostgreSQL 三个服务及依赖关系。",
            ),
            ("readme", "README.md", "本地开发使用 Docker Compose 一键启动。"),
        ],
        "A compose file plus a README statement: two kinds, same fact.",
    ),
    (
        "ev-0007",
        "为前端页面实现了键盘可访问的拖拽看板",
        "frontend",
        [
            (
                "repo_file",
                "kanban-board.tsx",
                "看板支持键盘操作：方向键移动卡片、确认键落位，并用 aria-live 播报状态。",
            ),
            ("commit", "e5f6a7b", "feat(web): 键盘可访问的看板拖拽与状态播报"),
        ],
        "Both sources name the keyboard interaction and the board.",
    ),
    (
        "ev-0008",
        "编写单元测试覆盖了结算逻辑的边界条件",
        "quality",
        [
            (
                "repo_file",
                "tests/test_settlement.py",
                "结算逻辑单元测试：零金额、负值、四舍五入与并发重复提交的边界用例。",
            ),
            ("commit", "f6a7b8c", "test(settlement): 边界条件与并发重复提交用例"),
        ],
        "Tests and their commit: two kinds, describing the same coverage.",
    ),
    (
        "ev-0009",
        "在 Azure Pipelines 上搭建了自动化构建与部署流水线",
        "devops",
        [
            (
                "repo_file",
                "azure-pipelines.yml",
                "Azure Pipelines 流水线：构建、单元测试、镜像推送与部署三个阶段。",
            ),
            (
                "document_chunk",
                "release_notes.md",
                "发布流程已迁移到 Azure Pipelines，构建与部署自动化。",
            ),
        ],
        "The pipeline file and a release note agree.",
    ),
    (
        "ev-0010",
        "使用 Redis 缓存会话数据以降低数据库压力",
        "backend_data",
        [
            (
                "repo_file",
                "session_store.py",
                "会话数据写入 Redis，设置过期时间，读取时优先命中缓存。",
            ),
            ("commit", "a7b8c9d", "perf(session): 会话数据迁移到 Redis 缓存"),
        ],
        "Redis caching is the action, and both sources describe it.",
    ),
    (
        "ev-0011",
        "为嵌入式项目实现了看门狗与断电恢复机制",
        "firmware",
        [
            (
                "repo_file",
                "watchdog.c",
                "独立看门狗喂狗逻辑与复位原因记录；掉电后从备份寄存器恢复运行状态。",
            ),
            ("commit", "b8c9d0e", "feat(firmware): 看门狗与掉电恢复"),
            ("experience", "某科技 · 嵌入式实习", "负责固件稳定性：加入看门狗保护与掉电恢复逻辑。"),
        ],
        "Three kinds available; the claim's two mechanisms are both present.",
    ),
    (
        "ev-0012",
        "把简历解析器从正则改写为分段器，支持中英文混排",
        "ai_app",
        [
            (
                "repo_file",
                "resume/parser.py",
                "简历解析：按标题分段的解析器，支持中英文混排与项目符号列表。",
            ),
            ("commit", "c9d0e1f", "refactor(parser): 正则改为分段器，支持中英文混排"),
        ],
        "The refactor and the language support are both stated in two sources.",
    ),
    (
        "ev-0013",
        "设计并实现了电机控制的 PID 闭环，控制周期 1kHz",
        "embedded_control",
        [
            (
                "repo_file",
                "pid_control.c",
                "PID 闭环控制，控制周期 1kHz，包含积分限幅与输出饱和处理。",
            ),
            ("commit", "d0e1f2a", "feat(control): PID 闭环，1kHz 控制周期"),
            ("document_chunk", "control_report.md", "电机控制使用 PID 闭环，实测控制周期 1kHz。"),
        ],
        "A quantified claim whose magnitude (1kHz) appears in the evidence — the case that must pass.",
    ),
    (
        "ev-0014",
        "实现了技能词典的归一化，把别名映射到同一技能",
        "ai_app",
        [
            (
                "repo_file",
                "skill_taxonomy.py",
                "技能归一化：别名表把 FreeRTOS / Free RTOS / freertos 映射到同一技能 id。",
            ),
            ("commit", "e1f2a3b", "feat(taxonomy): 技能别名归一化"),
        ],
        "Normalisation is the action and both sources name it.",
    ),
    (
        "ev-0015",
        "为公开页面实现了服务端渲染，并做了 PII 脱敏",
        "backend_api",
        [
            (
                "repo_file",
                "app/candidate/[slug]/page.tsx",
                "公开候选人页面在服务端渲染；邮箱与手机号在返回前被脱敏。",
            ),
            ("commit", "f2a3b4c", "feat(public): 公开页服务端渲染与 PII 脱敏"),
            (
                "document_chunk",
                "privacy_notes.md",
                "公开页输出前扫描并移除邮箱、手机号等个人信息。",
            ),
        ],
        "Two mechanisms, three sources, all naming them.",
    ),
    (
        "ev-0016",
        "用 pytest 与 Vitest 建立了前后端测试体系",
        "quality",
        [
            ("repo_file", "ci.yml", "CI 运行 pytest（后端）与 Vitest（前端）两套测试。"),
            ("readme", "CONTRIBUTING.md", "提交前需通过 pytest 与 Vitest。"),
        ],
        "Both tool names appear in two kinds of source.",
    ),
    (
        "ev-0017",
        "实现了向量检索与关键词检索的 RRF 融合排序",
        "ai_app",
        [
            (
                "repo_file",
                "rag/fusion.py",
                "RRF 融合：把向量检索与 BM25 关键词检索的排名按 k=60 融合。",
            ),
            ("commit", "a3b4c5d", "feat(rag): RRF 融合向量与关键词排名"),
        ],
        "The fusion algorithm is the claim and is named in both sources.",
    ),
    (
        "ev-0018",
        "为简历优化功能加入了证据门禁，无依据的句子会被拒绝",
        "ai_app",
        [
            (
                "repo_file",
                "agents/validator.py",
                "证据门禁：规则层拒绝无依据的量化表述，检索不到证据的句子判为不支持。",
            ),
            ("commit", "b4c5d6e", "feat(validator): 证据门禁与无依据句子的拒绝"),
            ("document_chunk", "ai_design.md", "简历优化不通过证据门禁就不会输出改写。"),
        ],
        "Three sources describe the gate and its refusal behaviour.",
    ),
    (
        "ev-0019",
        "用逻辑分析仪定位了 SPI 时序问题并修正了片选控制",
        "embedded_comms",
        [
            (
                "repo_file",
                "spi_sensor.c",
                "SPI 片选控制修正：片选拉低到首字节之间的建立时间不足，导致偶发读到 0xFF。",
            ),
            (
                "document_chunk",
                "debug_log.md",
                "用逻辑分析仪确认 SPI 片选时序问题，修正后通信稳定。",
            ),
        ],
        "The debugging action and its fix appear in both sources.",
    ),
    (
        "ev-0020",
        "为自动化部署编写了回滚脚本并接入流水线",
        "devops",
        [
            (
                "repo_file",
                "deploy/rollback.sh",
                "回滚脚本：按版本号重新部署上一个镜像并做健康检查。",
            ),
            ("commit", "c5d6e7f", "feat(deploy): 回滚脚本与健康检查"),
            (
                "document_chunk",
                "release_process.md",
                "发布流程包含回滚脚本，流水线在健康检查失败时自动触发。",
            ),
        ],
        "The script, its commit and the described process agree.",
    ),
    (
        "ev-0022",
        "主导了后端服务的重构",
        "over_claim_role",
        [
            ("document_chunk", "refactor_notes.md", "参与后端服务重构的技术方案讨论与接口梳理。"),
            ("commit", "e7f8a9b", "refactor(api): 接口梳理与参数校验统一"),
        ],
        "'Led' against a document that says 'participated in'. The work happened; the role is stated more strongly than the evidence carries.",
    ),
    (
        "ev-0027",
        "独立完成了芯片级驱动开发与流片验证",
        "over_claim_scope",
        [
            ("document_chunk", "resume_notes.md", "项目中未涉及芯片设计或流片环节。"),
            ("repo_file", "driver.c", "外设驱动开发与寄存器配置。"),
        ],
        "The driver work is real; the chip-level design and tape-out are explicitly absent from the material. Partial because a genuine subset exists.",
    ),
    (
        "ev-0030",
        "设计了完整的权限模型并落地到所有接口",
        "over_claim_scope",
        [
            ("repo_file", "auth/deps.py", "基于角色的接口鉴权依赖，覆盖订单与用户两个模块。"),
        ],
        "One module pair is evidenced; 'all endpoints' is not, and there is only one source.",
    ),
    (
        "ev-0031",
        "主导了跨部门的技术方案评审并推动落地",
        "over_claim_role",
        [
            ("manual", "自我记录", "参加了两次跨部门方案评审。"),
        ],
        "A hand-typed entry is a self-report, and it describes attendance, not leadership.",
    ),
    (
        "ev-0032",
        "使用 pgvector 实现了证据片段语义检索",
        "ai_app",
        [
            ("repo_file", "vector_store.py", "使用 pgvector 存储证据向量并做近邻检索。"),
        ],
        "The work is evidenced by exactly one source. One confident source is still one source — this is the case that must not come back as fully supported.",
    ),
    (
        "ev-0033",
        "为团队引入了代码评审规范并显著降低了缺陷率",
        "quantified_unsupported",
        [
            ("document_chunk", "team_notes.md", "推动建立了代码评审流程，缺陷率变化未统计。"),
        ],
        "The process change is described; 'significantly reduced' has no measurement behind it.",
    ),
    (
        "ev-0036",
        "用 C++ 重写了通信中间件，吞吐提升明显",
        "vague_magnitude",
        [
            ("repo_file", "middleware.cpp", "通信中间件使用 C++ 重写，替换原有实现。"),
            ("commit", "c1d2e3f", "refactor(middleware): 使用 C++ 重写"),
        ],
        "'明显' is vague enough that no benchmark could confirm or deny it; the rewrite itself is well evidenced.",
    ),
    (
        "ev-0037",
        "负责线上服务的日常维护与问题排查",
        "experience_only",
        [
            ("experience", "某公司 · 运维实习", "负责线上服务日常维护与问题排查。"),
        ],
        "A single experience entry restating the claim. One kind is one source.",
    ),
    (
        "ev-0039",
        "完成两轮自平衡机器人的整机调试",
        "partial_scope",
        [
            ("project", "Balance Robot", "两轮自平衡小车：负责控制算法的参数调试。"),
            ("repo_file", "balance.c", "平衡控制：角度环与速度环的串级 PID 调参记录。"),
        ],
        "Control tuning is evidenced; whole-machine debugging (mechanical, wiring, power) is not.",
    ),
]


def build_evidence_cases() -> list[dict[str, Any]]:
    """Every golden case as a dataset row: the accepted half, then the refused half.

    The split is by module, not by label: ``ACCEPTED`` holds both ``supported`` and
    ``partially_supported`` cases (the label is attached per case below), and ``REFUSED`` holds the
    ones that must not pass.
    """
    rows: list[dict[str, Any]] = []
    for case_id, claim, group, evidence, description in ACCEPTED:
        rows.append(
            evidence_rows(
                case_id,
                claim,
                group,
                evidence,
                description,
                "supported" if case_id < "ev-0021" else "partially_supported",
            )
        )
    for case_id, claim, group, evidence, description, quantified in REFUSED:
        rows.append(
            evidence_rows(
                case_id,
                claim,
                group,
                evidence,
                description,
                "unsupported",
                quantified=quantified,
            )
        )
    return rows
