"use client";

import { useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Home, Bot, Settings, Layers, ImageIcon } from "lucide-react";
import { useBranding } from "@/contexts/branding-context";
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
} from "@/components/ui/sidebar";

interface BrandingLogoProps {
  logoUrl: string | null;
  companyName: string;
}

function BrandingLogo({ logoUrl, companyName }: BrandingLogoProps) {
  const [imageError, setImageError] = useState(false);
  
  console.log('🖼️ BrandingLogo render:', { logoUrl, companyName, imageError });
  
  if (!logoUrl || imageError) {
    return (
      <div className="h-12 w-12 bg-gray-700 rounded-lg flex items-center justify-center">
        <ImageIcon className="h-7 w-7 text-gray-400" />
      </div>
    );
  }
  
  return (
    <img
      src={logoUrl}
      alt={companyName}
      className="h-12 w-12 object-contain"
      onError={(e) => {
        console.log('🚫 Image load error:', logoUrl);
        setImageError(true);
      }}
      onLoad={() => {
        console.log('✅ Image loaded successfully:', logoUrl);
      }}
    />
  );
}

export function AppSidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const { settings, loading } = useBranding();
  
  console.log('📋 AppSidebar branding data:', { settings, loading });

  const navigationItems = [
    {
      label: "Home",
      icon: Home,
      href: "/studio",
      isActive: pathname === "/" || pathname === "/studio",
    },
    {
      label: "Indexes",
      icon: Layers,
      href: "/indexes",
      isActive: pathname === "/indexes",
    },
    {
      label: "Settings",
      icon: Settings,
      href: "/settings",
      isActive: pathname === "/settings",
    },
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
              <h2 className="text-base font-semibold text-white truncate">
                {loading ? 'Loading...' : (settings.companyName || 'AWS IDP')}
              </h2>
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
    </Sidebar>
  );
}