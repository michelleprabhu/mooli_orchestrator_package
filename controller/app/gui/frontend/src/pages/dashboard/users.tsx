import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Search } from "lucide-react";

type Overview = { success: boolean; data?: { total_requests: number } };

const statsCards = [
  { title: "Total Users", value: "6", change: "+0% from yesterday", trend: "up" },
  { title: "Active Users Today", value: "6", change: "+13% from yesterday", trend: "up" },
  { title: "Avg. Session Duration", value: "45 min", change: "-16.9% from last month", trend: "down" },
];

const users = Array.from({ length: 6 }).map(() => ({
  name: "Arun Krishnaswamy",
  email: "dummy@moolai.ai",
  role: "User",
  status: "Online",
  lastActive: "2 mins ago",
}));

export const Users = () => {
  const [activeUsers, setActiveUsers] = useState<number | null>(null);

  useEffect(() => {
    api.get<Overview>("/api/v1/controller/overview").then(({ data }) => {
      setActiveUsers((data.data?.total_requests ?? 0) % 10); // placeholder derivation
    });
  }, []);

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-foreground">User Management</h1>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-3 gap-6 mb-8">
        {statsCards.map((stat, index) => (
          <Card key={index} className="bg-card border-border p-6">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium text-muted-foreground">{stat.title}</h3>
                {index === 1 && (
                  <div className="w-24 h-12 relative">
                    <svg className="w-full h-full" viewBox="0 0 100 50">
                      <path d="M0,40 Q25,20 50,30 T100,10" stroke="hsl(var(--primary))" strokeWidth="2" fill="none" opacity="0.8" />
                    </svg>
                  </div>
                )}
              </div>
              <div>
                <div className="text-3xl font-bold text-foreground">
                  {index === 1 ? (activeUsers ?? "…") : stat.value}
                </div>
                <p className={`text-sm mt-1 ${stat.trend === "up" ? "text-green-400" : "text-red-400"}`}>{stat.change}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Users Table */}
      <Card className="bg-card border-border">
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-lg font-semibold text-foreground">All Users</h2>
              <p className="text-muted-foreground text-sm">Manage the users of your organization logged into the system</p>
            </div>
            <Button className="bg-primary hover:bg-primary/90 text-primary-foreground">Add User</Button>
          </div>

          <div className="relative mb-6">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search" className="pl-10 bg-input border-border h-10" />
          </div>

          <div className="overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-3 px-0 text-sm font-medium text-muted-foreground">USER</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">ROLE</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">STATUS</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">LAST ACTIVE</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user, index) => (
                  <tr key={index} className="border-b border-border/50">
                    <td className="py-4 px-0">
                      <div>
                        <div className="font-medium text-foreground">{user.name}</div>
                        <div className="text-sm text-muted-foreground">{user.email}</div>
                      </div>
                    </td>
                    <td className="py-4 px-4 text-foreground">{user.role}</td>
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                        <span className="text-green-400 text-sm">{user.status}</span>
                      </div>
                    </td>
                    <td className="py-4 px-4 text-muted-foreground text-sm">{user.lastActive}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between mt-6">
            <div className="text-sm text-muted-foreground">1-10 of 97</div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Rows per page: 10</span>
              <div className="flex items-center gap-1 ml-4">
                <Button variant="ghost" size="sm" className="h-8 w-8 p-0"><span>‹</span></Button>
                <span className="text-sm text-muted-foreground">1/10</span>
                <Button variant="ghost" size="sm" className="h-8 w-8 p-0"><span>›</span></Button>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Bottom pagination */}
      <div className="fixed bottom-8 left-1/2 transform -translate-x-1/2 bg-card border border-border rounded-lg px-4 py-2 shadow-lg">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" className="h-8 w-8 p-0"><span>‹</span></Button>
          <span className="text-sm text-muted-foreground">46 / 56</span>
          <Button variant="ghost" size="sm" className="h-8 w-8 p-0"><span>›</span></Button>
        </div>
      </div>
    </div>
  );
};

export default Users;
