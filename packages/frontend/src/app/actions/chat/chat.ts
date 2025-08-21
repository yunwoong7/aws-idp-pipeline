import {
  ContentItem,
  FileAttachment,
  TextContentItem,
  ToolResultContentItem,
  ToolUseContentItem,
} from '@/types/agent.types';

// use crypto.randomUUID() but fallback if not available
function generateUUID(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // fallback for older browsers
  return 'xxxx-xxxx-4xxx-yxxx'.replace(/[xy]/g, function(c) {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}

// define backend response type
interface ChunkData {
  chunk: Array<{
    type: string;
    text?: string;
    name?: string;
    input?: string;
    id?: string;
    index: number;
    image_data?: string;
    mime_type?: string;
  }>;
  toolCalls: any;
  metadata: {
    langgraph_node: string;
    langgraph_step: number;
    type: string;
    is_image?: boolean;
    image_data?: string;
    mime_type?: string;
    requires_approval?: boolean;
    thread_id?: string;
  };
}

// state for accumulating text
let accumulatedText = '';
let currentTextId = '';

// state for accumulating tool uses
let accumulatedToolUses = new Map<string, {
  id: string;
  name: string;
  input: string;
  timestamp: number;
}>();

function processChunk(
  chunkData: ChunkData,
  controller: ReadableStreamDefaultController<ContentItem>,
) {
  console.log('🔍 Processing chunk:', chunkData);
  
  if (!chunkData.chunk || chunkData.chunk.length === 0) {
    return;
  }

  for (const item of chunkData.chunk) {
    console.log('🔍 Processing chunk item:', item);
    
    switch (item.type) {
      case 'text':
        const newText = item.text || '';
        if (newText.trim()) {
          // 순수 텍스트만 누적 처리. 도구 호출은 'tool_use' 타입에서만 처리한다.
          if (!currentTextId) {
            currentTextId = generateUUID();
            accumulatedText = '';
          }
          accumulatedText += newText;
          console.log(`📝 Accumulating text (length: ${accumulatedText.length}):`, newText);
          if (accumulatedText.length > 100 || newText.includes(' ') || newText.includes('\n')) {
            const textItem: TextContentItem = {
              id: currentTextId,
              type: 'text',
              content: accumulatedText,
              timestamp: Date.now(),
            };
            console.log(`📝 Enqueuing accumulated text (${accumulatedText.length} chars):`, textItem);
            controller.enqueue(textItem);
            // 누적 버퍼를 비우지 않고 유지하여 다음 청크에서도 전체 내용을 지속적으로 갱신
          }
        }
        break;
        
      case 'tool_use':
        // identify tool based on index (group chunks with the same index)
        const toolKey = `tool_${item.index}`;
        const toolName = item.name || '';
        const toolInput = item.input || '';
        
        console.log(`🔧 Processing tool_use chunk: key=${toolKey}, name="${toolName}", input="${toolInput}"`);
        
        if (!accumulatedToolUses.has(toolKey)) {
          // start new tool use
          accumulatedToolUses.set(toolKey, {
            id: generateUUID(),
            name: toolName,
            input: toolInput,
            timestamp: Date.now()
          });
          console.log(`🔧 Created new tool accumulation for ${toolKey}`);
        } else {
          // accumulate input to existing tool use
          const existing = accumulatedToolUses.get(toolKey)!;
          existing.input += toolInput;
          existing.name = toolName || existing.name; // update name if it exists
          console.log(`🔧 Updated tool accumulation for ${toolKey}: name="${existing.name}", input="${existing.input}"`);
        }
        
        // check if it's a complete tool use (name and complete JSON input)
        const accumulated = accumulatedToolUses.get(toolKey)!;
        if (accumulated.name && accumulated.input) {
          // check if JSON is complete
          try {
            JSON.parse(accumulated.input);
            // create tool use item
            const toolUseItem: ToolUseContentItem = {
              id: accumulated.id,
              type: 'tool_use',
              name: accumulated.name,
              input: accumulated.input,
              timestamp: accumulated.timestamp,
              requiresApproval: true, // all tools require approval
              approved: false,
              collapsed: true,
            };
            console.log('🔧 ✅ Enqueuing complete tool_use item:', toolUseItem);
            console.log('🔧 ✅ Tool input content:', accumulated.input);
            console.log('🔧 ✅ Tool input length:', accumulated.input.length);
            controller.enqueue(toolUseItem);
            
            // remove from accumulated state
            accumulatedToolUses.delete(toolKey);
          } catch (e) {
            // if JSON is incomplete, continue accumulation
            console.log(`🔧 ⏳ Incomplete tool_use JSON for ${toolKey}, continuing accumulation: "${accumulated.input}"`);
          }
        } else {
          console.log(`🔧 ⏳ Waiting for more tool data: name="${accumulated.name}", input="${accumulated.input}"`);
        }
        break;
        
      case 'tool_result':
        const toolResultItem: ToolResultContentItem = {
          id: generateUUID(),
          type: 'tool_result',
          result: item.text || '',
          timestamp: Date.now(),
          collapsed: true,
        };
        console.log('✅ Enqueuing tool_result item:', toolResultItem);
        controller.enqueue(toolResultItem);
        break;
        
      case 'image':
        // add image processing logic if needed
        console.log('🖼️ Image chunk received:', item);
        break;
        
      default:
        console.log('❓ Unknown chunk type:', item.type, item);
    }
  }
  
  // check for interrupt (in metadata)
  if (chunkData.metadata?.type === 'interrupt' && chunkData.metadata?.requires_approval) {
    console.log('🛑 Tool execution interrupt detected - waiting for user approval');
    
    // create special ContentItem to represent interrupt state
    const interruptItem: ToolUseContentItem = {
      id: generateUUID(),
      type: 'tool_use',
      name: 'interrupt',
      input: JSON.stringify({
        message: 'Tool execution requires approval',
        thread_id: chunkData.metadata.thread_id
      }),
      timestamp: Date.now(),
      requiresApproval: true,
      approved: false,
      collapsed: true,
    };
    
    console.log('🛑 Enqueuing interrupt item for approval:', interruptItem);
    controller.enqueue(interruptItem);
  }
}

export async function sendChatStream(
  message: string,
  conversationId?: string,
  attachments?: FileAttachment[],
  projectId?: string | null,
) {
  console.log('🚀 Starting chat stream:', { message: message.substring(0, 100), projectId });
  
  // initialize text accumulation state
  accumulatedText = '';
  currentTextId = '';
  
  // initialize tool use accumulation state
  accumulatedToolUses.clear();
  
  return new ReadableStream<ContentItem>({
    async start(controller) {
      try {
        // send request to backend
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            message,
            stream: true,
            project_id: projectId,
            conversation_id: conversationId,
          }),
        });

        if (!response.ok) {
          throw new Error(`API request failed: ${response.status}`);
        }

        if (!response.body) {
          throw new Error('No response body');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let buffer = '';
        
        try {
          while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
              console.log('🏁 Reader done - stream ended');
              break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // 마지막 불완전한 라인 보관
            
            let shouldBreak = false;
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6).trim();
                
                if (data === '[DONE]') {
                  console.log('🏁 Stream completed with [DONE] signal');
                  shouldBreak = true;
                  break;
                }
                
                if (data === '') continue; // 빈 데이터 스킵
                
                try {
                  const chunkData: ChunkData = JSON.parse(data);
                  processChunk(chunkData, controller);
                } catch (parseError) {
                  console.error('❌ Failed to parse chunk data:', parseError, 'Original data:', data);
                }
              }
            }
            
            if (shouldBreak) break;
          }
          // 스트림 종료 후 버퍼에 남은 단일 라인이 완전한 이벤트라면 처리
          const trimmed = buffer.trim();
          if (trimmed.startsWith('data: ')) {
            const data = trimmed.slice(6).trim();
            if (data && data !== '[DONE]') {
              try {
                const chunkData: ChunkData = JSON.parse(data);
                processChunk(chunkData, controller);
              } catch (e) {
                console.warn('⚠️ Leftover buffer parse failed (ignored):', e);
              }
            }
          }

          // 아직 완성되지 않아 누적 중인 tool_use 입력이 있다면 가능한 한 현재 상태로 플러시
          if (accumulatedToolUses.size > 0) {
            console.log('🔧 Flushing pending tool_use accumulations at stream end');
            for (const [key, pending] of accumulatedToolUses.entries()) {
              const toolUseItem: ToolUseContentItem = {
                id: pending.id,
                type: 'tool_use',
                name: pending.name,
                input: pending.input,
                timestamp: pending.timestamp,
                requiresApproval: true,
                approved: false,
                collapsed: true,
              };
              controller.enqueue(toolUseItem);
              accumulatedToolUses.delete(key);
            }
          }
          
          // 남은 텍스트가 있으면 최종 처리
          if (accumulatedText && currentTextId) {
            console.log('🔚 Finalizing accumulated text:', accumulatedText);
            controller.enqueue({
              type: 'text',
              id: currentTextId,
              content: accumulatedText,
              timestamp: Date.now(),
            });
          }
          
        } finally {
          reader.releaseLock();
        }
        
        controller.close();
      } catch (error) {
        console.error('❌ Chat stream error:', error);
        controller.error(error);
      }
    },
  });
}

