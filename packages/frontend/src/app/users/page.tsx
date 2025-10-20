"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/common/app-sidebar";
import { useAuth } from "@/contexts/auth-context";
import { Shield, UserCog, Lock, Settings } from "lucide-react";
import { usersApi, UserData, UserPermissions } from "@/lib/api";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { ChatBackground } from "@/components/ui/chat-background";
import { PermissionDialog } from "./permission-dialog";

export default function UsersPage() {
  const router = useRouter();
  const { isAdmin, isLoading } = useAuth();
  const [users, setUsers] = useState<UserData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedUser, setSelectedUser] = useState<UserData | null>(null);
  const [permissionDialogOpen, setPermissionDialogOpen] = useState(false);

  // Check admin permission
  useEffect(() => {
    if (!isLoading && !isAdmin) {
      router.push("/");
    }
  }, [isAdmin, isLoading, router]);

  // Fetch users
  useEffect(() => {
    const fetchUsers = async () => {
      try {
        setLoading(true);
        const data = await usersApi.listUsers();
        setUsers(data);
      } catch (err) {
        console.error("Failed to fetch users:", err);
        setError("Failed to fetch users");
      } finally {
        setLoading(false);
      }
    };

    if (isAdmin) {
      fetchUsers();
    }
  }, [isAdmin]);

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      const user = users.find((u) => u.user_id === userId);
      if (!user) return;

      // Update role with current permissions
      await usersApi.updatePermissions(userId, user.permissions, newRole);
      setUsers((prev) =>
        prev.map((u) => (u.user_id === userId ? { ...u, role: newRole as "admin" | "user" } : u))
      );
    } catch (err) {
      console.error("Failed to update role:", err);
      setError("Failed to update role");
    }
  };

  const handleStatusChange = async (userId: string, newStatus: string) => {
    try {
      await usersApi.updateStatus(userId, newStatus);
      setUsers((prev) =>
        prev.map((u) => (u.user_id === userId ? { ...u, status: newStatus } : u))
      );
    } catch (err) {
      console.error("Failed to update status:", err);
      setError("Failed to update status");
    }
  };

  const handleEditPermissions = (user: UserData) => {
    setSelectedUser(user);
    setPermissionDialogOpen(true);
  };

  const handleSavePermissions = async (
    userId: string,
    permissions: UserPermissions,
    role: string
  ) => {
    try {
      await usersApi.updatePermissions(userId, permissions, role);
      // Reload users
      const data = await usersApi.listUsers();
      setUsers(data);
    } catch (err) {
      console.error("Failed to update permissions:", err);
      throw err;
    }
  };

  if (isLoading || loading) {
    return (
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <div className="flex h-screen items-center justify-center">
            <div className="text-muted-foreground">Loading...</div>
          </div>
        </SidebarInset>
      </SidebarProvider>
    );
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <ChatBackground />

        <div className="relative z-10">
          {/* Header */}
          <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-2 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-4">
            <SidebarTrigger className="-ml-1" />
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary" />
              <h1 className="text-xl font-semibold">User Management</h1>
            </div>
          </header>

          {/* Content */}
          <main className="flex flex-1 flex-col gap-4 p-6">
            {error && (
              <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="rounded-xl border border-white/10 bg-gradient-to-br from-gray-900/50 to-slate-900/50 backdrop-blur-sm overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="border-b border-white/10 hover:bg-transparent">
                    <TableHead className="text-purple-300 font-semibold">Email</TableHead>
                    <TableHead className="text-purple-300 font-semibold">Name</TableHead>
                    <TableHead className="text-purple-300 font-semibold">Role</TableHead>
                    <TableHead className="text-purple-300 font-semibold">Permissions</TableHead>
                    <TableHead className="text-purple-300 font-semibold">Last Login</TableHead>
                    <TableHead className="text-purple-300 font-semibold">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((user) => (
                    <TableRow
                      key={user.user_id}
                      className="border-b border-white/5 hover:bg-white/5 transition-colors"
                    >
                      <TableCell className="font-medium text-white">{user.email}</TableCell>
                      <TableCell className="text-gray-300">{user.name || "-"}</TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={`${
                            user.role === "admin"
                              ? "border-purple-500/50 bg-purple-500/10 text-purple-300"
                              : "border-cyan-500/50 bg-cyan-500/10 text-cyan-300"
                          }`}
                        >
                          {user.role === "admin" ? "Admin" : "User"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1.5">
                          <Badge
                            variant="outline"
                            className="text-xs border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                          >
                            {user.permissions.available_tabs?.length || 0} features
                          </Badge>
                          <Badge
                            variant="outline"
                            className="text-xs border-blue-500/30 bg-blue-500/10 text-blue-300"
                          >
                            {user.permissions.accessible_indexes === "*"
                              ? "All indexes"
                              : `${Array.isArray(user.permissions.accessible_indexes) ? user.permissions.accessible_indexes.length : 0} indexes`}
                          </Badge>
                        </div>
                      </TableCell>
                      <TableCell className="text-sm text-gray-400">
                        {user.last_login_at
                          ? new Date(user.last_login_at).toLocaleString()
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleEditPermissions(user)}
                          className="h-8 border border-purple-500/30 bg-purple-500/10 text-purple-300 hover:bg-purple-500/20 hover:border-purple-400/50 transition-all"
                        >
                          <Settings className="h-3.5 w-3.5 mr-1.5" />
                          Edit
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </main>
        </div>
      </SidebarInset>

      {/* Permission Dialog */}
      {selectedUser && (
        <PermissionDialog
          open={permissionDialogOpen}
          onOpenChange={setPermissionDialogOpen}
          user={selectedUser}
          onSave={handleSavePermissions}
        />
      )}
    </SidebarProvider>
  );
}
