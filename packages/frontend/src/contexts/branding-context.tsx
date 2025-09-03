'use client';

import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { brandingApi, BrandingSettings } from '@/lib/api';

interface BrandingContextType {
  settings: BrandingSettings;
  loading: boolean;
  error: string | null;
  refreshSettings: () => Promise<void>;
  initializeSettings: () => Promise<void>;
}

const BrandingContext = createContext<BrandingContextType | undefined>(undefined);

interface BrandingProviderProps {
  children: ReactNode;
}

export function BrandingProvider({ children }: BrandingProviderProps) {
  const [settings, setSettings] = useState<BrandingSettings>({
    companyName: 'AWS IDP',
    logoUrl: '/default_logo.png',
    description: 'Transform Documents into\nActionable Insights',
    version: undefined,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  const fetchSettings = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const result = await brandingApi.getSettings();
      console.log('🎨 Branding settings loaded:', result);
      // Cache-bust logo to reflect file updates immediately in UI
      const cacheBuster = Date.now();
      const effectiveLogoUrl = result.logoUrl
        ? `${result.logoUrl}${result.logoUrl.includes('?') ? '&' : '?'}v=${cacheBuster}`
        : '/default_logo.png';
      setSettings({
        companyName: result.companyName || 'AWS IDP',
        logoUrl: effectiveLogoUrl,
        description: result.description || 'Transform Documents into\nActionable Insights',
        version: result.version,
      });
      setInitialized(true);
    } catch (err) {
      console.error('브랜딩 설정 로드 실패:', err);
      setError(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.');
      // 오류 발생 시 기본값 사용
      const cacheBuster = Date.now();
      setSettings({
        companyName: 'AWS IDP',
        logoUrl: `/default_logo.png?v=${cacheBuster}`,
        description: 'Transform Documents into\nActionable Insights',
        version: undefined,
      });
      setInitialized(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshSettings = useCallback(async () => {
    await fetchSettings();
  }, [fetchSettings]);

  const initializeSettings = useCallback(async () => {
    if (!initialized) {
      await fetchSettings();
    }
  }, [initialized, fetchSettings]);

  // 컴포넌트 마운트 시 자동 초기화 (한 번만)
  useEffect(() => {
    let mounted = true;
    if (!initialized && mounted) {
      fetchSettings();
    }
    return () => {
      mounted = false;
    };
  }, [initialized, fetchSettings]);

  const value: BrandingContextType = {
    settings,
    loading,
    error,
    refreshSettings,
    initializeSettings,
  };

  return (
    <BrandingContext.Provider value={value}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBranding() {
  const context = useContext(BrandingContext);
  if (context === undefined) {
    throw new Error('useBranding must be used within a BrandingProvider');
  }
  return context;
}