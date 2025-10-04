import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Logo } from "@/components/ui/logo";
import { 
  LayoutDashboard, 
  Building2, 
  Settings, 
  Info, 
  FileText, 
  User 
} from "lucide-react";

const navigation = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Organizations", href: "/organizations", icon: Building2 },
  { name: "Configuration", href: "/configuration", icon: Settings },
  { name: "Organization Details", href: "/organization-details", icon: Info },
  { name: "Logs", href: "/logs", icon: FileText },
];

export const Sidebar = () => {
  const location = useLocation();

  return (
    <div className="w-64 h-screen bg-sidebar border-r border-sidebar-border flex flex-col">
      <div className="p-6">
        <Logo />
      </div>

      <nav className="flex-1 px-4 pb-4 space-y-1">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          const Icon = item.icon;
          
          return (
            <Link
              key={item.name}
              to={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 text-sm font-medium rounded-lg transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground"
              )}
            >
              <Icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-sidebar-border">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="w-8 h-8 bg-sidebar-accent rounded-full flex items-center justify-center">
            <User className="h-4 w-4 text-sidebar-accent-foreground" />
          </div>
          <span className="text-sm font-medium text-sidebar-foreground">Profile</span>
        </div>
      </div>
    </div>
  );
};