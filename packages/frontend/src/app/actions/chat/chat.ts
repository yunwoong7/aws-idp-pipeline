import {
  ContentItem,
  FileAttachment,
  TextContentItem,
  ToolResultContentItem,
  ToolUseContentItem,
} from '@/types/agent.types';

// Step 인터페이스 정의
interface Step {
  step: number;
  node: string;
  items: ContentItem[];
  isComplete: boolean;
}

// Global step management variables
const currentMessageSteps = new Map();
const stepIdCounters = new Map();
let currentMessageId = '';

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

// Step 기반 유틸리티 함수들
function generateUniqueId(messageId: string, stepNumber: number, itemType: string, itemIndex: number): string {
  return `${messageId}-${stepNumber}-${itemType}-${itemIndex}`;
}

function getOrCreateStep(stepNumber: number, node: string): Step {
  if (!currentMessageSteps.has(stepNumber)) {
    currentMessageSteps.set(stepNumber, {
      step: stepNumber,
      node: node,
      items: [],
      isComplete: false
    });
    stepIdCounters.set(stepNumber, 0);
  }
  return currentMessageSteps.get(stepNumber)!;
}

function getNextItemIndex(stepNumber: number): number {
  const current = stepIdCounters.get(stepNumber) || 0;
  stepIdCounters.set(stepNumber, current + 1);
  return current;
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
    langgraph_node?: string;  // ReactAgent metadata
    strands_node?: string;    // StrandsAgent metadata
    langgraph_step?: number;  // ReactAgent metadata  
    strands_step?: number;    // StrandsAgent metadata
    type: string;
    is_image?: boolean;
    image_data?: string;
    mime_type?: string;
    requires_approval?: boolean;
    thread_id?: string;
  };
}

// Step 기반 상태 관리
let accumulatedTextByStep = new Map();
let currentStepForText = -1;

