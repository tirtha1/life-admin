import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Filter } from "lucide-react";
import clsx from "clsx";
import { billsApi } from "@/services/api";
import BillCard from "@/components/BillCard";
import type { BillStatus } from "@/types";

const STATUS_TABS: { label: string; value: BillStatus | "all" }[] = [
  { label: "All", value: "all" },
  { label: "Extracted", value: "extracted" },
  { label: "Needs Review", value: "review_required" },
  { label: "Confirmed", value: "confirmed" },
  { label: "Reminded", value: "reminded" },
  { label: "Paid", value: "paid" },
];

export default function Bills() {
  const [statusFilter, setStatusFilter] = useState<BillStatus | "all">("all");
  const [search, setSearch] = useState("");

  const { data: bills, isLoading } = useQuery({
    queryKey: ["bills", "list", statusFilter],
    queryFn: () =>
      billsApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 100,
      }),
  });

  const filtered = bills?.filter((bill) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      bill.provider.toLowerCase().includes(q) ||
      bill.bill_type.includes(q) ||
      bill.email_subject?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Bills</h1>
          <p className="text-sm text-gray-500 mt-1">
            {bills?.length ?? 0} bills total
          </p>
        </div>
      </div>

      {/* Search + filter */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search bills..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Status tabs */}
      <div className="flex gap-1 overflow-x-auto pb-1">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setStatusFilter(tab.value)}
            className={clsx(
              "px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors",
              statusFilter === tab.value
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-600 border border-gray-200 hover:bg-gray-50"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="grid gap-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl border h-28 animate-pulse" />
          ))}
        </div>
      ) : filtered && filtered.length > 0 ? (
        <div className="grid gap-3">
          {filtered.map((bill) => (
            <BillCard key={bill.id} bill={bill} />
          ))}
        </div>
      ) : (
        <div className="text-center py-16 text-gray-400">
          <Filter className="w-10 h-10 mx-auto mb-3" />
          <p>No bills found</p>
          {statusFilter !== "all" && (
            <button
              onClick={() => setStatusFilter("all")}
              className="mt-2 text-blue-600 text-sm hover:underline"
            >
              Clear filter
            </button>
          )}
        </div>
      )}
    </div>
  );
}
