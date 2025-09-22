import React from 'react';

interface MoolaiLogoProps {
  className?: string;
  showText?: boolean;
}

export const MoolaiLogo: React.FC<MoolaiLogoProps> = ({ className = "", showText = true }) => {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div className="relative w-8 h-8 flex items-center justify-center">
        <img 
          src="/favicon.ico"
          alt="Logo"
          className="w-8 h-8 object-contain"
        />
      </div>
      {showText && (
        <span className="text-xl font-semibold text-foreground tracking-wide">MoolAI</span>
      )}
    </div>
  );
};