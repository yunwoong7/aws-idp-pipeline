// BaseMessage interface definition
export interface BaseMessage {
  content: string;
  role?: string;
  type?: string;
  [key: string]: any;
}

// Agent state
export interface AgentState {
  messages: BaseMessage[];
  next?: string;
  [key: string]: any; // Index signature for additional properties
}

// Human review related type
export interface HumanReview {
  action: 'yes' | 'no';
  args?: any;
}

// Base content item type
export interface BaseContentItem {
  id: string;
  type: string;
  timestamp: number;
}

// Text content
export interface TextContentItem extends BaseContentItem {
  type: 'text';
  content: string;
}

// Image content
export interface ImageContentItem extends BaseContentItem {
  type: 'image';
  file_uri: string;
  alt?: string;
  caption?: string;
}

// Tool use content
export interface ToolUseContentItem extends BaseContentItem {
  type: 'tool_use';
  name: string;
  input: string;
  timestamp: number;
  collapsed?: boolean;
  requiresApproval?: boolean;
  approved?: boolean;
}

// Tool result content
export interface ToolResultContentItem extends BaseContentItem {
  type: 'tool_result';
  result: string;
  timestamp: number;
  collapsed?: boolean;
}

// Union of all content types
export type ContentItem = 
  | TextContentItem 
  | ImageContentItem 
  | ToolUseContentItem 
  | ToolResultContentItem;

// File attachment type
export interface FileAttachment {
  id: string;
  file: File;
  type: string;
  file_uri?: string;
  fileId?: string;
} 