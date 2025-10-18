"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';

export interface User {
  email: string;
  name?: string;
  groups?: string[];
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isLocalDev: boolean;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  
  const isLocalDev = process.env.NEXT_PUBLIC_AUTH_DISABLED === 'true';

  const fetchUserInfo = React.useCallback(async () => {
    setIsLoading(true);
    try {
      if (isLocalDev) {
        setUser({
          email: 'admin@localhost',
          name: 'Admin',
          groups: ['aws-idp-ai-admins', 'aws-idp-ai-users']
        });
        return;
      }

      // Auth API는 ALB를 통해 호출 (Cognito 헤더를 위해)
      const isEcsEnvironment = typeof window !== 'undefined' && 
                               window.location.hostname.includes('elb.amazonaws.com');
      
      let authEndpoint;
      if (isEcsEnvironment) {
        // ECS 환경: 현재 호스트를 사용하여 ALB 통해 호출
        authEndpoint = `${window.location.protocol}//${window.location.host}/api/auth/user`;
      } else {
        // 로컬/다른 환경: API Gateway 또는 로컬 서버 호출
        const authApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';
        authEndpoint = `${authApiUrl}/api/auth/user`;
      }
      
      // 디버깅 로그
      console.log('🔧 Auth request debug:', {
        isEcsEnvironment,
        hostname: typeof window !== 'undefined' ? window.location.hostname : 'N/A',
        NEXT_PUBLIC_ECS_BACKEND_URL: process.env.NEXT_PUBLIC_ECS_BACKEND_URL,
        NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
        authEndpoint
      });
        
      const response = await fetch(authEndpoint);
      if (response.ok) {
        const userData = await response.json();
        setUser(userData);
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Failed to fetch user info:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [isLocalDev]);

  const logout = async () => {
    console.log('🚪 Logout attempt started');
    console.log('🔍 isLocalDev:', isLocalDev);
    console.log('🔍 hostname:', typeof window !== 'undefined' ? window.location.hostname : 'N/A');

    if (isLocalDev) {
      console.log('⚠️ 로컬 개발 환경에서는 로그아웃이 시뮬레이션됩니다.');
      setUser(null);
      return;
    }

    // ECS 환경 체크 (ALB DNS 이름 감지)
    const isEcsEnvironment = typeof window !== 'undefined' &&
                             (window.location.hostname.includes('elb.amazonaws.com') ||
                              window.location.hostname.includes('cloudfront.net'));

    console.log('🔍 isEcsEnvironment:', isEcsEnvironment);

    try {
      if (isEcsEnvironment) {
        console.log('🔧 ECS environment detected - calling backend logout API');

        // 백엔드 로그아웃 API 호출 (ALB를 통해)
        const logoutEndpoint = `${window.location.protocol}//${window.location.host}/api/auth/logout`;
        console.log('📡 Calling logout endpoint:', logoutEndpoint);

        const response = await fetch(logoutEndpoint, {
          method: 'POST',
          credentials: 'include', // 쿠키 포함
        });

        if (response.ok) {
          const data = await response.json();
          console.log('✅ Logout API response:', data);

          // Backend에서 Set-Cookie 헤더로 ALB 세션 쿠키를 이미 삭제했습니다
          // (HttpOnly 쿠키는 서버에서만 삭제 가능)

          // Cognito logout URL이 있으면 리다이렉트
          if (data.logout_url) {
            console.log('🔄 Redirecting to Cognito logout:', data.logout_url);
            window.location.href = data.logout_url;
            return;
          } else {
            console.log('⚠️ No logout_url, redirecting home');
            window.location.href = data.redirect_url || '/';
            return;
          }
        } else {
          console.error('❌ Logout API failed:', response.status);
          const errorText = await response.text();
          console.error('❌ Error response:', errorText);
          // fallback: 홈으로
          window.location.href = '/';
        }
      } else {
        console.log('🔧 Non-ECS environment - redirecting to home');
        window.location.href = '/';
      }
    } catch (error) {
      console.error('❌ Logout error:', error);
      // fallback: 홈으로
      window.location.href = '/';
    }
  };

  const refreshUser = async () => {
    await fetchUserInfo();
  };

  useEffect(() => {
    fetchUserInfo();
  }, [fetchUserInfo]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isLocalDev,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}