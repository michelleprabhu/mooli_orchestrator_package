import { Sidebar } from "./sidebar";
import { Outlet } from "react-router-dom";

export const DashboardLayout = () => {
  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        {/* Nested routes render here */}
        <Outlet />
      </main>
    </div>
  );
};

export default DashboardLayout;
