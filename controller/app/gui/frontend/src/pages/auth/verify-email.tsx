import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "@/components/auth/auth-layout";
import { GoogleButton } from "@/components/auth/google-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const VerifyEmail = () => {
  const [email, setEmail] = useState("aisvarya@gmail.com");
  const [code, setCode] = useState(["", "", "", "", "", ""]);
  const navigate = useNavigate();

  const handleCodeChange = (index: number, value: string) => {
    if (value.length <= 1) {
      const newCode = [...code];
      newCode[index] = value;
      setCode(newCode);
      
      // Auto focus next input
      if (value && index < 5) {
        const nextInput = document.getElementById(`code-${index + 1}`);
        nextInput?.focus();
      }
    }
  };

  const handleVerifyEmail = () => {
    const enteredCode = code.join("");
    if (enteredCode === "123456") {
      navigate("/dashboard");
    }
  };

  return (
    <AuthLayout>
      <div className="space-y-6">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-semibold text-foreground">Verify your email</h1>
          <p className="text-muted-foreground">Enter the one-time code to create an account</p>
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email" className="text-foreground font-medium">
              Email ID
            </Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-12 bg-input border-border"
              disabled
            />
          </div>

          <div className="space-y-2">
            <Label className="text-foreground font-medium">
              Verification Code
            </Label>
            <div className="flex gap-3 justify-center">
              {code.map((digit, index) => (
                <Input
                  key={index}
                  id={`code-${index}`}
                  type="text"
                  value={digit}
                  onChange={(e) => handleCodeChange(index, e.target.value)}
                  className="w-12 h-12 text-center text-lg font-semibold bg-input border-border"
                  maxLength={1}
                />
              ))}
            </div>
          </div>

          <Button 
            onClick={handleVerifyEmail}
            className="w-full h-12 bg-primary hover:bg-primary/90 text-primary-foreground font-medium"
          >
            Verify Email
          </Button>

          <div className="text-center">
            <span className="text-muted-foreground">Already have an account? </span>
            <Link to="/login" className="text-primary hover:underline font-medium">
              Log in
            </Link>
          </div>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-4 bg-card text-muted-foreground">Or</span>
            </div>
          </div>

          <GoogleButton text="Sign up with Google" />
        </div>
      </div>
    </AuthLayout>
  );
};

export default VerifyEmail;