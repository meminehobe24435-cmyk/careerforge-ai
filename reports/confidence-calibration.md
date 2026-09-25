# Confidence calibration — evidence_validation

- cases 60 (dataset `evidence_validation` @ `ev2.1`), 10 bins
- **ECE** 0.0166 · **Brier** 0.1034 · accuracy 0.8833 · mean confidence 0.8999
- high-confidence mistakes (confidence ≥ 0.75): 7 · unsafe supports: 2

| bucket | cases | mean confidence | actual accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.0–0.1 | 0 | — | — | — |
| 0.1–0.2 | 0 | — | — | — |
| 0.2–0.3 | 0 | — | — | — |
| 0.3–0.4 | 0 | — | — | — |
| 0.4–0.5 | 0 | — | — | — |
| 0.5–0.6 | 0 | — | — | — |
| 0.6–0.7 | 0 | — | — | — |
| 0.7–0.8 | 0 | — | — | — |
| 0.8–0.9 | 45 | 0.8900 | 0.8889 | +0.0011 |
| 0.9–1.0 | 15 | 0.9296 | 0.8667 | +0.0629 |

A positive gap means over-confidence: the system claimed more than it delivered. ECE is the case-weighted mean absolute gap; Brier is the mean squared error, which punishes a single confident mistake more than ECE does.

## High-confidence mistakes

| case | claim | confidence | gold | predicted |
| --- | --- | ---: | --- | --- |
| `ev-0010` | "使用 Redis 缓存会话数据以降低数据库压力" | 0.9300 | `supported` | `partially_supported` |
| `ev-0030` | "设计了完整的权限模型并落地到所有接口" | 0.8900 | `partially_supported` | `unsupported` |
| `ev-0036` | "用 C++ 重写了通信中间件，吞吐提升明显" | 0.9100 | `partially_supported` | `supported` |
| `ev-0039` | "完成两轮自平衡机器人的整机调试" | 0.8900 | `partially_supported` | `supported` |
| `ev-0052` | "获得国家级算法竞赛一等奖" | 0.8900 | `unsupported` | `partially_supported` |
| `ev-0057` | "在 3 个月内完成了 6 个模块的交付并提前两周上线" | 0.8900 | `unsupported` | `partially_supported` |
| `ev-0058` | "实现了基于 FPGA 的实时图像处理流水线" | 0.8900 | `unsupported` | `partially_supported` |
