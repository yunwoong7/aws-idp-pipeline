'use client';

import React, { createContext, useContext, ReactNode } from 'react';

interface ApiConfig {
  apiBaseUrl: string;
  ecsBackendUrl: string;
}

const ApiConfigContext = createContext<ApiConfig>({
  apiBaseUrl: '',
  ecsBackendUrl: '',
});

interface ApiConfigProviderProps {
  children: ReactNode;
  apiBaseUrl: string;
  ecsBackendUrl: string;
}

export function ApiConfigProvider({ children, apiBaseUrl, ecsBackendUrl }: ApiConfigProviderProps) {
  const value = {
    apiBaseUrl,
    ecsBackendUrl,
  };

  return (
    <ApiConfigContext.Provider value={value}>
      {children}
    </ApiConfigContext.Provider>
  );
}

export function useApiConfig() {
  return useContext(ApiConfigContext);
}