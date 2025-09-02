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

  const fetchUserInfo = async () => {
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
  };

  const logout = () => {
    console.log('🚪 Logout attempt started');
    console.log('🔍 isLocalDev:', isLocalDev);
    console.log('🔍 hostname:', typeof window !== 'undefined' ? window.location.hostname : 'N/A');
    
    if (isLocalDev) {
      console.log('로컬 개발 환경에서는 로그아웃이 시뮬레이션됩니다.');
      return;
    }
    
    // ECS 환경 체크
    const isEcsEnvironment = typeof window !== 'undefined' && 
                             window.location.hostname.includes('elb.amazonaws.com');
    
    console.log('🔍 isEcsEnvironment:', isEcsEnvironment);
    
    if (isEcsEnvironment) {
      console.log('🔧 ECS environment detected - clearing ALB session cookies');
      // ALB + Cognito 환경에서는 세션 쿠키 삭제 후 홈으로 리다이렉트
      // ALB 세션 쿠키 삭제
      document.cookie = 'AWSELBAuthSessionCookie=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=' + window.location.hostname + ';';
      document.cookie = 'AWSELBAuthSessionCookie-0=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=' + window.location.hostname + ';';
      document.cookie = 'AWSELBAuthSessionCookie-1=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=' + window.location.hostname + ';';
      
      console.log('🔄 Redirecting to home page for re-authentication');
      // 쿠키 삭제 후 홈으로 리다이렉트 (ALB가 다시 인증 요구)
      setTimeout(() => {
        window.location.href = '/';
      }, 100);
    } else {
      console.log('🔧 Non-ECS environment - trying OAuth2 logout');
      // 다른 환경에서는 기본 OAuth2 로그아웃 경로 시도
      window.location.href = '/oauth2/sign_out';
    }
  };

  const refreshUser = async () => {
    await fetchUserInfo();
  };

  useEffect(() => {
    fetchUserInfo();
  }, [isLocalDev]);

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