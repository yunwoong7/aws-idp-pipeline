"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { UserData, UserPermissions } from "@/lib/api";
import { indicesApi } from "@/lib/api";
import { Shield, ShieldCheck, Settings, Layers, FileText, Search, CheckCircle2, Loader2 } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface PermissionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: UserData;
  onSave: (userId: string, permissions: UserPermissions, role: string) => Promise<void>;
}

const AVAILABLE_TABS = [
  { id: "documents", label: "Documents", icon: FileText },
  { id: "analysis", label: "Analysis", icon: Settings },
  { id: "search", label: "Search", icon: Search },
  { id: "verification", label: "Verification", icon: CheckCircle2 },
];

export function PermissionDialog({ open, onOpenChange, user, onSave }: PermissionDialogProps) {
  const [role, setRole] = useState<string>(user.role || "user");
  const [selectedTabs, setSelectedTabs] = useState<string[]>(user.permissions?.available_tabs || ["search"]);
  const [accessibleIndexes, setAccessibleIndexes] = useState<string[]>(
    user.permissions?.accessible_indexes === "*"
      ? ["*"]
      : (user.permissions?.accessible_indexes || [])
  );
  const [canCreateIndex, setCanCreateIndex] = useState(user.permissions?.can_create_index || false);
  const [canDeleteIndex, setCanDeleteIndex] = useState(user.permissions?.can_delete_index || false);
  const [canUploadDocuments, setCanUploadDocuments] = useState(user.permissions?.can_upload_documents || false);
  const [canDeleteDocuments, setCanDeleteDocuments] = useState(user.permissions?.can_delete_documents || false);

  const [availableIndices, setAvailableIndices] = useState<Array<{ index_id: string; index_name: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load available indices
  useEffect(() => {
    if (open) {
      loadIndices();
    }
  }, [open]);

  const loadIndices = async () => {
    try {
      setLoading(true);
      const indices = await indicesApi.list();
      const mapped = indices.map((i: any) => ({
        index_id: i.index_id,
        index_name: i.index_id
      }));
      setAvailableIndices(mapped);
    } catch (error) {
      console.error("Failed to load indices:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleTabToggle = (tabId: string) => {
    setSelectedTabs(prev =>
      prev.includes(tabId)
        ? prev.filter(t => t !== tabId)
        : [...prev, tabId]
    );
  };

  const handleIndexToggle = (indexId: string) => {
    if (indexId === "*") {
      setAccessibleIndexes(prev => prev.includes("*") ? [] : ["*"]);
    } else {
      setAccessibleIndexes(prev => {
        const filtered = prev.filter(id => id !== "*");
        return filtered.includes(indexId)
          ? filtered.filter(id => id !== indexId)
          : [...filtered, indexId];
      });
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);

      const permissions: UserPermissions = {
        can_create_index: canCreateIndex,
        can_delete_index: canDeleteIndex,
        can_upload_documents: canUploadDocuments,
        can_delete_documents: canDeleteDocuments,
        accessible_indexes: accessibleIndexes.includes("*") ? "*" : accessibleIndexes,
        available_tabs: selectedTabs,
      };

      await onSave(user.user_id, permissions, role);
      onOpenChange(false);
    } catch (error) {
      console.error("Failed to save permissions:", error);
      alert("Failed to save permissions");
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    if (!saving) {
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="!w-[65vw] !max-w-none !sm:max-w-none max-h-[85vh] p-0 border-0 bg-transparent overflow-hidden">
        <DialogHeader className="sr-only">
          <DialogTitle>Edit Permissions</DialogTitle>
          <DialogDescription>Manage user permissions and access control</DialogDescription>
        </DialogHeader>

        <div className="flex h-[80vh]">
          {/* Left panel - User info & visual */}
          <div className="w-1/3 bg-gradient-to-br from-purple-900/95 via-violet-900/95 to-indigo-900/95 backdrop-blur-xl p-8 flex flex-col justify-between relative overflow-hidden">
            {/* Background decorations */}
            <div className="absolute inset-0 opacity-10">
              <div className="absolute top-10 left-10 w-32 h-32 border border-purple-400/30 rounded-full"></div>
              <div className="absolute bottom-20 right-10 w-24 h-24 border border-violet-400/30 rounded-full"></div>
              <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-40 h-40 border border-indigo-400/20 rounded-full"></div>
            </div>

            {/* Content */}
            <div className="relative z-10 space-y-6">
              <div className="w-16 h-16 rounded-2xl bg-purple-500/20 flex items-center justify-center mb-6 backdrop-blur-sm border border-purple-400/20">
                <Shield className="h-8 w-8 text-purple-300" />
              </div>

              <div>
                <h2 className="text-3xl font-bold text-white mb-3">Edit Permissions</h2>
                <p className="text-purple-200 text-lg leading-relaxed">
                  Configure access rights and capabilities for this user
                </p>
              </div>

              {/* User info */}
              <div className="mt-8 p-4 bg-white/10 backdrop-blur-sm rounded-xl border border-white/20">
                <div className="space-y-2">
                  <div className="text-sm text-purple-200">User</div>
                  <div className="text-white font-semibold text-lg">{user.email}</div>
                  {user.name && (
                    <div className="text-purple-300 text-sm">{user.name}</div>
                  )}
                </div>
              </div>
            </div>

            {/* Footer info */}
            <div className="relative z-10 text-purple-300 text-sm">
              <p className="opacity-80">
                Admin users have full access to all features
              </p>
            </div>
          </div>

          {/* Right panel - Form */}
          <div className="flex-1 bg-gradient-to-br from-gray-900/90 via-slate-900/90 to-gray-800/90 backdrop-blur-xl flex flex-col">
            <div className="flex-1 overflow-y-auto p-8">
              <div className="max-w-2xl space-y-8 pb-4">
                {/* Role Selection */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-3">
                    <ShieldCheck className="w-5 h-5 text-purple-400" />
                    <Label className="text-lg font-semibold text-white">Role</Label>
                  </div>
                  <RadioGroup value={role} onValueChange={setRole} className="space-y-3">
                    <div className="flex items-center space-x-3 p-4 rounded-lg bg-white/5 border border-purple-500/20 hover:bg-white/10 transition-colors cursor-pointer">
                      <RadioGroupItem value="admin" id="role-admin" className="border-purple-400" />
                      <Label htmlFor="role-admin" className="flex-1 font-normal cursor-pointer text-white">
                        <div className="font-semibold">Admin</div>
                        <div className="text-sm text-gray-400">Full access to all features and settings</div>
                      </Label>
                    </div>
                    <div className="flex items-center space-x-3 p-4 rounded-lg bg-white/5 border border-purple-500/20 hover:bg-white/10 transition-colors cursor-pointer">
                      <RadioGroupItem value="user" id="role-user" className="border-purple-400" />
                      <Label htmlFor="role-user" className="flex-1 font-normal cursor-pointer text-white">
                        <div className="font-semibold">User</div>
                        <div className="text-sm text-gray-400">Custom permissions based on configuration below</div>
                      </Label>
                    </div>
                  </RadioGroup>
                </div>

                {/* Available Features */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Settings className="w-5 h-5 text-purple-400" />
                    <Label className="text-lg font-semibold text-white">Available Features</Label>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    {AVAILABLE_TABS.map((tab) => {
                      const Icon = tab.icon;
                      return (
                        <div
                          key={tab.id}
                          className={`flex items-center space-x-3 p-4 rounded-lg border transition-all cursor-pointer ${
                            selectedTabs.includes(tab.id)
                              ? "bg-purple-500/20 border-purple-500/50"
                              : "bg-white/5 border-gray-700 hover:bg-white/10"
                          } ${role === "admin" ? "opacity-50 cursor-not-allowed" : ""}`}
                          onClick={() => role !== "admin" && handleTabToggle(tab.id)}
                        >
                          <Checkbox
                            id={`tab-${tab.id}`}
                            checked={selectedTabs.includes(tab.id)}
                            disabled={role === "admin"}
                            className="border-purple-400"
                          />
                          <Label
                            htmlFor={`tab-${tab.id}`}
                            className="flex items-center gap-2 font-normal cursor-pointer text-white flex-1"
                          >
                            <Icon className="w-4 h-4" />
                            {tab.label}
                          </Label>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Accessible Indexes */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-3">
                    <Layers className="w-5 h-5 text-purple-400" />
                    <Label className="text-lg font-semibold text-white">Accessible Indexes</Label>
                  </div>
                  <div className="space-y-3">
                    {/* All Indexes option */}
                    <div
                      className={`flex items-center space-x-3 p-4 rounded-lg border transition-all cursor-pointer ${
                        accessibleIndexes.includes("*")
                          ? "bg-gradient-to-r from-purple-500/30 to-violet-500/30 border-purple-500/50"
                          : "bg-white/5 border-gray-700 hover:bg-white/10"
                      } ${role === "admin" ? "opacity-50 cursor-not-allowed" : ""}`}
                      onClick={() => role !== "admin" && handleIndexToggle("*")}
                    >
                      <Checkbox
                        id="index-all"
                        checked={accessibleIndexes.includes("*")}
                        disabled={role === "admin"}
                        className="border-purple-400"
                      />
                      <Label htmlFor="index-all" className="font-semibold cursor-pointer text-white flex-1">
                        All Indexes (*)
                      </Label>
                    </div>

                    {/* Individual indexes */}
                    {loading ? (
                      <div className="text-sm text-gray-400 flex items-center gap-2 p-4">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Loading indices...
                      </div>
                    ) : (
                      <div className="space-y-2 max-h-48 overflow-y-auto pr-2">
                        {availableIndices.map((index) => (
                          <div
                            key={index.index_id}
                            className={`flex items-center space-x-3 p-3 rounded-lg border transition-all cursor-pointer ${
                              accessibleIndexes.includes(index.index_id) || accessibleIndexes.includes("*")
                                ? "bg-purple-500/10 border-purple-500/30"
                                : "bg-white/5 border-gray-700 hover:bg-white/10"
                            } ${role === "admin" || accessibleIndexes.includes("*") ? "opacity-50 cursor-not-allowed" : ""}`}
                            onClick={() => {
                              if (role !== "admin" && !accessibleIndexes.includes("*")) {
                                handleIndexToggle(index.index_id);
                              }
                            }}
                          >
                            <Checkbox
                              id={`index-${index.index_id}`}
                              checked={accessibleIndexes.includes(index.index_id) || accessibleIndexes.includes("*")}
                              disabled={role === "admin" || accessibleIndexes.includes("*")}
                              className="border-purple-400"
                            />
                            <Label
                              htmlFor={`index-${index.index_id}`}
                              className="font-normal cursor-pointer text-white flex-1"
                            >
                              {index.index_name}
                            </Label>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Action Permissions */}
                <div className="space-y-4">
                  <div className="flex items-center gap-2 mb-3">
                    <ShieldCheck className="w-5 h-5 text-purple-400" />
                    <Label className="text-lg font-semibold text-white">Action Permissions</Label>
                  </div>
                  <div className="space-y-3">
                    {[
                      { id: "can_create_index", label: "Create Index", checked: canCreateIndex, onChange: setCanCreateIndex },
                      { id: "can_delete_index", label: "Delete Index", checked: canDeleteIndex, onChange: setCanDeleteIndex },
                      { id: "can_upload_documents", label: "Upload Documents", checked: canUploadDocuments, onChange: setCanUploadDocuments },
                      { id: "can_delete_documents", label: "Delete Documents", checked: canDeleteDocuments, onChange: setCanDeleteDocuments },
                    ].map((perm) => (
                      <div
                        key={perm.id}
                        className={`flex items-center space-x-3 p-4 rounded-lg border transition-all cursor-pointer ${
                          perm.checked
                            ? "bg-purple-500/10 border-purple-500/30"
                            : "bg-white/5 border-gray-700 hover:bg-white/10"
                        } ${role === "admin" ? "opacity-50 cursor-not-allowed" : ""}`}
                        onClick={() => role !== "admin" && perm.onChange(!perm.checked)}
                      >
                        <Checkbox
                          id={`perm-${perm.id}`}
                          checked={perm.checked}
                          onCheckedChange={(checked) => perm.onChange(!!checked)}
                          disabled={role === "admin"}
                          className="border-purple-400"
                        />
                        <Label htmlFor={`perm-${perm.id}`} className="font-normal cursor-pointer text-white flex-1">
                          {perm.label}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Footer buttons */}
            <div className="flex-shrink-0 border-t border-gray-700/50 p-6 bg-gray-900/50">
              <div className="flex justify-end gap-3">
                <Button
                  variant="outline"
                  onClick={handleClose}
                  disabled={saving}
                  className="border-gray-600 hover:bg-gray-700"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  className="bg-gradient-to-r from-purple-600 to-violet-600 hover:from-purple-700 hover:to-violet-700"
                >
                  {saving ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Save Changes"
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
