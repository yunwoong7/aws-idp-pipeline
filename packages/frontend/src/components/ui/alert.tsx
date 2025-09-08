import * as React from "react"
import { CheckCircle, AlertCircle, Info, AlertTriangle } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

// Alert 다이얼로그의 타입 정의
type AlertType = 'success' | 'error' | 'warning' | 'info'

interface AlertProps {
  isOpen: boolean;
  onClose: () => void;
  type: AlertType;
  title: string;
  message: string;
  confirmText?: string;
}

const getAlertIcon = (type: AlertType) => {
  switch (type) {
    case 'success':
      return <CheckCircle className="h-5 w-5 text-green-500" />
    case 'error':
      return <AlertCircle className="h-5 w-5 text-red-500" />
    case 'warning':
      return <AlertTriangle className="h-5 w-5 text-amber-500" />
    case 'info':
      return <Info className="h-5 w-5 text-blue-500" />
    default:
      return null
  }
}

const getAlertTitle = (type: AlertType) => {
  switch (type) {
    case 'success':
      return 'Success'
    case 'error':
      return 'Error'
    case 'warning':
      return 'Warning'
    case 'info':
      return 'Information'
    default:
      return ''
  }
}

// 팝업 Alert 다이얼로그 컴포넌트
function Alert({
  isOpen,
  onClose,
  type,
  title,
  message,
  confirmText = 'OK'
}: AlertProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {getAlertIcon(type)}
            {title || getAlertTitle(type)}
          </DialogTitle>
          <DialogDescription className="text-left">
            {message}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button onClick={onClose} className="w-full sm:w-auto">
            {confirmText}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Alert Hook - 상태 관리와 함께 사용하기 쉽게
interface AlertState {
  isOpen: boolean;
  type: AlertType;
  title: string;
  message: string;
}

function useAlert() {
  const [alertState, setAlertState] = React.useState<AlertState | null>(null);

  const showAlert = (type: AlertType, title: string, message: string) => {
    setAlertState({ isOpen: true, type, title, message });
  };

  const hideAlert = () => {
    setAlertState(null);
  };

  const AlertComponent = alertState ? (
    <Alert
      isOpen={alertState.isOpen}
      onClose={hideAlert}
      type={alertState.type}
      title={alertState.title}
      message={alertState.message}
    />
  ) : null;

  return {
    showAlert,
    hideAlert,
    AlertComponent,
    isAlertOpen: alertState?.isOpen || false,
    // 편의 메소드들
    showSuccess: (title: string, message: string) => showAlert('success', title, message),
    showError: (title: string, message: string) => showAlert('error', title, message),
    showWarning: (title: string, message: string) => showAlert('warning', title, message),
    showInfo: (title: string, message: string) => showAlert('info', title, message),
  };
}

export { Alert, useAlert, type AlertType }
