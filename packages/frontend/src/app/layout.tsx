import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { WebSocketProvider } from "@/contexts/websocket-context";
import { BrandingProvider } from "@/contexts/branding-context";
import { AuthProvider } from "@/contexts/auth-context";
import { Toaster } from "@/components/ui/toaster";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI-powered IDP",
  description: "Transform unstructured data into actionable insights with our advanced AI-powered Intelligent Document Processing solution. Analyze documents, videos, audio files, and images with unprecedented accuracy and speed.",
  keywords: ["IDP", "Intelligent Document Processing", "AI", "Data Extraction", "Document Analysis", "Video Analysis", "Audio Analysis", "Image Analysis"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        <BrandingProvider>
          <AuthProvider>
            <WebSocketProvider showToastOnError={true} showToastOnReconnect={true}>
              {children}
              <Toaster />
            </WebSocketProvider>
          </AuthProvider>
        </BrandingProvider>
      </body>
    </html>
  );
}