// function to resume from interrupt after tool approval/rejection
export async function resumeFromInterrupt(
  conversationId: string,
  approved: boolean,
  toolCallId?: string,
  projectId?: string | null,
) {
  console.log('🔄 Resuming from interrupt:', { conversationId, approved, toolCallId, projectId });
  
  // initialize text accumulation state
  accumulatedText = '';
  currentTextId = '';
  
  // initialize tool use accumulation state
  accumulatedToolUses.clear();
  
  return new ReadableStream<ContentItem>({
    async start(controller) {
      try {
        // send request to backend
        const response = await fetch('/api/chat/resume', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            conversation_id: conversationId,
            approved,
            tool_call_id: toolCallId,
            project_id: projectId,
          }),
        });

        if (!response.ok) {
          throw new Error(`Resume request failed: ${response.status}`);
        }

        if (!response.body) {
          throw new Error('No response body');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let buffer = '';
        
        try {
          while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
              console.log('🏁 Resume reader done - stream ended');
              break;
            }
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // 마지막 불완전한 라인 보관
            
            let shouldBreak = false;
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6).trim();
                
                if (data === '[DONE]') {
                  console.log('🏁 Resume stream completed with [DONE] signal');
                  shouldBreak = true;
                  break;
                }
                
                if (data === '') continue; // 빈 데이터 스킵
                
                try {
                  const chunkData: ChunkData = JSON.parse(data);
                  processChunk(chunkData, controller);
                } catch (parseError) {
                  console.error('❌ Failed to parse resume chunk data:', parseError, 'Original data:', data);
                }
              }
            }
            
            if (shouldBreak) break;
          }
          
          // 남은 텍스트가 있으면 최종 처리
          if (accumulatedText && currentTextId) {
            console.log('🔚 Finalizing accumulated text in resume:', accumulatedText);
            controller.enqueue({
              type: 'text',
              id: currentTextId,
              content: accumulatedText,
              timestamp: Date.now(),
            });
          }
          
        } finally {
          reader.releaseLock();
        }
        
        controller.close();
      } catch (error) {
        console.error('❌ Resume stream error:', error);
        controller.error(error);
      }
    },
  });
}