'use client'

import React, { useState, useRef, useEffect, useMemo } from 'react'
import {
  CheckCircle, Loader, TriangleAlert, XCircle, ChevronRight,
  BotMessageSquare, Terminal, Cog, GitCommitHorizontal, Cloud, BrainCircuit
} from 'lucide-react'

// --- Interfaces and Types ---

interface RawEvent {
  type: string;
  timestamp: string;
  data: any;
}

// A base type for all processed events
interface ProcessedEventBase {
  key: string;
  timestamp: string;
  raw: RawEvent;
}

// Specific types for each kind of displayable event
type TaskLifecycleEvent = ProcessedEventBase & { displayType: 'TASK_LIFECYCLE'; icon: JSX.Element; message: string; };
type SetupEvent = ProcessedEventBase & { displayType: 'SETUP'; icon: JSX.Element; message: string; };
type ErrorEvent = ProcessedEventBase & { displayType: 'ERROR'; message: string; content?: any; };
type ThoughtEvent = ProcessedEventBase & { displayType: 'LLM_THOUGHT'; text: string; };
type ToolCallEvent = ProcessedEventBase & {
  displayType: 'TOOL_CALL';
  status: 'running' | 'completed' | 'error';
  toolName: string;
  params: any;
  output?: any;
  error?: any;
};

// A union of all possible processed event types
type ProcessedEvent = TaskLifecycleEvent | SetupEvent | ErrorEvent | ThoughtEvent | ToolCallEvent;


