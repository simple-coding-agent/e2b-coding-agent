'use client'

import React, { useState, useRef, useEffect, useMemo, useLayoutEffect } from 'react'
import {
  CheckCircle, Loader, TriangleAlert, XCircle, ChevronRight,
  BotMessageSquare, Terminal, Cog, GitCommitHorizontal, Cloud, BrainCircuit
} from 'lucide-react'

// --- Interfaces and Types --- (No changes here)

interface RawEvent { type: string; timestamp: string; data: any; }
interface ProcessedEventBase { key: string; timestamp: string; raw: RawEvent; }
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
type ProcessedEvent = TaskLifecycleEvent | SetupEvent | ErrorEvent | ThoughtEvent | ToolCallEvent;

// --- Custom Hook for Status Toast --- (No changes here)
function useStatusToast() {
  const [status, setStatus] = useState<{ message: string; type: 'info' | 'error' | 'success' } | null>(null);
  const [isExiting, setIsExiting] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (status) {
      setIsExiting(false);
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        setIsExiting(true);
        setTimeout(() => setStatus(null), 300);
      }, 4000);
    }
  }, [status]);

  const showStatus = (message: string, type: 'info' | 'error' | 'success') => { setStatus({ message, type }); };
  return { status, isExiting, showStatus };
}


