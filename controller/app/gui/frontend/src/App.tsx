// App.tsx
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { DashboardLayout } from "@/components/dashboard/dashboard-layout";

import NotFound from "./pages/NotFound";
import SignUp from "./pages/auth/signup";
import Login from "./pages/auth/login";
import VerifyEmail from "./pages/auth/verify-email";
import Dashboard from "./pages/dashboard/dashboard";
import Organizations from "./pages/dashboard/organizations";
import OrganizationsDetail from "./pages/dashboard/organizations-detail";
import Configuration from "./pages/dashboard/configuration";
import Logs from "./pages/dashboard/logs";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          {/* Default route - redirect to login */}
          <Route path="/" element={<Navigate to="/login" replace />} />
          
          {/* Public/auth */}
          <Route path="/signup" element={<SignUp />} />
          <Route path="/login" element={<Login />} />
          <Route path="/verify-email" element={<VerifyEmail />} />

          {/* Dashboard layout with sidebar */}
          <Route path="/dashboard" element={<DashboardLayout />}>
            <Route index element={<Dashboard />} />
          </Route>
          <Route path="/organizations" element={<DashboardLayout />}>
            <Route index element={<Organizations />} />
          </Route>
          <Route path="/organization-details" element={<DashboardLayout />}>
            <Route index element={<OrganizationsDetail />} />
          </Route>
          <Route path="/configuration" element={<DashboardLayout />}>
            <Route index element={<Configuration />} />
          </Route>
          <Route path="/logs" element={<DashboardLayout />}>
            <Route index element={<Logs />} />
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
