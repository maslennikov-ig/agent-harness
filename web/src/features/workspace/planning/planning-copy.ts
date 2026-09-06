export type PlanningKind = "specification" | "plan";

// Legacy named the accepted artifact and the register action in different
// grammatical cases. One nominative noun cannot serve both in Russian, so the
// tab keeps the two forms it actually renders instead of interpolating a label.
const COPY: Record<PlanningKind, { accepted: string; register: string }> = {
  plan: {
    accepted: "Принятый план",
    register: "Зарегистрировать план",
  },
  specification: {
    accepted: "Принятая спецификация",
    register: "Зарегистрировать спецификацию",
  },
};

export function planningCopy(kind: PlanningKind) {
  return COPY[kind];
}
