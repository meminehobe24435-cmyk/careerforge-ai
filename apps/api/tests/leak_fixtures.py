"""The material that must never reach the ``agent_runs`` row, as fixtures.

Split out of ``failure_support.py`` when that module crossed the file-length gate, and along the seam
that matters: everything else in ``failure_support`` describes *how a provider fails*, and this file
describes *what a provider leaks when it does*. Two suites care about the second without caring about
the first (``test_error_report.py`` drives the sanitiser directly, ``test_failed_run_trace.py`` reads
the row it produced), and a fixture this specific is easier to audit on its own.

Every value here is fake and shaped like the real thing on purpose. The sanitiser in
``services/error_report.py`` matches on *shape* — a vendor prefix, a bearer scheme, a header
assignment, a phone number — because a blocklist of real secrets would only catch the ones someone
already thought of. The API key is not a real key, the token is not a signed token, and the document
is written material rather than anyone's résumé.
"""

from __future__ import annotations

__all__ = [
    "DOCUMENT_TEXT",
    "FAKE_API_KEY",
    "FAKE_BEARER",
    "LEAKY_ERROR",
    "RESUME_EMAIL",
    "RESUME_PHONE",
]

#: A fake credential in the vendor's exact shape.
FAKE_API_KEY = "sk-proj-ZZZZdeadbeefNOTAREALKEY0123456789"
#: A bearer header value, as an ``httpx`` error message would quote it.
FAKE_BEARER = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ZmFrZXBheWxvYWQ.c2lnbmF0dXJl"
#: The personal details in :data:`DOCUMENT_TEXT`, named separately so a test can assert on them one
#: at a time rather than on a substring of the document.
RESUME_PHONE = "13800001111"
RESUME_EMAIL = "zhangwei.private@example.com"
#: Stand-in for a résumé or a job description: long, prose-shaped, and unmistakably private. It is
#: *not* whitespace-free, so a per-token length rule alone would miss it.
DOCUMENT_TEXT = (
    f"张伟 男 1996 年出生 手机 {RESUME_PHONE} 邮箱 {RESUME_EMAIL} "
    "教育经历：某某大学 电子信息工程 本科 2014-2018 平均分 85.6 "
    "工作经历：某某科技有限公司 嵌入式软件工程师 2018-2023 负责 STM32 平台的电机控制固件开发，"
    "参与 CAN 总线通信协议设计，独立完成 PID 参数整定与整机调试，累计交付 6 个量产项目。"
    "项目经历：两轮自平衡机器人控制链路，使用 FreeRTOS 划分任务，UART DMA 回传数据，"
    "控制周期稳定在 1kHz。技能：C/C++、STM32、FreeRTOS、CAN、SPI、I2C、PID、PCB 设计。"
)
#: What a provider leaks when it echoes the request and its own headers into the failure. If ANY of
#: this appears in a stored row, the sanitiser has failed at the one job it has.
LEAKY_ERROR = (
    f"upstream rejected the request: Authorization: {FAKE_BEARER} api_key={FAKE_API_KEY} "
    f"body={{'text': '{DOCUMENT_TEXT}'}}"
)
