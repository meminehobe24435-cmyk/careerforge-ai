/**
 * The demo posting behind the **Load Demo JD** button.
 *
 * A real Chinese embedded-engineering posting, not a template: it is the text that was sent to
 * `POST /jobs/analyze` during verification, and the parse it produces is the one the page was
 * checked against — role `嵌入式软件工程师（电机控制方向）`, company `某某智能科技`, location
 * `上海 · 张江`, 3 years, 本科, `parseConfidence 1.00`, 18 requirements across the three levels.
 *
 * It deliberately contains all three requirement levels (任职要求 / 加分项) and two skills the
 * demo profile does not have (Kubernetes, AUTOSAR), so a first run shows the skill tree, the
 * gaps and the unknowns without anyone having to write a posting by hand.
 */
export const DEMO_JD_COMPANY = '某某智能科技';

export const DEMO_JD_ROLE = '嵌入式软件工程师（电机控制方向）';

export const DEMO_JD_TEXT = `嵌入式软件工程师（电机控制方向）
某某智能科技
工作地点：上海 · 张江
经验要求：3 年以上 | 学历要求：本科及以上

岗位职责：
1. 负责基于 STM32 的无刷直流电机控制固件开发与调试；
2. 使用 FreeRTOS 设计多任务实时调度，保证控制周期稳定；
3. 负责 CAN 总线通信协议实现与整车联调；
4. 参与 PID 控制算法整定与性能优化，输出测试报告。

任职要求：
1. 本科及以上学历，电子、自动化、计算机相关专业；
2. 熟练使用 C 语言，熟悉 STM32 系列 MCU 与外设驱动（UART / SPI / I2C）；
3. 熟悉 FreeRTOS 或同类 RTOS，理解任务调度与优先级反转；
4. 熟悉 CAN、UART 等通信协议，能独立定位总线问题；
5. 具备良好的英文技术文档阅读能力。

加分项：
1. 熟悉 Kubernetes 容器编排，能维护 CI/CD 流水线；
2. 熟悉 AUTOSAR Classic 架构；
3. 有 GitHub 开源项目或技术博客。`;
