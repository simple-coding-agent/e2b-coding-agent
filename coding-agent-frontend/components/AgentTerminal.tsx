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
  | { displayType: 'LLM_THOUGHT'; message: string; content: any; }
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
  
  // STABILITY FIX: Cache processed events to prevent re-computation and flickering.
  // The `useRef` hook ensures the cache persists across renders.
  const eventCache = useRef(new Map<string, ProcessedEvent>()).current;

  // Auto-scroll to bottom of the terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [rawEvents]);

  // Process raw events into a stable list for rendering
  const processedEvents = useMemo(() => {
    rawEvents.forEach((event, index) => {
      // Use a timestamp-based key for tool events to link start/end, and index-based for others.
      let uniqueId = `event-${index}-${event.timestamp}`;

      const [category, action] = event.type.split('.');
      
      // For tool events, we need to find the original start event and update it.
      if (category === 'tool' && (action === 'end' || action === 'error')) {
        // Find the running tool event in the cache that matches the name.
        // We iterate backwards to find the most recent running tool of that name.
        const cacheEntries = Array.from(eventCache.values()).reverse();
        const runningToolEntry = cacheEntries.find(p_event => 
          p_event.displayType === 'TOOL_CALL' && 
          p_event.toolName === event.data.tool_name && 
          p_event.status === 'running'
        );
        
        if (runningToolEntry) {
          runningToolEntry.status = action === 'end' ? 'completed' : 'error';
          if (action === 'end') {
            runningToolEntry.output = event.data;
          } else {
            runningToolEntry.error = event.data.error;
          }
          // We've mutated the cached object directly. No need to re-add to cache.
          // This avoids creating a new object and preserves React's reference equality.
        }
        return; // Don't process end/error events as new list items
      }

      // If the event is already cached, no need to re-process.
      if (eventCache.has(uniqueId)) return;

      let processed: ProcessedEvent | null = null;
      
      switch (category) {
        case 'task':
          if (action === 'start') {
            processed = { key: uniqueId, displayType: 'TASK_LIFECYCLE', icon: <span className='text-success'>▶</span>, message: `Task started for: "${event.data.query}"`, raw: event, timestamp: event.timestamp };
          } else if (action === 'finish') {
            processed = { key: uniqueId, displayType: 'TASK_LIFECYCLE', icon: <CheckCircle className="text-success" />, message: `Task finished successfully.`, raw: event, timestamp: event.timestamp };
          } else if (action === 'error') {
            processed = { key: uniqueId, displayType: 'ERROR', message: event.data.error, content: event.data, raw: event, timestamp: event.timestamp };
          }
          break;
        case 'setup':
          const icon = action.endsWith('end') ? <Cog className="text-info" size={16} /> : <Loader className="animate-spin" size={16} />;
          processed = { key: uniqueId, displayType: 'SETUP', icon, message: event.data.message, raw: event, timestamp: event.timestamp };
          break;
        case 'agent':
           processed = { key: uniqueId, displayType: 'TASK_LIFECYCLE', icon: <BotMessageSquare size={16} />, message: "Agent loop started", raw: event, timestamp: event.timestamp };
           break;
        case 'llm':
          if (action === 'tool_call') {
            processed = { key: uniqueId, displayType: 'LLM_THOUGHT', message: `LLM plans to use tool: ${event.data.tool_name}`, content: event.data.arguments, raw: event, timestamp: event.timestamp };
          }
          break;
        case 'tool':
          if (action === 'start') {
            // Use a unique key for the tool start itself
            uniqueId = `tool-${event.timestamp}-${event.data.tool_name}`;
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
        eventCache.set(processed.key, processed);
      }
    });
    
    return Array.from(eventCache.values());
  }, [rawEvents, eventCache]);

  const startTask = async () => {
    // When starting a new task, we must clear the cache.
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
          
          if (event.type === 'stream.keepalive') return;
          setRawEvents(prev => [...prev, event]);

          const [category, action] = event.type.split('.');
          switch (category) {
            case 'setup': setStatus(event.data.message || 'Setting up environment...'); break;
            case 'llm': 
              if (action === 'start') setStatus('Agent is thinking...'); 
              else if (action === 'tool_call') setStatus(`Agent plans to use: ${event.data.tool_name}`);
              break;
            case 'tool':
              if (action === 'start') setStatus(`Executing tool: ${event.data.tool_name}`);
              break;
            case 'task':
              if (action === 'finish') {
                setStatus('Task completed successfully!');
                setStatusType('info');
              } else if (action === 'end') {
                eventSource.close();
                setIsRunning(false);
              } else if (action === 'error') {
                setStatus(`Error: ${event.data.error || 'Unknown error'}`);
                setStatusType('error');
                eventSource.close();
                setIsRunning(false);
              }
              break;
          }
        } catch (error) {
          console.error('Error parsing event:', error);
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
  const formatTimestamp = (timestamp?: string) => timestamp ? new Date(timestamp).toLocaleTimeString("en-US", { hour12: false }) : '';

  const RenderableEvent = ({ event }: { event: ProcessedEvent }) => {
    const isExpanded = expandedEvents.has(event.key);

    const renderToolIcon = (toolName: string) => {
        if (toolName.includes('commit') || toolName.includes('push')) return <GitCommitHorizontal size={16} />;
        if (toolName.includes('observe') || toolName.includes('read')) return <Terminal size={16} />;
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
      case 'LLM_THOUGHT':
      case 'ERROR': {
        const isError = event.displayType === 'ERROR';
        return (
          <div className={`event ${isError ? 'simple-event event-error' : 'llm-event'}`}>
            <div className={`event-header ${event.content ? 'clickable' : ''}`} onClick={() => event.content && toggleEventExpansion(event.key)}>
                {event.content && <ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} />}
                <span className='mr-2'>{isError ? <TriangleAlert size={16} className='text-error'/> : <BotMessageSquare size={16} className='text-llm-color'/>}</span>
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
      default: return null;
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
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startTask(); }}}
        />
        <div className="button-group">
          <button onClick={startTask} disabled={isRunning} className={`button button-primary ${isRunning ? 'button-loading' : ''}`}>{isRunning ? 'Running...' : 'Start Task'}</button>
          <button onClick={() => { setRawEvents([]); eventCache.clear(); setStatus('Ready.'); }} disabled={isRunning} className="button button-secondary">Clear</button>
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
