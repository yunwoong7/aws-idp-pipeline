"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
import { usersApi } from '@/lib/api';

export interface User {
  email: string;
  name?: string;
  groups?: string[];
}

export interface UserPermissions {
  can_create_index: boolean;
  can_delete_index: boolean;
  can_upload_documents: boolean;
  can_delete_documents: boolean;
  accessible_indexes: string[] | "*";
  available_tabs: string[];
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isLocalDev: boolean;
  logout: () => void;
  refreshUser: () => Promise<void>;

  // Permission-related fields
  permissions: UserPermissions | null;
  userRole: string | null;
  isAdmin: boolean;
  isUser: boolean;
  canCreateIndex: boolean;
  canDeleteIndex: boolean;
  canUploadDocuments: boolean;
  canDeleteDocument: (indexId: string) => boolean;
  canAccessIndex: (indexId: string) => boolean;
  hasTabAccess: (tabName: string) => boolean;
  accessibleIndexes: string[] | "*";
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [permissions, setPermissions] = useState<UserPermissions | null>(null);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [permissionsLoading, setPermissionsLoading] = useState(false);

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
      // ECS 환경 판단: ALB 도메인 OR 현재 도메인이 BACKEND_URL과 일치
      const isEcsEnvironment = typeof window !== 'undefined' && (
        window.location.hostname.includes('elb.amazonaws.com') ||
        (process.env.NEXT_PUBLIC_ECS_BACKEND_URL &&
         process.env.NEXT_PUBLIC_ECS_BACKEND_URL.includes(window.location.hostname))
      );

      let authEndpoint;
      if (isEcsEnvironment) {
        // ECS/ALB/커스텀 도메인 환경: 현재 호스트를 사용하여 ALB 통해 호출 (Cognito 헤더 포함)
        authEndpoint = `${window.location.protocol}//${window.location.host}/api/auth/user`;
      } else {
        // 로컬 개발 환경: API Gateway 또는 로컬 서버 직접 호출
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

    // 프로덕션 환경 체크 (localhost가 아닌 모든 환경)
    const isProductionEnvironment = typeof window !== 'undefined' &&
                                    !['localhost', '127.0.0.1'].includes(window.location.hostname);

    console.log('🔍 isProductionEnvironment:', isProductionEnvironment);

    try {
      if (isProductionEnvironment) {
        console.log('🔧 Production environment detected - calling backend logout API');

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
        console.log('🔧 Local development environment - redirecting to home');
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

  // Fetch permissions when user changes
  useEffect(() => {
    const fetchPermissions = async () => {
      if (!user || isLoading) {
        return;
      }

      // Local dev mode - give admin permissions automatically
      if (isLocalDev) {
        console.log('🔧 Local dev mode: Setting admin permissions');
        setPermissions({
          can_create_index: true,
          can_delete_index: true,
          can_upload_documents: true,
          can_delete_documents: true,
          accessible_indexes: "*",
          available_tabs: ["documents", "analysis", "search", "verification"]
        });
        setUserRole("admin");
        setPermissionsLoading(false);
        return;
      }

      try {
        setPermissionsLoading(true);
        const userData = await usersApi.getCurrentUser();
        console.log('📋 User permissions loaded:', userData);
        setPermissions(userData.permissions);
        setUserRole(userData.role);
      } catch (err) {
        console.error('Failed to fetch permissions:', err);
        // Set default permissions on error
        setPermissions({
          can_create_index: false,
          can_delete_index: false,
          can_upload_documents: false,
          can_delete_documents: false,
          accessible_indexes: [],
          available_tabs: ["search"]
        });
        setUserRole("user");
      } finally {
        setPermissionsLoading(false);
      }
    };

    fetchPermissions();
  }, [user, isLoading, isLocalDev]);

  useEffect(() => {
    fetchUserInfo();
  }, [fetchUserInfo]);

  // Permission helper functions
  const canAccessIndex = (indexId: string) => {
    if (!permissions) return false;
    const accessible = permissions.accessible_indexes;
    return accessible === "*" || (Array.isArray(accessible) && accessible.includes(indexId));
  };

  const hasTabAccess = (tabName: string) => {
    if (!permissions) return false;
    return permissions.available_tabs.includes(tabName);
  };

  const canDeleteDocument = (indexId: string) => {
    if (!permissions) return false;
    // Must have delete permission AND access to the index
    return permissions.can_delete_documents && canAccessIndex(indexId);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading: isLoading || permissionsLoading,
        isLocalDev,
        logout,
        refreshUser,

        // Permission-related values
        permissions,
        userRole,
        isAdmin: userRole === "admin",
        isUser: userRole === "user",
        canCreateIndex: permissions?.can_create_index ?? false,
        canDeleteIndex: permissions?.can_delete_index ?? false,
        canUploadDocuments: permissions?.can_upload_documents ?? false,
        canDeleteDocument,
        canAccessIndex,
        hasTabAccess,
        accessibleIndexes: permissions?.accessible_indexes ?? [],
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