export default function AgentTerminal() {
  const [rawEvents, setRawEvents] = useState<RawEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [query, setQuery] = useState('Create a simple README.md file with project information, then commit and push it.');
  const [status, setStatus] = useState('Ready.');
  const [statusType, setStatusType] = useState<'info' | 'error'>('info');
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  const terminalRef = useRef<HTMLDivElement>(null);

  // Refs for state that shouldn't trigger re-renders on its own
  const eventCache = useRef(new Map<string, ProcessedEvent>()).current;
  const runningTools = useRef(new Map<string, string>()).current; // Maps toolName to the key of its 'running' event

  // Auto-scroll to bottom of the terminal on new events
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [rawEvents]);

  // The core logic to process raw server events into a stable, renderable list.
  const processedEvents = useMemo(() => {
    rawEvents.forEach((event, index) => {
      let key = `event-${index}-${event.timestamp}`;

      // Skip if this event object has already been processed and cached.
      if (eventCache.has(key)) return;

      let processed: ProcessedEvent | null = null;
      let shouldCache = true;

      // **FIX: Switch on the full, explicit event type for reliability.**
      // This avoids all the ambiguity of splitting the string.
      switch (event.type) {
        case 'task.start':
          processed = { key, displayType: 'TASK_LIFECYCLE', icon: <span className='text-success'>▶</span>, message: `Task started: "${event.data.query}"`, raw: event, timestamp: event.timestamp };
          break;
        case 'task.finish':
          processed = { key, displayType: 'TASK_LIFECYCLE', icon: <CheckCircle className="text-success" />, message: `Task completed successfully (${event.data.total_iterations} iterations)`, raw: event, timestamp: event.timestamp };
          break;
        case 'task.error':
          processed = { key, displayType: 'ERROR', message: event.data.error, content: event.data, raw: event, timestamp: event.timestamp };
          break;
        case 'setup.sandbox.end':
        case 'setup.repo.end':
        case 'setup.model.end':
          processed = { key, displayType: 'SETUP', icon: <CheckCircle className="text-success" size={16} />, message: event.data.message, raw: event, timestamp: event.timestamp };
          break;
        case 'agent.loop.start':
          processed = { key, displayType: 'TASK_LIFECYCLE', icon: <BotMessageSquare className="text-info" size={16} />, message: "Agent started working on the task", raw: event, timestamp: event.timestamp };
          break;
        case 'llm.thought':
          processed = { key, displayType: 'LLM_THOUGHT', text: event.data.text, raw: event, timestamp: event.timestamp };
          break;
        case 'llm.tool_call.start':
          key = `tool-${event.data.tool_name}-${event.timestamp}`; // Make the key unique for this call
          processed = {
            key,
            displayType: 'TOOL_CALL',
            status: 'running',
            toolName: event.data.tool_name,
            // **FIX: Use `event.data.arguments`, not `event.data.params`**
            params: event.data.arguments,
            raw: event,
            timestamp: event.timestamp
          };
          // Track the key of this running tool to update it later
          runningTools.set(event.data.tool_name, key);
          break;

        case 'llm.tool_call.end':
          const runningToolKey = runningTools.get(event.data.tool_name);
          if (runningToolKey && eventCache.has(runningToolKey)) {
            const toolToUpdate = eventCache.get(runningToolKey) as ToolCallEvent;
            // Update the existing event in the cache directly
            toolToUpdate.status = event.data.was_successful ? 'completed' : 'error';
            if (event.data.was_successful) {
              toolToUpdate.output = event.data.response_preview;
            } else {
              toolToUpdate.error = event.data.error;
            }
            // This tool is no longer running
            runningTools.delete(event.data.tool_name);
          }
          // An 'end' event only updates an existing event, it doesn't create a new one.
          shouldCache = false;
          break;
      }
      
      if (processed && shouldCache) {
        eventCache.set(processed.key, processed);
      }
    });
    
    // Return the processed events from the cache as a new array to trigger re-render
    return Array.from(eventCache.values());
  }, [rawEvents, eventCache, runningTools]);

  const startTask = async () => {
    if (!query.trim()) {
      setStatus('Please enter a query');
      setStatusType('error');
      return;
    }

    // Reset state completely for a new run
    eventCache.clear();
    runningTools.clear();
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
        const event: RawEvent = JSON.parse(e.data);
        if (event.type === 'stream.keepalive') return;
        
        setRawEvents(prev => [...prev, event]);

        // Update the live status bar based on the full event type
        switch (event.type) {
            case 'setup.repo.end':
            case 'setup.sandbox.end':
                setStatus(event.data.message);
                break;
            case 'llm.thought':
                setStatus('Agent is thinking...');
                break;
            case 'llm.tool_call.start':
                setStatus(`Executing: ${event.data.tool_name}`);
                break;
            case 'llm.tool_call.end':
                 setStatus(`Completed: ${event.data.tool_name}`);
                break;
            case 'task.finish':
                setStatus('Task completed successfully!');
                setStatusType('info');
                break;
            case 'task.end':
                eventSource.close();
                setIsRunning(false);
                break;
            case 'task.error':
                setStatus(`Error: ${event.data.error || 'Unknown error'}`);
                setStatusType('error');
                eventSource.close();
                setIsRunning(false);
                break;
        }
      };

      eventSource.onerror = () => {
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

  // A memoized component for rendering a single event to prevent re-renders
  const RenderableEvent = React.memo(({ event }: { event: ProcessedEvent }) => {
    const isExpanded = expandedEvents.has(event.key);

    const renderToolIcon = (toolName: string) => {
      if (toolName.includes('commit') || toolName.includes('push')) 
        return <GitCommitHorizontal size={16} />;
      if (toolName.includes('observe') || toolName.includes('read') || toolName.includes('write')) 
        return <Terminal size={16} />;
      return <Cog size={16} />;
    }

    switch (event.displayType) {
      case 'LLM_THOUGHT':
        return (
          <div className="event thought-event">
            <div className="event-header">
                <span className='mr-2'><BrainCircuit size={16} className='text-purple-400' /></span>
                <span className='event-message'>Agent thought:</span>
                <span className="event-timestamp">{formatTimestamp(event.timestamp)}</span>
            </div>
            <div className='event-content markdown'>
                <p>{event.text}</p>
            </div>
          </div>
        )
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
                <h4 className="tool-section-header">Parameters</h4>
                <pre className="tool-section-content">{formatJson(event.params)}</pre>
                {event.output && (
                    <><h4 className="tool-section-header">Output</h4><pre className="tool-section-content">{formatJson(event.output)}</pre></>
                )}
                {event.error && (
                    <><h4 className="tool-section-header text-error">Error</h4><pre className="tool-section-content">{formatJson(event.error)}</pre></>
                )}
              </div>
            )}
          </div>
        );
      }
      
      case 'ERROR': {
        return (
          <div className="event simple-event event-error">
            <div className={`event-header ${event.content ? 'clickable' : ''}`} onClick={() => event.content && toggleEventExpansion(event.key)}>
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
  });
  RenderableEvent.displayName = 'RenderableEvent';
  
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
          <button onClick={startTask} disabled={isRunning} className={`button button-primary ${isRunning ? 'button-loading' : ''}`}>
            {isRunning ? 'Running...' : 'Start Task'}
          </button>
          <button onClick={() => { setRawEvents([]); eventCache.clear(); runningTools.clear(); setStatus('Ready.'); }} disabled={isRunning} className="button button-secondary">
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
