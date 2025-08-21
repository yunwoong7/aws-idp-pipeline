"use client";

import { Hero } from "@/components/ui/hero";
import { UploadNotificationContainer } from "@/components/ui/upload-notification";
import { useUploadNotifications } from "@/hooks/use-upload-notifications";

export default function HomePage() {
  // Manage upload notifications
  const { notifications, removeNotification } = useUploadNotifications({
    maxNotifications: 3,
    autoRemove: true,
    autoRemoveDelay: 6000
  });

  return (
    <div className="relative min-h-screen">
      <Hero />

      {/* Upload complete notification */}
      <UploadNotificationContainer
        notifications={notifications}
        onDismiss={removeNotification}
        position="top-center"
        maxNotifications={3}
      />
    </div>
  );
}
