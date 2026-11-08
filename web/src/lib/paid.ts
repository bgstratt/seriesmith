// Asking before a render that costs money: a hosted model, or a Comfy partner node (the server's
// targets.billing says where it's billed; null on your own GPU, which goes without asking).

/** The question asked before `what` is sent, or null when it isn't billed. */
export function paidAsk(paid: string | null | undefined, what: string): string | null {
  return paid ? `${what}

${paid}. Go ahead?` : null;
}

/** Whether to go ahead: at once when it isn't billed, else what the person answers. */
export function confirmPaid(paid: string | null | undefined, what: string): boolean {
  const q = paidAsk(paid, what);
  return !q || window.confirm(q);
}
