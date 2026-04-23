function sum(values) {
  return values.reduce((total, value) => total + value, 0);
}

function appliedAmountForInvoice(invoiceId, payments) {
  return sum(
    payments.flatMap((payment) => payment.allocations)
      .filter((allocation) => allocation.invoiceId === invoiceId)
      .map((allocation) => allocation.amountCents)
  );
}

export function computeFinancialSummary({ invoices, payments, donations, year }) {
  const receivableCents = sum(
    invoices
      .filter((invoice) => invoice.status === "issued" || invoice.status === "paid")
      .map((invoice) => Math.max(invoice.amountCents - appliedAmountForInvoice(invoice.id, payments), 0))
  );

  const prepaidCents = sum(
    payments.map((payment) => {
      const appliedCents = sum(payment.allocations.map((allocation) => allocation.amountCents));
      return Math.max(payment.amountCents - appliedCents, 0);
    })
  );

  const donationsYtdCents = sum(
    donations
      .filter((donation) => new Date(donation.receivedAt).getUTCFullYear() === year)
      .map((donation) => donation.amountCents)
  );

  return {
    currency: "USD",
    receivableCents,
    prepaidCents,
    donationsYtdCents
  };
}

