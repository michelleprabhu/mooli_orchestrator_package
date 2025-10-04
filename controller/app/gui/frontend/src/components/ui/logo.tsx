import { cn } from "@/lib/utils";
import logoImage from "@/assets/moolai-logo.png";

interface LogoProps {
  className?: string;
  showText?: boolean;
}

export const Logo = ({ className, showText = true }: LogoProps) => {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <img src={logoImage} alt="Moolai" className="h-8 w-8" />
      {showText && (
        <span className="text-xl font-semibold text-foreground">Moolai</span>
      )}
    </div>
  );
};