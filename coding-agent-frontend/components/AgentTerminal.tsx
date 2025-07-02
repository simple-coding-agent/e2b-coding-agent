'use client'

import { useState, useRef, useEffect, useMemo } from 'react'
import {
  CheckCircle, Loader, TriangleAlert, XCircle, ChevronRight,
  BotMessageSquare, Terminal, Cog, GitCommitHorizontal, Cloud
} from 'lucide-react'

// --- Interfaces ---

// Raw event directly from the server stream
interface RawEvent {
  type: string;
  timestamp: string;
  data: any;
}

// A processed event, structured for easy rendering
type ProcessedEvent = {
  key: string;
  timestamp: string;
  raw: RawEvent;
} & (
  | { displayType: 'TASK_LIFECYCLE'; icon: JSX.Element; message: string; }
  | { displayType: 'SETUP'; icon: JSX.Element; message: string; }
  | { displayType: 'ERROR'; message: string; content: any; }
  | {
      displayType: 'TOOL_CALL';
      status: 'running' | 'completed' | 'error';
      toolName: string;
      params: any;
      output?: any;
      error?: any;
    }
);

export default function AgentTerminal() {
  const [rawEvents, setRawEvents] = useState<RawEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [query, setQuery] = useState('Create a simple README.md file with project information, then commit and push it.');
  const [status, setStatus] = useState('Ready.');
  const [statusType, setStatusType] = useState<'info' | 'error'>('info');
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const terminalRef = useRef<HTMLDivElement>(null);
  
  // Cache processed events to prevent re-computation and flickering
  const eventCache = useRef(new Map<string, ProcessedEvent>()).current;

  // Add this near the top of your component
  useEffect(() => {
    console.log(`🔄 Component re-rendered. Raw events: ${rawEvents.length}, Processed events: ${processedEvents.length}`);
  }, [rawEvents]);

  // Auto-scroll to bottom of the terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [rawEvents]);

  // Process raw events into a stable list for rendering
  const processedEvents = useMemo(() => {
    console.log(`🔄 Processing ${rawEvents.length} raw events`);
    
    rawEvents.forEach((event, index) => {
      const [category, action] = event.type.split('.');
      
      // For tool events, we need to find the original start event and update it
      if (category === 'tool' && (action === 'end' || action === 'error')) {
        console.log(`🔗 Looking for running tool to update: ${event.data.tool_name}`);
        
        // Find the running tool event in the cache that matches the name
        const cacheEntries = Array.from(eventCache.values()).reverse();
        const runningToolEntry = cacheEntries.find(p_event => 
          p_event.displayType === 'TOOL_CALL' && 
          p_event.toolName === event.data.tool_name && 
          p_event.status === 'running'
        );
        
        if (runningToolEntry) {
          console.log(`✨ Found and updating tool: ${event.data.tool_name} -> ${action}`);
          runningToolEntry.status = action === 'end' ? 'completed' : 'error';
          if (action === 'end') {
            runningToolEntry.output = event.data;
          } else {
            runningToolEntry.error = event.data;
          }
        } else {
          console.warn(`⚠️ Could not find running tool to update: ${event.data.tool_name}`);
          console.log('Available cache entries:', cacheEntries.map(e => ({
            type: e.displayType,
            tool: e.displayType === 'TOOL_CALL' ? e.toolName : 'N/A',
            status: e.displayType === 'TOOL_CALL' ? e.status : 'N/A'
          })));
        }
        return; // Don't process end/error events as new list items
      }

      // Generate a unique ID for this event
      let uniqueId = `event-${index}-${event.timestamp}`;
      
      // If the event is already cached, skip it
      if (eventCache.has(uniqueId)) {
        console.log(`⏭️ Event already cached: ${uniqueId}`);
        return;
      }

      let processed: ProcessedEvent | null = null;
      
      switch (category) {
        case 'task':
          console.log(`📋 Processing task event: ${action}`);
          if (action === 'start') {
            processed = { 
              key: uniqueId, 
              displayType: 'TASK_LIFECYCLE', 
              icon: <span className='text-success'>▶</span>, 
              message: `Task started: "${event.data.query}"`, 
              raw: event, 
              timestamp: event.timestamp 
            };
          } else if (action === 'finish') {
            processed = { 
              key: uniqueId, 
              displayType: 'TASK_LIFECYCLE', 
              icon: <CheckCircle className="text-success" />, 
              message: `Task completed successfully (${event.data.total_iterations} iterations)`, 
              raw: event, 
              timestamp: event.timestamp 
            };
          } else if (action === 'error') {
            processed = { 
              key: uniqueId, 
              displayType: 'ERROR', 
              message: event.data.error, 
              content: event.data, 
              raw: event, 
              timestamp: event.timestamp 
            };
          }
          break;

        case 'setup':
          console.log(`⚙️ Processing setup event: ${action}`);
          const icon = action.endsWith('end') ? 
            <CheckCircle className="text-success" size={16} /> : 
            <Loader className="animate-spin text-info" size={16} />;
          processed = { 
            key: uniqueId, 
            displayType: 'SETUP', 
            icon, 
            message: event.data.message, 
            raw: event, 
            timestamp: event.timestamp 
          };
          break;

        case 'agent':
          console.log(`🤖 Processing agent event: ${action}`);
          if (action === 'loop' && event.type === 'agent.loop.start') {
            processed = { 
              key: uniqueId, 
              displayType: 'TASK_LIFECYCLE', 
              icon: <BotMessageSquare className="text-info" size={16} />, 
              message: "Agent started working on the task", 
              raw: event, 
              timestamp: event.timestamp 
            };
          }
          // Remove LLM_THOUGHT processing - we're simplifying this
          break;

        case 'tool':
          if (action === 'start') {
            // Use a unique key based on tool name and timestamp for linking
            uniqueId = `tool-${event.data.tool_name}-${event.timestamp}`;
            console.log(`🔧 Processing tool START: ${event.data.tool_name}, ID: ${uniqueId}`);
            processed = {
              key: uniqueId,
              displayType: 'TOOL_CALL',
              status: 'running',
              toolName: event.data.tool_name,
              params: event.data,
              raw: event,
              timestamp: event.timestamp,
            };
          }
          break;
      }
      
      if (processed) {
        console.log(`💾 Caching processed event: ${processed.key}`);
        eventCache.set(processed.key, processed);
      }
    });
    
    const result = Array.from(eventCache.values());
    console.log(`📊 Returning ${result.length} processed events`);
    return result;
  }, [rawEvents, eventCache]);

  const startTask = async () => {
    // Clear the cache when starting a new task
    eventCache.clear();
    
    if (!query.trim()) {
      setStatus('Please enter a query');
      setStatusType('error');
      return;
    }

    setRawEvents([]);
    setExpandedEvents(new Set());
    setIsRunning(true);
    setStatus('Creating task...');
    setStatusType('info');

    try {
      const response = await fetch('http://127.0.0.1:8000/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), model: 'openai/gpt-4o' }),
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      const taskId = data.task_id;
      setStatus(`Task stream opened: ${taskId}`);

      const eventSource = new EventSource(`http://127.0.0.1:8000/tasks/${taskId}/events`);

      eventSource.onmessage = (e) => {
        try {
          const event: RawEvent = JSON.parse(e.data);
          
          // ADD DETAILED LOGGING HERE
          console.log(`🔥 Event received at ${new Date().toISOString()}:`, {
            type: event.type,
            timestamp: event.timestamp,
            data: event.data
          });
          
          if (event.type === 'stream.keepalive') {
            console.log('⏰ Keepalive event - ignoring');
            return;
          }
          
          // Add event to state immediately
          console.log('📝 Adding event to state:', event.type);
          setRawEvents(prev => {
            const newEvents = [...prev, event];
            console.log(`📊 Total events now: ${newEvents.length}`);
            return newEvents;
          });

          // Update status based on event type
          const [category, action] = event.type.split('.');
          console.log(`🏷️ Event category: ${category}, action: ${action}`);
          
          switch (category) {
            case 'setup': 
              console.log('⚙️ Setup event:', event.data.message);
              setStatus(event.data.message || 'Setting up environment...'); 
              break;
            case 'tool':
              if (action === 'start') {
                console.log('🔧 Tool START:', event.data.tool_name);
                setStatus(`Executing: ${event.data.tool_name}`);
              } else if (action === 'end') {
                console.log('✅ Tool END:', event.data.tool_name);
                setStatus(`Completed: ${event.data.tool_name}`);
              } else if (action === 'error') {
                console.log('❌ Tool ERROR:', event.data.tool_name, event.data);
              }
              break;
            case 'llm':
              if (action === 'start') {
                console.log('🧠 LLM START');
                setStatus('Agent is thinking...');
              } else if (action === 'end') {
                console.log('🧠 LLM END');
              }
              break;
            case 'task':
              if (action === 'finish') {
                console.log('🎉 Task FINISHED');
                setStatus('Task completed successfully!');
                setStatusType('info');
              } else if (action === 'end') {
                console.log('🔚 Task END - closing connection');
                eventSource.close();
                setIsRunning(false);
              } else if (action === 'error') {
                console.log('💥 Task ERROR:', event.data);
                setStatus(`Error: ${event.data.error || 'Unknown error'}`);
                setStatusType('error');
                eventSource.close();
                setIsRunning(false);
              }
              break;
            default:
              console.log('❓ Unknown event category:', category);
          }
        } catch (error) {
          console.error('💀 Error parsing event:', error, 'Raw data:', e.data);
        }
      };

      eventSource.onerror = (e) => {
        console.error('EventSource error:', e);
        setStatus('Connection error. The agent may have finished or an error occurred.');
        setStatusType('error');
        eventSource.close();
        setIsRunning(false);
      };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      setStatus(`Failed to start task: ${errorMessage}`);
      setStatusType('error');
      setIsRunning(false);
    }
  };

  const toggleEventExpansion = (key: string) => {
    setExpandedEvents(prev => {
      const newSet = new Set(prev);
      if (newSet.has(key)) newSet.delete(key);
      else newSet.add(key);
      return newSet;
    });
  };

  const formatJson = (data: any) => JSON.stringify(data, null, 2);
  const formatTimestamp = (timestamp?: string) => 
    timestamp ? new Date(timestamp).toLocaleTimeString("en-US", { hour12: false }) : '';

  const RenderableEvent = ({ event }: { event: ProcessedEvent }) => {
    const isExpanded = expandedEvents.has(event.key);

    const renderToolIcon = (toolName: string) => {
      if (toolName.includes('commit') || toolName.includes('push')) 
        return <GitCommitHorizontal size={16} />;
      if (toolName.includes('observe') || toolName.includes('read')) 
        return <Terminal size={16} />;
      return <Cog size={16} />;
    }

    switch (event.displayType) {
      case 'TOOL_CALL': {
        const StatusIcon = {
          running: <Loader className="animate-spin text-info" size={16} />,
          completed: <CheckCircle className="text-success" size={16} />,
          error: <XCircle className="text-error" size={16} />,
        }[event.status];
        
        return (
          <div className={`event tool-call-event status-${event.status}`}>
            <div className="event-header clickable" onClick={() => toggleEventExpansion(event.key)}>
              <ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} />
              <span className="tool-status-icon">{StatusIcon}</span>
              <span className="tool-icon">{renderToolIcon(event.toolName)}</span>
              <span className="event-tool">{event.toolName}</span>
              <span className="event-timestamp">{formatTimestamp(event.timestamp)}</span>
            </div>
            {isExpanded && (
              <div className="tool-details">
                <div className="tool-section">
                  <h4 className="tool-section-header">Parameters</h4>
                  <pre className="tool-section-content">{formatJson(event.params)}</pre>
                </div>
                {event.output && (
                  <div className="tool-section">
                    <h4 className="tool-section-header">Output</h4>
                    <pre className="tool-section-content">{formatJson(event.output)}</pre>
                  </div>
                )}
                {event.error && (
                  <div className="tool-section">
                    <h4 className="tool-section-header text-error">Error</h4>
                    <pre className="tool-section-content">{formatJson(event.error)}</pre>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      }
      
      case 'ERROR': {
        return (
          <div className="event simple-event event-error">
            <div className={`event-header ${event.content ? 'clickable' : ''}`} 
                 onClick={() => event.content && toggleEventExpansion(event.key)}>
              {event.content && <ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} />}
              <span className='mr-2'><TriangleAlert size={16} className='text-error'/></span>
              <span>{event.message}</span>
              <span className="event-timestamp">{formatTimestamp(event.timestamp)}</span>
            </div>
            {isExpanded && event.content && <pre className="event-data">{formatJson(event.content)}</pre>}
          </div>  
        );
      }
      
      case 'SETUP':
      case 'TASK_LIFECYCLE':
        return (
          <div className="event simple-event">
            <div className="event-header">
              <span className='mr-2'>{event.icon}</span>
              <span>{event.message}</span>
              <span className="event-timestamp">{formatTimestamp(event.timestamp)}</span>
            </div>
          </div>
        );
        
      default: 
        return null;
    }
  };
  
  return (
    <div>
      <div className="input-section">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your task for the AI agent..."
          disabled={isRunning}
          onKeyDown={(e) => { 
            if (e.key === 'Enter' && !e.shiftKey) { 
              e.preventDefault(); 
              startTask(); 
            }
          }}
        />
        <div className="button-group">
          <button 
            onClick={startTask} 
            disabled={isRunning} 
            className={`button button-primary ${isRunning ? 'button-loading' : ''}`}>
            {isRunning ? 'Running...' : 'Start Task'}
          </button>
          <button 
            onClick={() => { 
              setRawEvents([]); 
              eventCache.clear(); 
              setStatus('Ready.'); 
            }} 
            disabled={isRunning} 
            className="button button-secondary">
            Clear
          </button>
        </div>
      </div>
      
      {status && (
        <div className={`status-bar ${statusType}`}>
          <div className="status-indicator" />
          <span>{status}</span>
        </div>
      )}
      
      <div className="terminal-container">
        <div className="terminal-header"><Cloud size={16} /> Agent Stream</div>
        <div className="terminal" ref={terminalRef}>
          {processedEvents.length === 0 ? (
            <div className="terminal-empty">Task stream will appear here...</div>
          ) : (
            processedEvents.map(event => <RenderableEvent key={event.key} event={event} />)
          )}
        </div>
      </div>
    </div>
  );
}
