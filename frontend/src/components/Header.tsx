import { NavLink } from "react-router-dom";
import { LayoutDashboard, Receipt, Brain } from "lucide-react";
import clsx from "clsx";

export default function Header() {
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="w-6 h-6 text-blue-600" />
          <span className="font-bold text-gray-900 text-lg">Life Admin</span>
          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">AI</span>
        </div>

        <nav className="flex items-center gap-1">
          {[
            { to: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
            { to: "/bills", icon: Receipt, label: "Bills" },
          ].map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                  isActive
                    ? "bg-blue-50 text-blue-700"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                )
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
