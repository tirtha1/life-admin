import { differenceInCalendarDays, format, parseISO } from "date-fns";

const integerFormatter = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 0,
});

const decimalFormatter = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 2,
});

export function formatInr(amount: number, withCode = true) {
  const prefix = withCode ? "INR " : "";
  return `${prefix}${integerFormatter.format(amount)}`;
}

export function formatMoney(amount: number, currency = "INR") {
  return `${currency} ${decimalFormatter.format(amount)}`;
}

export function formatShortDate(value: string) {
  return format(parseISO(value), "dd MMM");
}

export function formatLongDate(value: string) {
  return format(parseISO(value), "dd MMM yyyy");
}

export function formatMonthDate(value: string) {
  return format(parseISO(value), "MMMM d, yyyy");
}

export function getFriendlyDueDate(dueDate: string | null) {
  if (!dueDate) {
    return {
      tone: "neutral" as const,
      label: "No due date",
    };
  }

  const daysAway = differenceInCalendarDays(parseISO(dueDate), new Date());
  if (daysAway < 0) {
    return {
      tone: "danger" as const,
      label: `${Math.abs(daysAway)}d overdue • ${formatShortDate(dueDate)}`,
    };
  }
  if (daysAway === 0) {
    return {
      tone: "warning" as const,
      label: `Due today • ${formatShortDate(dueDate)}`,
    };
  }
  if (daysAway <= 2) {
    return {
      tone: "warning" as const,
      label: `Due in ${daysAway}d • ${formatShortDate(dueDate)}`,
    };
  }
  return {
    tone: "neutral" as const,
    label: `Due in ${daysAway}d • ${formatShortDate(dueDate)}`,
  };
}