// Legacy text accumulation variables
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

  // Extract step metadata
  const strandsStep = chunkData.metadata?.strands_step;
  const strandsNode = chunkData.metadata?.strands_node || 'agent';
  const stepType = chunkData.metadata?.type;
  
  console.log(`📊 Step metadata: step=${strandsStep}, node=${strandsNode}, type=${stepType}`);

  for (const item of chunkData.chunk) {
    console.log('🔍 Processing chunk item:', item);
    
    switch (item.type) {
      case 'text':
        const newText = item.text || '';
        if (newText.trim() && stepType === 'ai_response' && strandsNode === 'agent') {
          // Handle text accumulation per step
          const step = strandsStep || 0;
          
          if (!accumulatedTextByStep.has(step)) {
            // New step - create new text accumulator
            accumulatedTextByStep.set(step, {
              text: '',
              id: generateUUID()
            });
            console.log(`📝 Starting text accumulation for step ${step}`);
          }
          
          const accumulator = accumulatedTextByStep.get(step)!;
          accumulator.text += newText;
          console.log(`📝 Accumulating text (step ${step}):`, newText);
          
          // Stream text immediately for AI responses
          const textItem: TextContentItem = {
            id: accumulator.id,
            type: 'text', 
            content: accumulator.text,
            timestamp: Date.now(),
          };
          console.log(`📝 Enqueuing text (step ${step}):`, textItem);
          controller.enqueue(textItem);
        }
        break;
        
      case 'tool_use':
        // Only process tool use if they're part of a tools step
        if (strandsNode === 'tools' && stepType === 'tool_use') {
          const toolKey = `step_${strandsStep}_tool_${item.index}`;
          const toolName = item.name || '';
          const toolInput = item.input || '';
          
          console.log(`🔧 Processing tool_use chunk (step ${strandsStep}): key=${toolKey}, name="${toolName}", input="${toolInput}"`);
          
          if (!accumulatedToolUses.has(toolKey)) {
            // start new tool use for this step
            accumulatedToolUses.set(toolKey, {
              id: generateUUID(),
              name: toolName,
              input: toolInput,
              timestamp: Date.now()
            });
            console.log(`🔧 Created new tool accumulation for ${toolKey} in step ${strandsStep}`);
          } else {
            // accumulate input to existing tool use
            const existing = accumulatedToolUses.get(toolKey)!;
            existing.input += toolInput;
            existing.name = toolName || existing.name; // update name if it exists
            console.log(`🔧 Updated tool accumulation for ${toolKey}: name="${existing.name}", input="${existing.input}"`);
          }
          
          // Enqueue the current accumulated snapshot as a streaming update
          const acc = accumulatedToolUses.get(toolKey)!;
          const toolUseItem: ToolUseContentItem = {
            id: acc.id, // keep id stable for this step
            type: 'tool_use',
            name: acc.name,
            input: acc.input,
            timestamp: acc.timestamp,
            requiresApproval: false,
            approved: false,
            collapsed: true,
          };
          console.log(`🔧 ⏩ Enqueuing streaming tool_use snapshot (step ${strandsStep}):`, toolUseItem);
          controller.enqueue(toolUseItem);
        }
        break;
        
      case 'tool_result':
        // Only process tool results if they're part of a tools step
        if (strandsNode === 'tools' && stepType === 'tool_result') {
          const toolResultItem: ToolResultContentItem = {
            id: generateUUID(),
            type: 'tool_result',
            result: item.text || '',
            timestamp: Date.now(),
            collapsed: true,
          };
          console.log(`✅ Enqueuing tool_result item (step ${strandsStep}):`, toolResultItem);
          controller.enqueue(toolResultItem);
        }
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

// 새로운 Step 기반 처리 함수
function processChunkWithSteps(
  chunkData: ChunkData,
  controller: ReadableStreamDefaultController<ContentItem>,
  messageId: string,
) {
  console.log('🔍 Processing chunk with steps:', chunkData);
  
  if (!chunkData.chunk || chunkData.chunk.length === 0) {
    return;
  }

  // 메타데이터에서 스텝 정보 추출
  const strandsStep = chunkData.metadata?.strands_step || 0;
  const strandsNode = chunkData.metadata?.strands_node || 'agent';
  const stepType = chunkData.metadata?.type;
  
  console.log(`📊 Step metadata: step=${strandsStep}, node=${strandsNode}, type=${stepType}`);

  // 현재 Step 가져오기 또는 생성
  const currentStep = getOrCreateStep(strandsStep, strandsNode);
  
  for (const item of chunkData.chunk) {
    console.log('🔍 Processing chunk item:', item);
    
    const itemIndex = getNextItemIndex(strandsStep);
    const uniqueId = generateUniqueId(messageId, strandsStep, item.type, itemIndex);
    
    switch (item.type) {
      case 'text':
        const newText = item.text || '';
        if (newText.trim() && stepType === 'ai_response' && strandsNode === 'agent') {
          // 기존 텍스트 아이템 찾기 또는 새로 생성
          let textItem = currentStep.items.find(i => i.type === 'text') as TextContentItem;
          
          if (!textItem) {
            textItem = {
              id: generateUUID(),
              uniqueId: uniqueId,
              type: 'text',
              content: '',
              timestamp: Date.now(),
            } as TextContentItem;
            currentStep.items.push(textItem);
          }
          
          textItem.content += newText;
          console.log(`📝 Accumulating text (step ${strandsStep}):`, newText);
          
          controller.enqueue(textItem);
        }
        break;
        
      case 'tool_use':
        if (strandsNode === 'tools' && stepType === 'tool_use') {
          // 기존 도구 사용 아이템 찾기 또는 새로 생성
          let toolUseItem = currentStep.items.find(i => 
            i.type === 'tool_use' && (i as ToolUseContentItem).name === item.name
          ) as ToolUseContentItem;
          
          if (!toolUseItem) {
            toolUseItem = {
              id: item.id || generateUUID(),
              uniqueId: uniqueId,
              type: 'tool_use',
              name: item.name || '',
              input: '',
              timestamp: Date.now(),
              requiresApproval: false,
              approved: false,
              collapsed: true,
            } as ToolUseContentItem;
            currentStep.items.push(toolUseItem);
          }
          
          toolUseItem.input = item.input || '';
          console.log(`🔧 Tool use (step ${strandsStep}): ${item.name}`);
          
          controller.enqueue(toolUseItem);
        }
        break;
        
      case 'tool_result':
        if (strandsNode === 'tools' && stepType === 'tool_result') {
          const toolResultItem: ToolResultContentItem = {
            id: generateUUID(),
            uniqueId: uniqueId,
            type: 'tool_result',
            result: item.text || '',
            timestamp: Date.now(),
            collapsed: true,
          } as ToolResultContentItem;
          
          currentStep.items.push(toolResultItem);
          console.log(`✅ Tool result (step ${strandsStep}):`, item.text?.substring(0, 100));
          
          controller.enqueue(toolResultItem);
        }
        break;
    }
  }
}

export async function sendChatStream(
  message: string,
  conversationId?: string,
  attachments?: FileAttachment[],
  projectId?: string | null,
) {
  console.log('🚀 Starting chat stream:', { message: message.substring(0, 100), projectId });
  
  // initialize step-based state
  currentMessageSteps.clear();
  stepIdCounters.clear();
  const messageId = generateUUID();
  currentMessageId = messageId;
  
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
                  processChunkWithSteps(chunkData, controller, messageId);
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
                processChunkWithSteps(chunkData, controller, messageId);
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
                  processChunkWithSteps(chunkData, controller, currentMessageId || generateUUID());
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