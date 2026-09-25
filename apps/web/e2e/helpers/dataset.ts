/**
 * The Chinese fixtures the specs analyse, quote and try to disprove.
 *
 * Kept in one file so a claim, the evidence that is supposed to support it and the interview
 * answer that talks about it cannot drift apart into three slightly different stories.
 */

/** A résumé the demo account does not start with: STM32 / FreeRTOS / CAN / PID work. */
export const RESUME = `教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2022-07 至 2022-12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。

项目经历
平衡小车 2022
基于 STM32 的 PID 平衡控制，使用 FreeRTOS 任务调度与 CAN 通信。
`;

/** A posting whose requirements the fixture résumé covers only partly — that gap is the point. */
export const JOB_DESCRIPTION = `岗位名称：嵌入式软件工程师（电机控制方向）
公司：某某智能科技
工作地点：上海

岗位职责：
1. 负责基于 STM32 的无刷电机控制固件开发与调试；
2. 使用 FreeRTOS 设计多任务实时调度，保证控制周期稳定；
3. 负责 CAN 总线通信协议实现与整车联调；
4. 参与 PID 控制算法整定与性能优化。

任职要求：
1. 本科及以上学历，电子、自动化、计算机相关专业；
2. 熟练使用 C 语言，熟悉 STM32 系列 MCU 与外设驱动；
3. 熟悉 FreeRTOS 或同类 RTOS，理解任务调度与优先级反转；
4. 熟悉 CAN、UART、SPI 等通信协议；
5. 有 Docker 与 CI/CD 经验者优先。
`;

/** A sentence the fixture résumé states almost verbatim, with no invented numbers in it. */
export const SUPPORTED_CLAIM =
  '使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。';

/** Two hard numbers, a superlative and a technology — none of which any evidence measures. */
export const EXAGGERATED_CLAIM =
  '主导过 10 万 QPS 的分布式交易系统重构，性能提升 70%，是全公司最强的架构师。';

/** An answer with enough substance for the heuristic evaluator to score it, and no more. */
export const INTERVIEW_ANSWER =
  '我先按控制回路划分 FreeRTOS 任务：采样、PID 计算、CAN 收发各一个任务，用队列传递数据，' +
  '并为 PID 任务设最高优先级。这样做的好处是控制周期稳定，代价是内存占用更高；' +
  '实测调度周期抖动小于 50us，CAN 报文延迟约 2ms。';
