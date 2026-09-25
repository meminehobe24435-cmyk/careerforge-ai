import type { ClaimStatus } from '@/lib/validator-api';

/**
 * The three presets, written against the demo profile's evidence.
 *
 * They are *shortcuts for typing*, not canned verdicts: each button puts its sentence in the
 * textarea and sends it to `POST /evidence/validate`, and the panel shows whatever the gate
 * returns. The expected verdict below is what the live stack actually returned when these
 * sentences were measured against the demo evidence (`.tmp/p13-validator-populate.py`); it is
 * printed as a hint so the reader knows what the preset is *for*, never as the answer.
 *
 * Each preset was measured, not guessed, and the three sentences were chosen so that they still
 * land on three different verdicts after `detect_missing_technical` was changed (PHASE 13) to
 * *block* on a technology the taxonomy knows and the evidence does not carry — which is why the
 * middle preset is the ownership variant rather than the "one invented technology" variant that
 * used to be here: an absent-but-known technology like TensorFlow now makes a claim unsupported,
 * not partially supported.
 *
 * If the evidence base changes, the verdicts change with it — which is the point of the page.
 */
export interface DemoClaim {
  id: string;
  /** Button label. */
  label: string;
  /** One line on what this preset is testing, shown beside the button. */
  hint: string;
  /** The sentence the button submits, verbatim. */
  text: string;
  /** The verdict this preset is built to reach on the demo evidence. */
  expected: ClaimStatus;
  expectedLabel: string;
}

export const DEMO_CLAIMS: DemoClaim[] = [
  {
    id: 'strong',
    label: 'Strong',
    hint: 'STM32, FreeRTOS, PID and I2C all appear in the evidence, with two independent source kinds behind them.',
    text: '使用 STM32 与 FreeRTOS 实现串级 PID 控制环，通过 I2C 读取传感器数据',
    expected: 'supported',
    expectedLabel: 'supported',
  },
  {
    id: 'partial',
    label: 'Partial',
    hint: 'The first half is carried by the evidence; the second asserts ownership of a role ("主导了") and names RRF, a term the evidence never carries. The gate answers with a shortened, supported version.',
    text: '使用 STM32 与 FreeRTOS 实现串级 PID 控制环，主导了 RRF 融合排序模块的设计',
    expected: 'partially_supported',
    expectedLabel: 'partially supported',
  },
  {
    id: 'unsupported',
    label: 'Unsupported',
    hint: 'Rust, Kubernetes and TensorFlow never appear in the evidence, and nothing measures a 90% latency drop. The gate declines a rewrite: the sentence would still name technologies the evidence does not carry.',
    text: '使用 Rust 与 TensorFlow 部署 Kubernetes 推理服务，把延迟降低了 90%',
    expected: 'unsupported',
    expectedLabel: 'unsupported',
  },
];
