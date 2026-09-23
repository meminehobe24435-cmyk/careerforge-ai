"""Retrieval corpus: evidence fragments and queries with explicit gold relevance.

Ground truth is attached to **each query**, not to its topic. That distinction
matters, and the first version of this file got it wrong: labelling every fragment
of a topic as relevant to every query about that topic made Recall@5 measure "did
you find every fragment that mentions the general area", which is not a question
anybody asks. A query about ``STM32F407`` is relevant to the fragment containing
that string, and relevance has to be defined per query.

Two query styles are included on purpose, because they exercise the two retrieval
arms differently:

* **exact_term** (``STM32F407``, ``CANopen``) — where lexical search should win;
  dense retrieval tends to generalise a rare identifier into oblivion.
* **intent** (``多任务实时调度怎么划分优先级``) — where semantic search should win,
  since the evidence phrases it as "任务按优先级划分并周期调度".

Structure: ``(topic, fragments, queries)`` where each query is
``(query, style, gold_fragment_indices)``.
"""

from __future__ import annotations

__all__ = ["RETRIEVAL_TOPICS"]

#: ``(topic, fragments, ((query, style, gold_indices), ...))``
RETRIEVAL_TOPICS: tuple[
    tuple[str, tuple[str, ...], tuple[tuple[str, str, tuple[int, ...]], ...]], ...
] = (
    (
        "stm32",
        (
            "在 STM32F407 上完成外设初始化：先使能 RCC 时钟，再配置 GPIO 复用功能，最后设置外设寄存器。",
            "STM32 的启动流程从复位向量开始，经过 SystemInit 后进入 main，时钟树在进入 main 前完成配置。",
        ),
        (
            ("STM32F407", "exact_term", (0,)),
            ("STM32 HAL 库", "exact_term", (0,)),
            ("外设初始化为什么必须先使能时钟", "intent", (0,)),
            ("上电后外设寄存器写入无效怎么查", "intent", (0,)),
            ("时钟树是在什么阶段配置的", "intent", (1,)),
            ("SystemInit 之后执行什么", "exact_term", (1,)),
        ),
    ),
    (
        "freertos",
        (
            "基于 FreeRTOS 实现多任务实时控制：使用 vTaskDelayUntil 保证周期任务的节拍稳定，任务间通过队列通信。",
            "FreeRTOS 中任务与中断服务程序之间使用队列传递数据，共享资源由互斥量保护以避免优先级反转。",
        ),
        (
            ("FreeRTOS", "exact_term", (0, 1)),
            ("vTaskDelayUntil", "exact_term", (0,)),
            ("多任务实时调度怎么划分优先级", "intent", (0,)),
            ("中断和任务之间怎么传数据", "intent", (1,)),
            ("优先级反转是什么，怎么避免", "intent", (1,)),
            ("互斥量在什么场景下必须用", "intent", (1,)),
        ),
    ),
    (
        "pid",
        (
            "通过编码器读取转速，使用 PID 控制器计算占空比输出到电机驱动，积分项做了抗饱和处理。",
            "整定 PID 参数时先调比例再调积分，阶跃响应出现过冲说明比例增益偏大。",
        ),
        (
            ("PID", "exact_term", (0, 1)),
            ("编码器反馈", "exact_term", (0,)),
            ("闭环调速的占空比怎么算出来", "intent", (0,)),
            ("积分饱和怎么处理", "intent", (0,)),
            ("阶跃响应一直振荡该调哪个参数", "intent", (1,)),
            ("参数整定的顺序是什么", "intent", (1,)),
        ),
    ),
    (
        "can",
        (
            "实现 CANopen 协议栈的节点管理与错误帧处理，总线仲裁采用非破坏性逐位仲裁机制。",
            "CAN 总线出现大量错误帧时，先检查终端电阻与波特率配置，再逐节点断开定位。",
        ),
        (
            ("CANopen", "exact_term", (0,)),
            ("CAN 总线仲裁", "exact_term", (0,)),
            ("多个节点同时发送会不会冲突", "intent", (0,)),
            ("总线上错误帧很多怎么排查", "intent", (1,)),
            ("终端电阻不匹配会有什么现象", "intent", (1,)),
        ),
    ),
    (
        "uart_dma",
        (
            "使用 UART DMA 配合空闲中断与环形缓冲区接收不定长数据帧，接收过程不占用 CPU 轮询。",
            "UART 波特率不匹配时会出现持续乱码，接收偶发丢字节需要检查 DMA 缓冲长度与中断优先级。",
        ),
        (
            ("UART DMA", "exact_term", (0,)),
            ("空闲中断", "exact_term", (0,)),
            ("不定长数据帧怎么接收", "intent", (0,)),
            ("怎么做到接收时不占用 CPU", "intent", (0,)),
            ("串口接收偶尔丢字节怎么查", "intent", (1,)),
            ("波特率不对会看到什么现象", "intent", (1,)),
        ),
    ),
    (
        "pgvector",
        (
            "使用 pgvector 存储证据向量，查询时按余弦相似度检索 Top-K 片段，索引采用 HNSW。",
            "pgvector 的 HNSW 索引参数 m 与 ef_construction 决定了召回率与构建时间的权衡。",
        ),
        (
            ("pgvector", "exact_term", (0, 1)),
            ("HNSW 索引", "exact_term", (0, 1)),
            ("向量检索怎么找最相似的片段", "intent", (0,)),
            ("余弦相似度怎么做近邻搜索", "intent", (0,)),
            ("召回率和构建时间怎么取舍", "intent", (1,)),
            ("索引参数 m 的作用是什么", "intent", (1,)),
        ),
    ),
    (
        "rag_rrf",
        (
            "混合检索将关键词检索与语义检索的结果用 RRF 融合，避免不同通道的分数不可比问题。",
            "RAG 链路中先分块再嵌入，检索命中后把片段与元数据一起交给生成模型。",
        ),
        (
            ("RRF 融合", "exact_term", (0,)),
            ("RAG", "exact_term", (1,)),
            ("关键词和语义检索结果怎么合并", "intent", (0,)),
            ("不同检索通道的分数为什么不能直接相加", "intent", (0,)),
            ("检索到的片段怎么交给大模型", "intent", (1,)),
            ("为什么先分块再嵌入", "intent", (1,)),
        ),
    ),
    (
        "docker",
        (
            "使用 Docker Compose 编排服务与数据库，通过 healthcheck 控制启动顺序，数据卷持久化。",
            "多阶段构建把编译依赖留在构建阶段，运行镜像只保留产物，并以非 root 用户启动。",
        ),
        (
            ("Docker Compose", "exact_term", (0,)),
            ("healthcheck", "exact_term", (0,)),
            ("怎么保证服务按顺序启动", "intent", (0,)),
            ("数据库数据怎么持久化", "intent", (0,)),
            ("怎么让运行镜像更小", "intent", (1,)),
            ("为什么容器不应该用 root 跑", "intent", (1,)),
        ),
    ),
    (
        "react_next",
        (
            "Next.js App Router 中服务端组件负责数据获取，客户端组件只用于需要交互的部分。",
            "深色主题在服务端注入 data-theme 属性，避免首屏闪烁与 hydration 不一致。",
        ),
        (
            ("Next.js App Router", "exact_term", (0,)),
            ("服务端组件", "exact_term", (0,)),
            ("哪些组件必须是客户端组件", "intent", (0,)),
            ("数据获取应该放在哪一层", "intent", (0,)),
            ("怎么避免主题切换时闪白", "intent", (1,)),
            ("hydration 不一致是怎么产生的", "intent", (1,)),
        ),
    ),
    (
        "pytest",
        (
            "使用 pytest 编写单元测试与集成测试，集成测试通过 httpx 的 ASGI transport 直接调用应用。",
            "pytest 的 fixture 用于准备测试数据与数据库会话，参数化用例覆盖边界条件。",
        ),
        (
            ("pytest", "exact_term", (0, 1)),
            ("ASGI transport", "exact_term", (0,)),
            ("怎么在不启动服务的情况下测接口", "intent", (0,)),
            ("集成测试和单元测试怎么分工", "intent", (0,)),
            ("怎么复用测试数据准备逻辑", "intent", (1,)),
            ("参数化用例用来做什么", "intent", (1,)),
        ),
    ),
)
