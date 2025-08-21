import { create } from 'zustand';

interface RightPanelState {
    isOpen: boolean;
    panelType: 'documents' | 'document-management' | null;
    projectId: string | null;
    openDocumentPanel: (projectId: string) => void;
    openDocumentManagementPanel: (projectId: string) => void;
    closePanel: () => void;
    togglePanel: (panelType: 'documents' | 'document-management', projectId: string) => void;
}

export const useRightPanelStore = create<RightPanelState>((set, get) => ({
    isOpen: false,
    panelType: null,
    projectId: null,
    
    openDocumentPanel: (projectId: string) => {
        set({
            isOpen: true,
            panelType: 'documents',
            projectId: projectId
        });
    },
    
    openDocumentManagementPanel: (projectId: string) => {
        set({
            isOpen: true,
            panelType: 'document-management',
            projectId: projectId
        });
    },
    
    closePanel: () => {
        set({
            isOpen: false,
            panelType: null,
            projectId: null
        });
    },
    
    togglePanel: (panelType: 'documents' | 'document-management', projectId: string) => {
        const state = get();
        if (state.isOpen && state.panelType === panelType && state.projectId === projectId) {
            set({
                isOpen: false,
                panelType: null,
                projectId: null
            });
        } else {
            set({
                isOpen: true,
                panelType: panelType,
                projectId: projectId
            });
        }
    }
}));