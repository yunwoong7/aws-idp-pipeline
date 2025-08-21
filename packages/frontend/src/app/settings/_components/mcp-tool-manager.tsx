import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Plus, Trash2, RefreshCw, Server, Check, Plug, Copy, ChevronDown, ChevronUp, Zap, ShieldAlert, FileJson, Search, Edit, X, AlertCircle, CheckCircle, AlertTriangle } from 'lucide-react';

interface MCPToolManagerProps {
  onSettingsChanged?: () => void;
}

interface MCPTool {
  name: string;
  description?: string;
  status?: 'ready' | 'error' | 'unknown';
}

interface ServerConfig {
  command?: string;
  args?: string[];
  [key: string]: unknown;
}

interface MCPServer {
  name: string;
  config: ServerConfig;
  status?: 'online' | 'offline' | 'unknown';
  tools?: MCPTool[];
  expanded?: boolean;
}

interface MCPServerInfo {
  name: string;
  config: ServerConfig;
  status: 'online' | 'offline' | 'unknown';
  tools: MCPTool[];
}

interface RestartResult {
  success: boolean;
  message: string;
}

interface ServerActionResponse {
  message: string;
  restart?: RestartResult;
}

const ServerStatusIcon = ({ status }: { status: 'online' | 'offline' | 'unknown' }) => {
  let bgColor = 'bg-gray-800/50';
  let textColor = 'text-gray-400';
  
  if (status === 'online') {
    bgColor = 'bg-emerald-900/30';
    textColor = 'text-emerald-400';
  } else if (status === 'offline') {
    bgColor = 'bg-red-900/30';
    textColor = 'text-red-400';
  }
  
  return (
    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${bgColor} ${textColor} relative`}>
      <Plug className="h-5 w-5" />
      {status === 'online' && (
        <span className="absolute w-full h-full rounded-lg bg-emerald-400/20 animate-ping" />
      )}
    </div>
  );
};

const ToolsList = ({ tools, serverName }: { tools: MCPTool[], serverName: string }) => {
  const [searchTerm, setSearchTerm] = useState('');
  
  const filteredTools = searchTerm.trim()
    ? tools.filter(tool => 
        tool.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
        (tool.description || '').toLowerCase().includes(searchTerm.toLowerCase())
      )
    : tools;
    
  const getDisplayName = (name: string) => {
    if (name.startsWith(`${serverName}:`)) {
      return name.substring(serverName.length + 1);
    }
    return name;
  };
  
  return (
    <div className="space-y-3">
      {tools.length > 6 && (
        <div className="relative mb-4">
          <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
            <Search className="w-4 h-4 text-slate-500" />
          </div>
          <input
            type="search"
            className="block w-full p-2 pl-10 text-sm bg-slate-800/50 border border-slate-600 rounded-lg focus:ring-blue-500 focus:border-blue-500 text-slate-300"
            placeholder="Search tools..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      )}
      
      {filteredTools.length === 0 ? (
        <p className="text-slate-500 text-center py-2">No results found</p>
      ) : (
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
          {filteredTools.map((tool, toolIdx) => (
            <li key={toolIdx} className="bg-slate-800/20 p-3 rounded-md flex items-start gap-3 hover:bg-slate-800/30 transition-colors border border-transparent hover:border-slate-700">
              <div className={`w-8 h-8 rounded-md flex items-center justify-center ${
                tool.status === 'ready' 
                  ? 'bg-emerald-900/20 text-emerald-400' 
                  : tool.status === 'error' 
                    ? 'bg-red-900/20 text-red-400'
                    : 'bg-slate-800/30 text-slate-400'
              }`}>
                <Zap className="h-4 w-4" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-slate-300 font-medium flex items-center">
                  {getDisplayName(tool.name)}
                  {tool.status === 'ready' && (
                    <span className="ml-2 w-2 h-2 rounded-full bg-emerald-500"></span>
                  )}
                </p>
                {tool.description && (
                  <p className="text-xs text-slate-500 mt-1 line-clamp-3">
                    {tool.description}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

const ResultNotification = ({ result, onClose }: { result: RestartResult | null, onClose: () => void }) => {
  if (!result) return null;
  
  return (
    <div className={`fixed bottom-6 right-6 max-w-md ${result.success ? 'bg-emerald-900/90' : 'bg-red-900/90'} rounded-lg p-4 shadow-xl border ${result.success ? 'border-emerald-700' : 'border-red-700'} z-50 animate-fade-in`}>
      <div className="flex items-start gap-3">
        {result.success ? (
          <CheckCircle className="h-5 w-5 text-emerald-400 mt-0.5 flex-shrink-0" />
        ) : (
          <AlertCircle className="h-5 w-5 text-red-400 mt-0.5 flex-shrink-0" />
        )}
        <div className="flex-1">
          <p className={`text-sm ${result.success ? 'text-emerald-200' : 'text-red-200'}`}>
            {result.message}
          </p>
        </div>
        <button 
          onClick={onClose}
          className="text-slate-400 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};

const autoFixJsonString = (jsonStr: string): string => {
  if (!jsonStr.trim()) return '';
  
  try {
    JSON.parse(jsonStr);
    return jsonStr;
  } catch (e) {
    let processedStr = jsonStr.trim();
    
    if (processedStr.match(/^"[^"]+"\s*:\s*\{/)) {
      processedStr = `{${processedStr}}`;
      
      try {
        JSON.parse(processedStr);
        return processedStr;
      } catch (innerError) {
        // continue processing
      }
    }
    
    processedStr = processedStr.replace(/,\s*}/g, '}');
    processedStr = processedStr.replace(/,\s*\]/g, ']');
    processedStr = processedStr.replace(/\{([^{}:"']+):/g, '{"$1":');
    processedStr = processedStr.replace(/,\s*([^{}:"']+):/g, ',"$1":');
    
    try {
      JSON.parse(processedStr);
      return processedStr;
    } catch (finalError) {
      return jsonStr;
    }
  }
};

const JsonHelpMessage = ({ jsonString, onFix }: { jsonString: string, onFix: (fixed: string) => void }) => {
  if (!jsonString.trim()) return null;
  
  try {
    JSON.parse(jsonString);
    return null;
  } catch (e) {
    const fixedJson = autoFixJsonString(jsonString);
    const isFixed = fixedJson !== jsonString;
    
    return (
      <div className="mt-2 p-2 bg-blue-950/30 border border-blue-700/50 rounded text-xs text-blue-200">
        <p className="font-medium mb-1">JSON format error detected</p>
        <p>
          {isFixed 
            ? 'Click the below button to automatically fix the JSON format:' 
            : 'The pasted JSON is invalid. Please check the following format:'}
        </p>
        {isFixed && (
          <button 
            onClick={() => onFix(fixedJson)}
            className="mt-2 py-1 inline-flex items-center justify-center whitespace-nowrap text-xs font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-3 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-6 rounded gap-1 px-2 has-[>svg]:px-1.5 bg-transparent border-blue-500/50 text-blue-400 hover:bg-blue-500/20 hover:border-blue-400 hover:text-blue-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <FileJson /> JSON auto fix
          </button>
        )}
        {!isFixed && (
          <pre className="mt-1 p-1 bg-black/30 rounded overflow-x-auto">
            {`{"server name": { server config object }}`}
          </pre>
        )}
      </div>
    );
  }
};

// API URL helper function
const getApiUrl = (path: string) => {
  const baseUrl = process.env.NODE_ENV === 'development' 
    ? 'http://localhost:8000' 
    : '';
  return `${baseUrl}${path}`;
};

const MCPToolManager: React.FC<MCPToolManagerProps> = ({ onSettingsChanged }) => {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [newConfigJSON, setNewConfigJSON] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isCheckingStatus, setIsCheckingStatus] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonMode, setJsonMode] = useState(false);
  const isFetchingRef = useRef(false);
  const validationTimerRef = useRef<NodeJS.Timeout | null>(null);
  
  const [editMode, setEditMode] = useState(false);
  const [editingServer, setEditingServer] = useState<string | null>(null);
  const [editedConfig, setEditedConfig] = useState('');
  const [editedName, setEditedName] = useState('');
  
  const [showAddServerModal, setShowAddServerModal] = useState(false);
  const [restartResult, setRestartResult] = useState<RestartResult | null>(null);
  
  const editConfigRef = useRef<HTMLTextAreaElement>(null);
  const newConfigRef = useRef<HTMLTextAreaElement>(null);

  const handleNewConfigChange = (value: string) => {
    const cursorPosition = newConfigRef.current?.selectionStart || 0;
    setNewConfigJSON(value);
    setError(null);
    
    requestAnimationFrame(() => {
      if (newConfigRef.current) {
        newConfigRef.current.focus();
        newConfigRef.current.selectionStart = cursorPosition;
        newConfigRef.current.selectionEnd = cursorPosition;
      }
    });
  };

  const fetchTools = useCallback(async () => {
    if (isFetchingRef.current) {
      console.log('API call already in progress. Prevent duplicate calls');
      return;
    }
    
    isFetchingRef.current = true;
    setIsLoading(true);
    setError(null);
    
    try {
      console.log('API call: /api/mcp-tools');
      const response = await fetch(getApiUrl('/api/mcp-tools'), {
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
        },
      });
      
      if (!response.ok) {
        throw new Error('Failed to get tool list.');
      }
      
      const data = await response.json();
      console.log(`API response success: ${data.servers?.length || 0} servers`);
      
      setServers(prevServers => {
        const serversList: MCPServer[] = data.servers.map((serverInfo: MCPServerInfo) => ({
          name: serverInfo.name,
          config: serverInfo.config,
          status: serverInfo.status,
          tools: serverInfo.tools,
          expanded: prevServers.find(s => s.name === serverInfo.name)?.expanded || false
        }));
        return serversList;
      });
    } catch (err) {
      console.error('Error getting tool list:', err);
      setError(`Failed to get tool list. Please check the server connection status.`);
    } finally {
      setIsLoading(false);
      isFetchingRef.current = false;
    }
  }, []);

  const refreshServerStatus = useCallback(async () => {
    if (isFetchingRef.current) return;
    
    setIsCheckingStatus(true);
    
    try {
      await fetchTools();
    } catch (error) {
      console.error('Error checking server status:', error);
    } finally {
      setIsCheckingStatus(false);
    }
  }, [fetchTools]);

  useEffect(() => {
    let mounted = true;
    let intervalId: NodeJS.Timeout | null = null;
    
    const initialFetch = async () => {
      if (mounted) {
        await fetchTools();
      }
    };
    
    initialFetch();
    
    intervalId = setInterval(() => {
      if (mounted && !isFetchingRef.current) {
        console.log('60 seconds interval update started');
        fetchTools();
      }
    }, 60000);
    
    return () => {
      mounted = false;
      if (intervalId) {
        console.log('Component unmount: interval cleanup');
        clearInterval(intervalId);
      }
    };
  }, [fetchTools]);

  const handleEditedConfigChange = (value: string) => {
    const cursorPosition = editConfigRef.current?.selectionStart || 0;
    setEditedConfig(value);
    setError(null);
    
    requestAnimationFrame(() => {
      if (editConfigRef.current) {
        editConfigRef.current.focus();
        editConfigRef.current.selectionStart = cursorPosition;
        editConfigRef.current.selectionEnd = cursorPosition;
      }
    });
  };
  
  const handleAddServer = async () => {
    if (!newConfigJSON.trim()) {
      setError('Please enter MCP server configuration.');
      return;
    }
    
    setIsLoading(true);
    setError(null);
    
    try {
      const parsed = tryParseConfig(newConfigJSON);
      if (!parsed) return;
      
      const { mcpServers } = parsed;
      
      for (const [name, config] of Object.entries(mcpServers)) {
        const response = await fetch(getApiUrl('/api/mcp-tools'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            name,
            config,
          }),
        });
        
        if (!response.ok) {
          throw new Error(`Failed to add server ${name}.`);
        }
        
        const data: ServerActionResponse = await response.json();
        if (data.restart) {
          setRestartResult(data.restart);
        }
      }
      
      setNewConfigJSON('');
      setShowAddServerModal(false);
      await fetchTools();
      
      if (onSettingsChanged) onSettingsChanged();
    } catch (err) {
      console.error('Server add error:', err);
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleDeleteServer = async (serverName: string) => {
    if (!window.confirm(`Delete MCP server '${serverName}'?`)) {
      return;
    }
    
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(getApiUrl(`/api/mcp-tools/${encodeURIComponent(serverName)}`), {
        method: 'DELETE',
      });
      
      if (!response.ok) {
        throw new Error('Failed to delete server.');
      }
      
      const data: ServerActionResponse = await response.json();
      if (data.restart) {
        setRestartResult(data.restart);
      }
      
      await fetchTools();
      
      if (onSettingsChanged) onSettingsChanged();
    } catch (err) {
      console.error('Server delete error:', err);
      setError(`Failed to delete server. Please check the server connection status.`);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleServerExpanded = (index: number) => {
    setServers(prev => {
      const updated = [...prev];
      updated[index] = {
        ...updated[index],
        expanded: !updated[index].expanded
      };
      return updated;
    });
  };

  const copyJSON = (text: string) => {
    navigator.clipboard.writeText(text)
      .then(() => {
        alert('Copied to clipboard.');
      })
      .catch(err => {
        console.error('Copy failed:', err);
        setError('Failed to copy to clipboard.');
      });
  };

  const handleEditServer = (serverName: string, serverConfig: ServerConfig) => {
    if (validationTimerRef.current) {
      clearTimeout(validationTimerRef.current);
      validationTimerRef.current = null;
    }
    
    const configStr = JSON.stringify(serverConfig, null, 2);
    
    setEditMode(true);
    setEditingServer(serverName);
    setEditedName(serverName);
    setEditedConfig(configStr);
    setError(null);
  };
  
  const handleCancelEdit = () => {
    setEditMode(false);
    setEditingServer(null);
    setEditedConfig('');
    setEditedName('');
    setError(null);
  };
  
  const handleSaveEdit = async () => {
    if (!editingServer) return;
    
    try {
      if (!editedName.trim()) {
        setError('Server name cannot be empty.');
        return;
      }
      
      let configObj;
      try {
        configObj = JSON.parse(editedConfig);
      } catch (e: unknown) {
        const errorMessage = e instanceof Error ? e.message : 'Syntax error';
        setError(`Invalid JSON format: ${errorMessage}`);
        return;
      }
      
      setIsLoading(true);
      setError(null);
      
      const response = await fetch(getApiUrl(`/api/mcp-tools/${encodeURIComponent(editingServer)}`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: editedName,
          config: configObj
        }),
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to edit server.');
      }
      
      const data: ServerActionResponse = await response.json();
      if (data.restart) {
        setRestartResult(data.restart);
      }
      
      setEditMode(false);
      setEditingServer(null);
      setEditedConfig('');
      setEditedName('');
      
      await fetchTools();
      
      if (onSettingsChanged) onSettingsChanged();
      
    } catch (err) {
      console.error('Server edit error:', err);
      setError((err as Error).message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRestartService = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch(getApiUrl('/api/mcp-tools/restart'), {
        method: 'POST',
      });
      
      if (!response.ok) {
        throw new Error('Failed to restart MCP service.');
      }
      
      const data = await response.json();
      setRestartResult({
        success: data.success,
        message: data.message
      });
      
      await fetchTools();
      
    } catch (err) {
      console.error('MCP service restart error:', err);
      setError(`Failed to restart MCP service: ${(err as Error).message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const EditModal = () => {
    if (!editMode) return null;
    
    return (
      <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-6 w-full max-w-2xl max-h-[90vh] overflow-auto">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium text-slate-200">Edit MCP server</h3>
            <button 
              onClick={handleCancelEdit}
              className="p-1 text-slate-400 hover:text-slate-200 rounded-md"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          
          {error && (
            <div className="my-4 p-3 bg-red-950/30 border border-red-800 rounded-lg flex items-start gap-3">
              <ShieldAlert className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-red-200 text-sm">{error}</p>
            </div>
          )}
          
          <div className="my-4 p-3 bg-blue-950/30 border border-blue-700/50 rounded-lg flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
            <p className="text-blue-200 text-sm">After changing the MCP server configuration, you need to click the <strong>Restart Service</strong> button to apply the changes.</p>
          </div>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Server name
              </label>
              <input
                type="text"
                value={editedName}
                onChange={(e) => setEditedName(e.target.value)}
                className="w-full p-2 text-sm bg-slate-800 border border-slate-700 rounded-lg focus:ring-blue-500 focus:border-blue-500 text-slate-300"
                placeholder="Server name"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                Server configuration (JSON)
              </label>
              <div className="relative border border-slate-700 rounded-lg bg-slate-800 overflow-hidden">
                <textarea
                  key="edit-config-textarea"
                  ref={editConfigRef}
                  rows={10}
                  value={editedConfig}
                  onChange={(e) => handleEditedConfigChange(e.target.value)}
                  className="w-full p-3 text-sm bg-transparent focus:ring-blue-500 focus:border-blue-500 text-slate-300 font-mono border-0 resize-none"
                  placeholder='{"transport": "stdio", "command": "python", "args": ["path/script.py"]}'
                  spellCheck="false"
                  autoComplete="off"
                  autoCorrect="off"
                  wrap="off"
                ></textarea>
              </div>
              
              <JsonHelpMessage 
                jsonString={editedConfig} 
                onFix={handleEditedConfigChange} 
              />
            </div>
            
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={handleCancelEdit}
                className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-slate-500/50 text-slate-400 hover:bg-slate-500/20 hover:border-slate-400 hover:text-slate-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-blue-500/50 text-blue-400 hover:bg-blue-500/20 hover:border-blue-400 hover:text-blue-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isLoading}
              >
                {isLoading ? <RefreshCw className="animate-spin" /> : <Check />}
                Save
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };
  
  const AddServerModal = () => {
    if (!showAddServerModal) return null;
    
    return (
      <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-6 w-full max-w-2xl max-h-[90vh] overflow-auto">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-medium text-slate-200">Add MCP server</h3>
            <button 
              onClick={() => {
                setShowAddServerModal(false);
                setNewConfigJSON('');
                setError(null);
              }}
              className="p-1 text-slate-400 hover:text-slate-200 rounded-md"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          
          {error && (
            <div className="my-4 p-3 bg-red-950/30 border border-red-800 rounded-lg flex items-start gap-3">
              <ShieldAlert className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
              <p className="text-red-200 text-sm">{error}</p>
            </div>
          )}
          
          <div className="my-4 p-3 bg-blue-950/30 border border-blue-700/50 rounded-lg flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-blue-400 mt-0.5 flex-shrink-0" />
            <p className="text-blue-200 text-sm">MCP 서버를 추가한 후에는 <strong>서비스 재시작</strong> 버튼을 눌러 변경사항을 적용해야 합니다.</p>
          </div>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1">
                MCP 설정 JSON (직접 붙여넣기)
              </label>
              <div className="relative border border-slate-700 rounded-lg bg-slate-800 overflow-hidden">
                <textarea
                  key="new-config-textarea" 
                  ref={newConfigRef}
                  rows={10}
                  className="w-full p-3 text-sm bg-transparent focus:ring-blue-500 focus:border-blue-500 text-slate-300 font-mono border-0 resize-none"
                  placeholder='{"서버이름": {"transport": "stdio", "command": "python", "args": ["경로/스크립트.py"]}}'
                  value={newConfigJSON}
                  onChange={(e) => handleNewConfigChange(e.target.value)}
                  spellCheck="false"
                  autoComplete="off"
                  autoCorrect="off"
                  wrap="off"
                ></textarea>
              </div>
              
              <JsonHelpMessage 
                jsonString={newConfigJSON} 
                onFix={handleNewConfigChange} 
              />
            </div>
            
            <div className="bg-slate-800/30 rounded-lg p-3 border border-slate-700/50">
              <h4 className="text-sm font-medium text-slate-300 mb-2">참고 사이트</h4>
              <div className="flex flex-col space-y-2">
                <a 
                  href="https://smithery.ai/" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1"
                >
                  <Plug className="h-4 w-4" /> Smithery.ai
                </a>
                <a 
                  href="https://cursor.directory/mcp" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1"
                >
                  <Server className="h-4 w-4" /> Cursor MCP Directory
                </a>
              </div>
            </div>
            
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => {
                  setShowAddServerModal(false);
                  setNewConfigJSON('');
                  setError(null);
                }}
                className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-slate-500/50 text-slate-400 hover:bg-slate-500/20 hover:border-slate-400 hover:text-slate-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isLoading}
              >
                Cancel
              </button>
              <button
                onClick={handleAddServer}
                className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-400 hover:text-emerald-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                disabled={isLoading}
              >
                {isLoading ? <RefreshCw className="animate-spin" /> : <Plus />}
                Add server
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const JsonModeView = () => {
    const allServersConfig = servers.reduce((acc, server) => {
      acc[server.name] = server.config;
      return acc;
    }, {} as Record<string, ServerConfig>);
    
    const initialJsonText = useMemo(() => 
      JSON.stringify(allServersConfig, null, 2), 
      [allServersConfig]
    );
    
    const [jsonText, setJsonText] = useState(initialJsonText);
    const jsonTextareaRef = useRef<HTMLTextAreaElement>(null);
    
    useEffect(() => {
      setJsonText(initialJsonText);
    }, [initialJsonText]);
    
    const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      const cursorPosition = e.target.selectionStart || 0;
      setJsonText(e.target.value);
      setError(null);
      
      setTimeout(() => {
        if (jsonTextareaRef.current) {
          jsonTextareaRef.current.focus();
          jsonTextareaRef.current.selectionStart = cursorPosition;
          jsonTextareaRef.current.selectionEnd = cursorPosition;
        }
      }, 0);
    };
    
    const formatJSON = () => {
      try {
        const fixedJson = autoFixJsonString(jsonText);
        const parsed = JSON.parse(fixedJson);
        setJsonText(JSON.stringify(parsed, null, 2));
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : 'Syntax error';
        setError(`JSON format error: ${errorMessage}`);
      }
    };
    
    const handleSaveJSON = async () => {
      try {
        let configObj;
        try {
          const fixedJson = autoFixJsonString(jsonText);
          configObj = JSON.parse(fixedJson);
        } catch (e: unknown) {
          const errorMessage = e instanceof Error ? e.message : 'Syntax error';
          setError(`Invalid JSON format: ${errorMessage}`);
          return;
        }
        
        setIsLoading(true);
        setError(null);
        
        const currentServerNames = servers.map(server => server.name);
        const newServerNames = Object.keys(configObj);
        
        for (const serverName of currentServerNames) {
          if (!newServerNames.includes(serverName)) {
            const response = await fetch(getApiUrl(`/api/mcp-tools/${encodeURIComponent(serverName)}`), {
              method: 'DELETE',
            });
            
            if (!response.ok) {
              throw new Error(`Failed to delete server ${serverName}.`);
            }
          }
        }
        
        for (const [serverName, config] of Object.entries(configObj)) {
          if (currentServerNames.includes(serverName)) {
            const response = await fetch(getApiUrl(`/api/mcp-tools/${encodeURIComponent(serverName)}`), {
              method: 'PUT',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                name: serverName,
                config
              }),
            });
            
            if (!response.ok) {
              throw new Error(`Failed to update server ${serverName}.`);
            }
          } else {
            const response = await fetch(getApiUrl('/api/mcp-tools'), {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                name: serverName,
                config,
              }),
            });
            
            if (!response.ok) {
              throw new Error(`Failed to add server ${serverName}.`);
            }
          }
        }
        
        await fetchTools();
        
        if (onSettingsChanged) onSettingsChanged();
      } catch (err) {
        console.error('JSON save error:', err);
        setError((err as Error).message);
      } finally {
        setIsLoading(false);
      }
    };
    
    return (
      <div className="space-y-4">
        <div className="flex justify-end space-x-2">
          <button
            className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-blue-500/50 text-blue-400 hover:bg-blue-500/20 hover:border-blue-400 hover:text-blue-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={handleSaveJSON}
            disabled={isLoading}
          >
            {isLoading ? <RefreshCw className="animate-spin" /> : <Check />}
            Save
          </button>
          <button
            className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-slate-500/50 text-slate-400 hover:bg-slate-500/20 hover:border-slate-400 hover:text-slate-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={formatJSON}
          >
            <FileJson /> Format
          </button>
          <button
            className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-slate-500/50 text-slate-400 hover:bg-slate-500/20 hover:border-slate-400 hover:text-slate-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            onClick={() => copyJSON(jsonText)}
          >
            <Copy /> Copy
          </button>
        </div>
        
        <div className="bg-slate-900/40 border border-slate-800 rounded-lg overflow-hidden">
          <div className="px-3 py-2 bg-slate-800/50 border-b border-slate-700">
            <span className="text-sm text-slate-300">MCP server configuration (JSON)</span>
          </div>
          <textarea
            ref={jsonTextareaRef}
            rows={24}
            className="w-full p-3 text-sm bg-slate-900/30 focus:ring-blue-500 focus:border-blue-500 text-slate-300 font-mono border-0 resize-none block"
            value={jsonText}
            onChange={handleTextChange}
            spellCheck="false"
            autoComplete="off"
            autoCorrect="off"
            wrap="off"
          ></textarea>
        </div>
        
        <JsonHelpMessage 
          jsonString={jsonText} 
          onFix={setJsonText} 
        />
      </div>
    );
  };

  const tryParseConfig = (jsonString: string): { mcpServers: Record<string, ServerConfig> } | null => {
    try {
      const fixedJsonString = autoFixJsonString(jsonString);
      const config = JSON.parse(fixedJsonString);
      return { mcpServers: config };
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : 'Syntax error';
      setError(`Invalid JSON format: ${errorMessage}`);
      return null;
    }
  };

  useEffect(() => {
    return () => {
      if (validationTimerRef.current) {
        clearTimeout(validationTimerRef.current);
      }
    };
  }, []);

  return (
    <div className="p-6 relative">
      <EditModal />
      <AddServerModal />
      <ResultNotification 
        result={restartResult} 
        onClose={() => setRestartResult(null)} 
      />
      
      <h2 className="text-xl font-semibold mb-4 flex items-center gap-2 text-card-foreground">
        <Plug className="h-5 w-5 text-muted-foreground" /> MCP tool management
      </h2>
      
      {!jsonMode && (
        <button 
          onClick={() => setJsonMode(true)}
          className="absolute top-6 right-6 text-xs px-2 py-1 rounded bg-muted text-muted-foreground flex items-center gap-1 hover:bg-muted/80"
        >
          <FileJson className="h-3 w-3" /> JSON mode
        </button>
      )}
      
      {jsonMode && (
        <button 
          onClick={() => setJsonMode(false)}
          className="absolute top-6 right-6 text-xs px-2 py-1 rounded bg-muted text-muted-foreground flex items-center gap-1 hover:bg-muted/80"
        >
          <Server className="h-3 w-3" /> Server mode
        </button>
      )}
      
      {error && !editMode && !showAddServerModal && (
        <div className="my-4 p-3 bg-red-950/30 border border-red-800 rounded-lg flex items-start gap-3">
          <ShieldAlert className="h-5 w-5 text-red-500 mt-0.5 flex-shrink-0" />
          <p className="text-red-200 text-sm">{error}</p>
        </div>
      )}
      
              {!editMode && !showAddServerModal && (
        <div className="my-4 p-3 bg-muted/50 border border-border rounded-lg flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
          <div className="text-muted-foreground text-sm">
            <p className="font-medium mb-1">Important Notice</p>
            <p>After changing the MCP tool settings (add/edit/delete), you must click the <strong>Restart Service</strong> button to apply the changes.</p>
          </div>
        </div>
      )}
      
      <div className="mt-6">
        {isLoading && !editMode && !showAddServerModal ? (
          <div className="flex items-center justify-center p-8">
            <RefreshCw className="h-5 w-5 text-muted-foreground animate-spin" />
            <span className="ml-2 text-muted-foreground">Loading tool list...</span>
          </div>
        ) : jsonMode ? (
          <JsonModeView />
        ) : (
          <div>
            {servers.length === 0 ? (
              <div className="bg-muted/50 rounded-lg p-6 text-center">
                <Server className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                <p className="text-muted-foreground mb-4">No registered MCP servers</p>
                <button
                  className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-400 hover:text-emerald-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={() => setShowAddServerModal(true)}
                >
                  <Plus /> Add server
                </button>
              </div>
            ) : (
              <div className="space-y-6">
                {servers.map((server, serverIdx) => (
                  <div 
                    key={serverIdx}
                    className="bg-muted/30 rounded-lg border border-border overflow-hidden"
                  >
                    <div className="p-4 flex items-center gap-4">
                      <ServerStatusIcon status={server.status || 'unknown'} />
                      
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-card-foreground flex items-center gap-2">
                          {server.name}
                          {server.status === 'online' && (
                            <span className="text-xs px-2 py-0.5 bg-emerald-900/30 text-emerald-400 rounded-full">Online</span>
                          )}
                          {server.status === 'offline' && (
                            <span className="text-xs px-2 py-0.5 bg-red-900/30 text-red-400 rounded-full">Offline</span>
                          )}
                        </h3>
                        <p className="text-xs text-muted-foreground mt-1">
                          {server.tools && server.tools.length > 0 ? (
                            `${server.tools.length} tools provided`
                          ) : (
                            'No tools'
                          )}
                        </p>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        <button
                          className="p-2 text-muted-foreground hover:text-card-foreground rounded-lg hover:bg-muted"
                          onClick={() => toggleServerExpanded(serverIdx)}
                          title={server.expanded ? 'Collapse' : 'Expand'}
                        >
                          {server.expanded ? (
                            <ChevronUp className="h-5 w-5" />
                          ) : (
                            <ChevronDown className="h-5 w-5" />
                          )}
                        </button>
                        
                        <button
                          className="p-2 text-muted-foreground hover:text-card-foreground rounded-lg hover:bg-muted"
                          onClick={() => handleEditServer(server.name, server.config)}
                          title="Edit server"
                        >
                          <Edit className="h-5 w-5" />
                        </button>
                        
                        <button
                          className="p-2 text-muted-foreground hover:text-red-400 rounded-lg hover:bg-muted"
                          onClick={() => handleDeleteServer(server.name)}
                          title="Delete server"
                        >
                          <Trash2 className="h-5 w-5" />
                        </button>
                      </div>
                    </div>
                    
                    {server.expanded && (
                      <div className="border-t border-border p-4 bg-muted/30">
                        {server.tools && server.tools.length > 0 ? (
                          <ToolsList tools={server.tools} serverName={server.name} />
                        ) : (
                          <p className="text-muted-foreground text-center py-4">No tools provided by this server</p>
                        )}
                      </div>
                    )}
                  </div>
                ))}
                
                <div className="flex justify-between">
                  <div className="flex gap-2">
                    <button
                      className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-emerald-500/50 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-400 hover:text-emerald-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      onClick={() => setShowAddServerModal(true)}
                    >
                      <Plus /> Add server
                    </button>
                    
                    <button
                      className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-blue-500/50 text-blue-400 hover:bg-blue-500/20 hover:border-blue-400 hover:text-blue-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      onClick={handleRestartService}
                      disabled={isLoading}
                    >
                      <RefreshCw className={`${isLoading ? 'animate-spin' : ''}`} /> 
                      Restart service
                    </button>
                  </div>
                  
                  <button
                    className="py-2 inline-flex items-center justify-center whitespace-nowrap text-sm font-medium disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive border shadow-xs dark:bg-input/30 dark:border-input dark:hover:bg-input/50 h-8 rounded-md gap-1.5 px-3 has-[>svg]:px-2.5 bg-transparent border-slate-500/50 text-slate-400 hover:bg-slate-500/20 hover:border-slate-400 hover:text-slate-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                    onClick={refreshServerStatus}
                    disabled={isLoading || isCheckingStatus}
                  >
                    {isCheckingStatus ? (
                      <>
                        <RefreshCw className="animate-spin" /> Checking...
                      </>
                    ) : (
                      <>
                        <RefreshCw /> Check status
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default MCPToolManager;