"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter, usePathname } from "next/navigation";
import { Home, Bot, Settings, Layers, ImageIcon, LogOut, User, Shield } from "lucide-react";
import { useBranding } from "@/contexts/branding-context";
import { useAuth } from "@/contexts/auth-context";
import { useAlert } from "@/components/ui/alert";
import {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarSeparator,
  SidebarRail,
  SidebarFooter,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";

interface BrandingLogoProps {
  logoUrl: string | null;
  companyName: string;
}

function BrandingLogo({ logoUrl, companyName }: BrandingLogoProps) {
  const [imageError, setImageError] = useState(false);
  
  // console.log('🖼️ BrandingLogo render:', { logoUrl, companyName, imageError });
  
  if (!logoUrl || imageError) {
    return (
      <div className="h-12 w-12 bg-gray-700 rounded-lg flex items-center justify-center">
        <ImageIcon className="h-7 w-7 text-gray-400" />
      </div>
    );
  }
  
  return (
    <Image
      src={logoUrl}
      alt={companyName}
      width={48}
      height={48}
      unoptimized
      className="h-12 w-12 object-contain"
      onError={() => {
        console.log('🚫 Image load error:', logoUrl);
        setImageError(true);
      }}
      onLoadingComplete={() => {
        console.log('✅ Image loaded successfully:', logoUrl);
      }}
    />
  );
}

export function AppSidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { settings, loading } = useBranding();
  const { user, isLoading: authLoading, isLocalDev, logout, isAdmin, hasTabAccess } = useAuth();
  const { showInfo, AlertComponent } = useAlert();

  console.log('📋 AppSidebar branding data:', { settings, loading });
  console.log('👤 AppSidebar auth data:', { user, authLoading, isLocalDev });

  const handleLogout = () => {
    console.log('🚪 Logout button clicked');
    logout();
  };

  const navigationItems = [
    {
      label: "Home",
      icon: Home,
      href: "/studio",
      isActive: pathname === "/" || pathname === "/studio",
    },
    // Indexes menu - show if user has any tab access
    ...((hasTabAccess('documents') || hasTabAccess('analysis') || hasTabAccess('search') || hasTabAccess('verification'))
      ? [
          {
            label: "Indexes",
            icon: Layers,
            href: "/indexes",
            isActive: pathname === "/indexes",
          },
        ]
      : []),
    ...(isAdmin
      ? [
          {
            label: "Users",
            icon: Shield,
            href: "/users",
            isActive: pathname === "/users",
          },
          {
            label: "Settings",
            icon: Settings,
            href: "/settings",
            isActive: pathname === "/settings",
          },
        ]
      : []),
  ];

  return (
    <Sidebar collapsible="offcanvas" className="border-r border-white/10 bg-black text-white">
      <SidebarRail />
      <SidebarHeader className="pt-4">
        {/* Company Branding Section */}
        <div className="px-3 mb-6">
          <div className="flex items-center space-x-3">
            <BrandingLogo 
              logoUrl={loading ? null : (settings.logoUrl || null)}
              companyName={settings.companyName || 'AWS IDP'}
            />
            <div className="flex-1 min-w-0">
              <h2 className="text-base font-semibold text-white whitespace-pre-line break-words line-clamp-2 leading-tight">
                {loading ? 'Loading...' : (settings.companyName || 'AWS IDP')}
              </h2>
              {!loading && settings.version && (
                <p className="text-[10px] text-gray-400 mt-0.5">v{settings.version}</p>
              )}
            </div>
          </div>
        </div>
        
        <SidebarSeparator />
        
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigationItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton 
                    onClick={() => router.push(item.href)} 
                    tooltip={item.label}
                    isActive={item.isActive}
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarHeader>
      <SidebarContent />
      
      <SidebarFooter className="p-4 border-t border-white/10">
        {authLoading ? (
          <div className="flex items-center space-x-3">
            <div className="h-8 w-8 bg-gray-700 rounded-full animate-pulse"></div>
            <div className="flex-1">
              <div className="h-3 bg-gray-700 rounded animate-pulse mb-1"></div>
              <div className="h-2 bg-gray-700 rounded animate-pulse w-3/4"></div>
            </div>
          </div>
        ) : user ? (
          <div className="space-y-3">
            {/* User Info */}
            <div className="flex items-center space-x-3">
              <div className="h-8 w-8 bg-blue-600 rounded-full flex items-center justify-center">
                <User className="h-4 w-4 text-white" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">
                  {user.name || user.email.split('@')[0]}
                </p>
                <p className="text-xs text-gray-400 truncate">
                  {user.email}
                </p>
                {isLocalDev && (
                  <p className="text-xs text-yellow-400">
                    Local Dev Mode
                  </p>
                )}
              </div>
            </div>
            
            {/* Logout Button */}
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="w-full justify-start text-gray-300 hover:text-white hover:bg-white/10"
            >
              <LogOut className="h-4 w-4 mr-2" />
              Logout
            </Button>
          </div>
        ) : (
          <div className="text-center text-gray-400">
            <p className="text-sm">Login information could not be loaded</p>
          </div>
        )}
      </SidebarFooter>
      {AlertComponent}
    </Sidebar>
  );
}