"use client";

import { Button } from "@/components/ui/button";
import { CheckCircle } from "lucide-react";
import { useAuth } from "@/contexts/auth-context";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LoggedOutPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  // If user is logged in, redirect to studio automatically
  useEffect(() => {
    if (!isLoading && user) {
      console.log('User is logged in on logged-out page, redirecting to studio');
      router.push('/studio');
    }
  }, [user, isLoading, router]);

  const handleRelogin = () => {
    // Navigate to home -> ALB will redirect to Cognito login page
    window.location.href = '/';
  };

  // Show loading state while checking auth
  if (isLoading) {
    return null;
  }

  // If user is logged in, don't show the logout message
  if (user) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-gray-900 via-purple-900/20 to-gray-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-gray-900/80 backdrop-blur-xl rounded-2xl border border-purple-500/30 p-8 text-center shadow-2xl shadow-purple-500/10">
        <div className="flex justify-center mb-6">
          <div className="w-20 h-20 bg-gradient-to-br from-purple-500/20 to-blue-500/20 rounded-full flex items-center justify-center">
            <CheckCircle className="w-12 h-12 text-purple-400" />
          </div>
        </div>

        <h1 className="text-3xl font-bold text-white mb-4">
          Logged Out Successfully
        </h1>

        <p className="text-gray-300 mb-8">
          You have been logged out successfully.
          <br />
          Click the button below to log in with a different account.
        </p>

        <Button
          onClick={handleRelogin}
          className="w-full bg-gradient-to-r from-purple-600 to-blue-600 hover:from-purple-700 hover:to-blue-700 text-white font-semibold py-3 rounded-lg transition-all shadow-lg hover:shadow-purple-500/50"
        >
          Log In Again
        </Button>
      </div>
    </div>
  );
}
