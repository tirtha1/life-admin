import { Routes, Route, Navigate } from "react-router-dom";
import Header from "@/components/Header";
import Dashboard from "@/pages/Dashboard";
import Bills from "@/pages/Bills";
import BillDetail from "@/pages/BillDetail";
import Transactions from "@/pages/Transactions";

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/bills" element={<Bills />} />
          <Route path="/bills/:id" element={<BillDetail />} />
          <Route path="/transactions" element={<Transactions />} />
        </Routes>
      </main>
    </div>
  );
}
