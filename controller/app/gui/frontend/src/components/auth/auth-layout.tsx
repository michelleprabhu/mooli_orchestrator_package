import { ReactNode } from "react";
import { Logo } from "@/components/ui/logo";

interface AuthLayoutProps {
  children: ReactNode;
}

export const AuthLayout = ({ children }: AuthLayoutProps) => {
  return (
    <div className="min-h-screen bg-gradient-auth flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-card rounded-2xl p-8 shadow-2xl border border-border">
          <div className="flex justify-center mb-8">
            <Logo />
          </div>
          {children}
        </div>
      </div>
    </div>
  );
};