export default function AgentTerminal() {
  const [rawEvents, setRawEvents] = useState<RawEvent[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [hasRunOnce, setHasRunOnce] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());

  const queryRef = useRef<HTMLTextAreaElement>(null);
  const { status, isExiting, showStatus } = useStatusToast();
  const terminalRef = useRef<HTMLDivElement>(null);
  const eventCache = useRef(new Map<string, ProcessedEvent>()).current;
  const runningTools = useRef(new Map<string, string>()).current;

  // REVISED: Smarter auto-scroll that only scrolls if user is already at the bottom.
  // We use useLayoutEffect to run this after the DOM has been updated but before the browser has painted.
  useLayoutEffect(() => {
    const terminalEl = terminalRef.current;
    if (terminalEl) {
      // A buffer to consider the user "at the bottom" even if they're a few pixels off.
      const isScrolledToBottom = terminalEl.scrollHeight - terminalEl.scrollTop <= terminalEl.clientHeight + 50;
      
      // If the user was at the bottom before the new message, stay at the bottom.
      if (isScrolledToBottom) {
        terminalEl.scrollTop = terminalEl.scrollHeight;
      }
    }
  }, [rawEvents]);

  // Logic for processing raw events into a displayable format (No changes here)
  const processedEvents = useMemo(() => {
    rawEvents.forEach((event, index) => {
      let key = `event-${index}-${event.timestamp}`;
      if (eventCache.has(key)) return;
      let processed: ProcessedEvent | null = null;
      let shouldCache = true;
      switch (event.type) { case 'task.start': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <span className='text-success'>▶</span>, message: `Task started: "${event.data.query}"`, raw: event, timestamp: event.timestamp }; break; case 'task.finish': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <CheckCircle className="text-success" />, message: `Task completed successfully (${event.data.total_iterations} iterations)`, raw: event, timestamp: event.timestamp }; break; case 'task.error': processed = { key, displayType: 'ERROR', message: event.data.error, content: event.data, raw: event, timestamp: event.timestamp }; break; case 'setup.sandbox.end': case 'setup.repo.end': case 'setup.model.end': processed = { key, displayType: 'SETUP', icon: <CheckCircle className="text-success" size={16} />, message: event.data.message, raw: event, timestamp: event.timestamp }; break; case 'agent.loop.start': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <BotMessageSquare className="text-info" size={16} />, message: "Agent started working on the task", raw: event, timestamp: event.timestamp }; break; case 'llm.thought': processed = { key, displayType: 'LLM_THOUGHT', text: event.data.text, raw: event, timestamp: event.timestamp }; break; case 'llm.tool_call.start': key = `tool-${event.data.tool_name}-${event.timestamp}`; processed = { key, displayType: 'TOOL_CALL', status: 'running', toolName: event.data.tool_name, params: event.data.arguments, raw: event, timestamp: event.timestamp }; runningTools.set(event.data.tool_name, key); break; case 'llm.tool_call.end': const runningToolKey = runningTools.get(event.data.tool_name); if (runningToolKey && eventCache.has(runningToolKey)) { const toolToUpdate = eventCache.get(runningToolKey) as ToolCallEvent; toolToUpdate.status = event.data.was_successful ? 'completed' : 'error'; if (event.data.was_successful) toolToUpdate.output = event.data.response_preview; else toolToUpdate.error = event.data.error; runningTools.delete(event.data.tool_name); } shouldCache = false; break; }
      if (processed && shouldCache) { eventCache.set(processed.key, processed); }
    });
    return Array.from(eventCache.values());
  }, [rawEvents, eventCache, runningTools]);

  const handleTaskEnd = (isError = false) => {
    setIsRunning(false);
    if (!isError) showStatus('Task finished. Ready for next command.', 'success');
  }

  const startTask = async () => {
    const query = queryRef.current?.value.trim();
    if (!query) { showStatus('Please enter a task', 'error'); return; }
    if (!hasRunOnce) setHasRunOnce(true);
    eventCache.clear(); runningTools.clear(); setRawEvents([]); setExpandedEvents(new Set());
    setIsRunning(true); showStatus('Agent starting...', 'info');

    try {
      const response = await fetch('http://127.0.0.1:8000/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, model: 'openai/gpt-4o' }), });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      if (queryRef.current) { queryRef.current.value = ''; }
      const eventSource = new EventSource(`http://127.0.0.1:8000/tasks/${data.task_id}/events`);
      eventSource.onmessage = (e) => {
        const event: RawEvent = JSON.parse(e.data);
        if (event.type === 'stream.keepalive') return;
        setRawEvents(prev => [...prev, event]);
        switch (event.type) { case 'llm.thought': showStatus('Agent is thinking...', 'info'); break; case 'llm.tool_call.start': showStatus(`Executing: ${event.data.tool_name}`, 'info'); break; case 'llm.tool_call.end': if (event.data.was_successful) showStatus(`Completed: ${event.data.tool_name}`, 'success'); break; case 'task.end': eventSource.close(); handleTaskEnd(); break; case 'task.error': showStatus(event.data.error || 'An unknown error occurred', 'error'); eventSource.close(); handleTaskEnd(true); break; }
      };
      eventSource.onerror = () => { showStatus('Stream connection lost.', 'error'); eventSource.close(); handleTaskEnd(true); };
    } catch (error) { const errorMessage = error instanceof Error ? error.message : String(error); showStatus(`Failed to start task: ${errorMessage}`, 'error'); handleTaskEnd(true); }
  };

  const toggleEventExpansion = (key: string) => { setExpandedEvents(prev => { const newSet = new Set(prev); if (newSet.has(key)) newSet.delete(key); else newSet.add(key); return newSet; }); };
  const formatJson = (data: any) => JSON.stringify(data, null, 2);
  const formatTimestamp = (timestamp?: string) => timestamp ? new Date(timestamp).toLocaleTimeString("en-US", { hour12: false }) : '';
  const RenderableEvent = React.memo(({ event }: { event: ProcessedEvent }) => { const isExpanded = expandedEvents.has(event.key); const renderToolIcon = (toolName: string) => { if (toolName.includes('commit')) return <GitCommitHorizontal size={16} />; if (toolName.includes('observe') || toolName.includes('write')) return <Terminal size={16} />; return <Cog size={16} />; }; switch (event.displayType) { case 'LLM_THOUGHT': return (<div className="event thought-event"><div className="event-header"><span className='mr-2'><BrainCircuit size={16} /></span><span>Agent thought:</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div><div className='event-content'><p>{event.text}</p></div></div>); case 'TOOL_CALL': const StatusIcon = { running: <Loader className="animate-spin text-info" size={16} />, completed: <CheckCircle className="text-success" size={16} />, error: <XCircle className="text-error" size={16} />, }[event.status]; return (<div className={`event tool-call-event status-${event.status}`}><div className="event-header clickable" onClick={() => toggleEventExpansion(event.key)}><ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} /><span className="tool-status-icon">{StatusIcon}</span><span className="tool-icon">{renderToolIcon(event.toolName)}</span><span className="event-tool">{event.toolName}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div>{isExpanded && (<div className="tool-details"><h4 className="tool-section-header">Parameters</h4><pre className="tool-section-content">{formatJson(event.params)}</pre>{event.output && (<><h4 className="tool-section-header">Output Preview</h4><pre className="tool-section-content">{event.output}</pre></>)}{event.error && (<><h4 className="tool-section-header text-error">Error</h4><pre className="tool-section-content">{formatJson(event.error)}</pre></>)}</div>)}</div>); case 'ERROR': return (<div className="event simple-event event-error"><div className="event-header clickable" onClick={() => toggleEventExpansion(event.key)}><ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} /><span className='mr-2'><TriangleAlert size={16} /></span><span>{event.message}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div>{isExpanded && <pre className="event-data">{formatJson(event.content)}</pre>}</div>); case 'SETUP': case 'TASK_LIFECYCLE': return (<div className="event simple-event"><div className="event-header"><span className='mr-2'>{event.icon}</span><span>{event.message}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div></div>); default: return null; } });
  RenderableEvent.displayName = 'RenderableEvent';

  return (
    <div className={`agent-terminal-wrapper ${!hasRunOnce ? 'idle' : ''}`}>
      {hasRunOnce && (
        <div className="terminal-container">
          <div className="terminal-header"><Cloud size={16} /> Agent Stream</div>
          <div className="terminal" ref={terminalRef}>
            {processedEvents.map(event => <RenderableEvent key={event.key} event={event} />)}
          </div>
        </div>
      )}

      {!isRunning && (
        <div className="input-section">
          <div className="input-container">
            <textarea
              ref={queryRef}
              placeholder={
                hasRunOnce
                  ? "Enter a follow-up command or a new task..."
                  : "Describe the task for the AI agent..."
              }
              disabled={isRunning}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startTask(); } }}
            />
            <button
              onClick={startTask}
              disabled={isRunning}
              className={`submit-button ${isRunning ? 'loading' : ''}`}
              title="Start Task (Enter)">
              {'>'}
            </button>
          </div>
        </div>
      )}

      {status && (
        <div className={`status-toast ${status.type} ${isExiting ? 'exiting' : ''}`}>
          <div className="status-indicator" />
          <span>{status.message}</span>
        </div>
      )}
    </div>
  );
}
