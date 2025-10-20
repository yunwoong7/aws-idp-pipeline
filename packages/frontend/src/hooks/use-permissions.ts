import { useAuth } from '@/contexts/auth-context';

export interface UserPermissions {
  can_create_index: boolean;
  can_delete_index: boolean;
  can_upload_documents: boolean;
  accessible_indexes: string[] | "*";
  available_tabs: string[];
}

export interface UserWithPermissions {
  user_id: string;
  email: string;
  name?: string;
  role: "admin" | "user";
  permissions: UserPermissions;
  status: string;
  created_at?: string;
  updated_at?: string;
  last_login_at?: string;
}

/**
 * usePermissions hook - wrapper for useAuth
 * Returns all permission-related data from AuthContext
 */
export function usePermissions() {
  const auth = useAuth();

  return {
    permissions: auth.permissions,
    userRole: auth.userRole,
    loading: auth.isLoading,
    error: null,

    // Role checks
    isAdmin: auth.isAdmin,
    isUser: auth.isUser,

    // Permission checks
    canCreateIndex: auth.canCreateIndex,
    canDeleteIndex: auth.canDeleteIndex,
    canUploadDocuments: auth.canUploadDocuments,

    // Helper functions
    canAccessIndex: auth.canAccessIndex,
    hasTabAccess: auth.hasTabAccess,

    // Get accessible indexes
    accessibleIndexes: auth.accessibleIndexes,
  };
}
