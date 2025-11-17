import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AuthCard } from '@/components/AuthCard';
import { Button } from '@/components/ui/button';

const BACKEND_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const Login: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string>('');

  // Check for error from OAuth callback
  useEffect(() => {
    const errorParam = searchParams.get('error');
    if (errorParam) {
      const errorMessages: Record<string, string> = {
        'no_code': 'No authorization code received from Microsoft',
        'token_exchange_failed': 'Failed to exchange authorization code',
        'no_token': 'No access token received',
        'invalid_token': 'Token validation failed',
        'callback_failed': 'Authentication callback failed'
      };
      setError(errorMessages[errorParam] || `Authentication error: ${errorParam}`);
    }
  }, [searchParams]);

  const handleMicrosoftLogin = () => {
    // Redirect to backend OAuth endpoint
    window.location.href = `${BACKEND_URL}/api/v1/auth/entra/login`;
  };

  return (
    <AuthCard>
      <div className="text-center mb-8">
        <h1 className="text-2xl font-semibold text-foreground mb-2">Welcome Back</h1>
        <p className="text-sm text-muted-foreground">Sign in with your Microsoft account</p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      <Button 
        onClick={handleMicrosoftLogin}
        className="w-full h-12 bg-[#0078D4] hover:bg-[#106EBE] text-white font-medium rounded-lg flex items-center justify-center gap-3"
      >
        <svg className="w-5 h-5" viewBox="0 0 21 21" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="1" y="1" width="9" height="9" fill="#F25022"/>
          <rect x="1" y="11" width="9" height="9" fill="#00A4EF"/>
          <rect x="11" y="1" width="9" height="9" fill="#7FBA00"/>
          <rect x="11" y="11" width="9" height="9" fill="#FFB900"/>
        </svg>
        <span>Sign in with Microsoft</span>
      </Button>

      <div className="text-center mt-6">
        <p className="text-sm text-muted-foreground">
          Don't have a Microsoft account?{' '}
          <a 
            href="https://signup.microsoft.com" 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-orange-primary hover:text-orange-light"
          >
            Create one
          </a>
        </p>
      </div>
    </AuthCard>
  );
};