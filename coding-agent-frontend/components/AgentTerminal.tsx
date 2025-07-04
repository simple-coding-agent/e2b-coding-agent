'use client'

import React, { useState, useRef, useEffect, useMemo, useLayoutEffect } from 'react'
import {
  CheckCircle, Loader, TriangleAlert, XCircle, ChevronRight, ChevronUp,
  BotMessageSquare, Terminal, Cog, GitCommitHorizontal, Cloud, BrainCircuit,
  Square // <-- Import the new icon for the stop button
} from 'lucide-react'

// --- Type Definitions ---
interface RawEvent { type: string; timestamp: string; data: any; }
interface ProcessedEventBase { key: string; timestamp: string; raw: RawEvent; }
type TaskLifecycleEvent = ProcessedEventBase & { displayType: 'TASK_LIFECYCLE'; icon: JSX.Element; message: string; };
type ErrorEvent = ProcessedEventBase & { displayType: 'ERROR'; message: string; content?: any; };
type ThoughtEvent = ProcessedEventBase & { displayType: 'LLM_THOUGHT'; text: string; };
type ToolCallEvent = ProcessedEventBase & { displayType: 'TOOL_CALL'; status: 'running' | 'completed' | 'error'; toolName: string; params: any; output?: any; error?: any; };
type ProcessedEvent = TaskLifecycleEvent | ErrorEvent | ThoughtEvent | ToolCallEvent;
type SessionState = 'NO_SESSION' | 'CREATING_SESSION' | 'SESSION_ACTIVE';
interface RepoInfo { name: string; owner: string; isFork: boolean; }
interface Model { id: string; name: string; }
interface ModelGroup { provider: string; models: Model[]; }


// --- Constants ---
const MODEL_GROUPS: ModelGroup[] = [
  { provider: 'OpenAI', models: [{ id: 'openai/gpt-4o', name: 'ChatGPT 4o' }, { id: 'openai/gpt-4.1', name: 'GPT-4.1' },] },
  { provider: 'Anthropic', models: [{ id: 'anthropic/claude-sonnet-4', name: 'Claude Sonnet 4' }, { id: 'anthropic/claude-opus-4', name: 'Claude Opus 4' },] },
  { provider: 'Google', models: [{ id: 'google/gemini-2.5-pro', name: 'Gemini 2.5 Pro' }, { id: 'google/gemini-2.5-flash', name: 'Gemini 2.5 Flash' },] },
  { provider: 'Mistral AI', models: [{ id: 'mistralai/mistral-medium-3', name: 'Mistral Medium 3' },] },
  { provider: 'DeepSeek', models: [{ id: 'deepseek/deepseek-r1-0528', name: 'DeepSeek R1' },] },
  { provider: 'xAI', models: [{ id: 'x-ai/grok-3-mini', name: 'Grok 3 Mini' },] }
];
const API_BASE_URL = 'http://127.0.0.1:8000/api';
const ALL_MODELS = MODEL_GROUPS.flatMap(g => g.models);


// --- Custom Hook for Status Toast ---
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


// --- Main Component ---
export default function AgentTerminal() {
  // Session and Task state
  const [sessionState, setSessionState] = useState<SessionState>('NO_SESSION');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [repoInfo, setRepoInfo] = useState<RepoInfo | null>(null);
  const [isTaskRunning, setIsTaskRunning] = useState(false);
  const [repoUrl, setRepoUrl] = useState<string>('');
  const [selectedModel, setSelectedModel] = useState('openai/gpt-4o');
  const [lastUsedModelId, setLastUsedModelId] = useState<string | null>(null);
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);
  const [hasStartedFirstTask, setHasStartedFirstTask] = useState(false);
  
  // NEW: State for stop functionality
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [isStopping, setIsStopping] = useState(false);

  // Event and UI state
  const [rawEvents, setRawEvents] = useState<RawEvent[]>([]);
  const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
  
  // Refs & Hooks
  const queryRef = useRef<HTMLTextAreaElement>(null);
  const terminalRef = useRef<HTMLDivElement>(null);
  const modelSelectorRef = useRef<HTMLDivElement>(null);
  const eventCache = useRef(new Map<string, ProcessedEvent>()).current;
  const runningTools = useRef(new Map<string, string>()).current;
  const { status, isExiting, showStatus } = useStatusToast();

  const lastUsedModelName = useMemo(() => {
    if (!lastUsedModelId) return null;
    return ALL_MODELS.find(m => m.id === lastUsedModelId)?.name || lastUsedModelId;
  }, [lastUsedModelId]);

  const selectedModelName = useMemo(() => {
    return ALL_MODELS.find(m => m.id === selectedModel)?.name || selectedModel;
  }, [selectedModel]);

  // Effect to close model selector on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (modelSelectorRef.current && !modelSelectorRef.current.contains(event.target as Node)) {
        setIsModelSelectorOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => { document.removeEventListener("mousedown", handleClickOutside); };
  }, [modelSelectorRef]);
  
  // Auto-scroll logic
  useLayoutEffect(() => {
    const terminalEl = terminalRef.current;
    if (terminalEl) {
      const isScrolledToBottom = terminalEl.scrollHeight - terminalEl.scrollTop <= terminalEl.clientHeight + 50;
      if (isScrolledToBottom) {
        terminalEl.scrollTop = terminalEl.scrollHeight;
      }
    }
  }, [rawEvents]);

  // Event processing logic
  const processedEvents = useMemo(() => {
    const filteredRawEvents = rawEvents.filter(event => !event.type.startsWith('repo.') && !event.type.startsWith('setup.'));
    filteredRawEvents.forEach((event, index) => {
      let key = `event-${index}-${event.timestamp}`; if (eventCache.has(key)) return;
      let processed: ProcessedEvent | null = null; let shouldCache = true;
      switch (event.type) { case 'task.start': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <span className='text-success'>▶</span>, message: `Task started: "${event.data.query}"`, raw: event, timestamp: event.timestamp }; break; case 'task.finish': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <CheckCircle size={16} className="text-success" />, message: `Task completed successfully: "${event.data.response}"`, raw: event, timestamp: event.timestamp }; break; case 'task.error': processed = { key, displayType: 'ERROR', message: event.data.error, content: event.data, raw: event, timestamp: event.timestamp }; break; case 'agent.loop.start': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <BotMessageSquare className="text-info" size={16} />, message: "Agent started working on the task", raw: event, timestamp: event.timestamp }; break; case 'llm.thought': processed = { key, displayType: 'LLM_THOUGHT', text: event.data.text, raw: event, timestamp: event.timestamp }; break; case 'llm.tool_call.start': key = `tool-${event.data.tool_name}-${event.timestamp}`; processed = { key, displayType: 'TOOL_CALL', status: 'running', toolName: event.data.tool_name, params: event.data.arguments, raw: event, timestamp: event.timestamp }; runningTools.set(event.data.tool_name, key); break; case 'llm.tool_call.end': const runningToolKey = runningTools.get(event.data.tool_name); if (runningToolKey && eventCache.has(runningToolKey)) { const toolToUpdate = eventCache.get(runningToolKey) as ToolCallEvent; toolToUpdate.status = event.data.was_successful ? 'completed' : 'error'; if (event.data.was_successful) toolToUpdate.output = event.data.response_preview; else toolToUpdate.error = event.data.error; runningTools.delete(event.data.tool_name); } shouldCache = false; break; }
      if (processed && shouldCache) { eventCache.set(processed.key, processed); }
    });
    return Array.from(eventCache.values());
  }, [rawEvents, eventCache, runningTools]);

  const handleTaskEnd = (isError = false) => {
    setIsTaskRunning(false);
    setCurrentTaskId(null);
    setIsStopping(false);
    if (!isError) showStatus('Task finished. Ready for next command.', 'success');
  }

  // Session Creation Logic
  const createSession = async () => {
    if (!repoUrl.trim() || !repoUrl.includes('github.com')) { showStatus('Please enter a valid GitHub repository URL', 'error'); return; }
    setSessionState('CREATING_SESSION');
    showStatus('Setting up repository environment...', 'info');
    eventCache.clear(); runningTools.clear(); setRawEvents([]); setExpandedEvents(new Set()); setLastUsedModelId(null);
    try {
      const response = await fetch(`${API_BASE_URL}/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ repo_url: repoUrl }), });
      if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.detail || `HTTP error! status: ${response.status}`); }
      const data: { session_id: string; repo_owner: string; repo_name: string; is_fork: boolean } = await response.json();
      setSessionId(data.session_id);
      setRepoInfo({ owner: data.repo_owner, name: data.repo_name, isFork: data.is_fork });
      setSessionState('SESSION_ACTIVE');
      setHasStartedFirstTask(false); 
      showStatus(data.is_fork ? 'Repository forked and ready.' : 'Repository connected and ready.', 'success');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      showStatus(`Session setup failed: ${errorMessage}`, 'error');
      setSessionState('NO_SESSION');
    }
  };

  const startTask = async () => {
    const query = queryRef.current?.value.trim();
    if (!query || !sessionId || isTaskRunning) return;

    setHasStartedFirstTask(true);
    setLastUsedModelId(selectedModel);
    
    runningTools.clear();
    setExpandedEvents(new Set());

    setIsTaskRunning(true);
    showStatus('Agent starting...', 'info');

    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/tasks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query, model: selectedModel }), });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data: { task_id: string } = await response.json();
      
      setCurrentTaskId(data.task_id); // <-- STORE THE TASK ID
      
      if (queryRef.current) queryRef.current.value = '';
      const eventSource = new EventSource(`${API_BASE_URL}/tasks/${data.task_id}/events`);
      eventSource.onmessage = (e) => { const event: RawEvent = JSON.parse(e.data); if (event.type === 'stream.keepalive') return; setRawEvents(prev => [...prev, event]); switch (event.type) { case 'llm.thought': showStatus('Agent is thinking...', 'info'); break; case 'llm.tool_call.start': showStatus(`Executing: ${event.data.tool_name}`, 'info'); break; case 'task.finish': eventSource.close(); handleTaskEnd(); break; case 'task.error': showStatus(event.data.error || 'An unknown error occurred', 'error'); eventSource.close(); handleTaskEnd(true); break; } };
      eventSource.onerror = () => { showStatus('Stream connection lost.', 'error'); eventSource.close(); handleTaskEnd(true); };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      showStatus(`Failed to start task: ${errorMessage}`, 'error');
      handleTaskEnd(true);
    }
  };

  // NEW: Function to stop the currently running task
  const stopTask = async () => {
    if (!currentTaskId || isStopping) return;

    setIsStopping(true);
    showStatus('Sending stop signal...', 'info');
    try {
      const response = await fetch(`${API_BASE_URL}/tasks/${currentTaskId}/stop`, { method: 'POST' });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to send stop signal.");
      }
      showStatus('Stop signal accepted. Waiting for agent to terminate.', 'success');
      // The `task.finish` event from the stream will call `handleTaskEnd`, cleaning up the UI state.
    } catch (error) {
       const errorMessage = error instanceof Error ? error.message : String(error);
       showStatus(`Stop request failed: ${errorMessage}`, 'error');
       setIsStopping(false); // Re-enable the button if the API call itself fails
    }
  };

  // --- Reusable UI Render Functions ---
  const toggleEventExpansion = (key: string) => { setExpandedEvents(prev => { const newSet = new Set(prev); if (newSet.has(key)) newSet.delete(key); else newSet.add(key); return newSet; }); };
  const formatJson = (data: any) => JSON.stringify(data, null, 2);
  const formatTimestamp = (timestamp?: string) => timestamp ? new Date(timestamp).toLocaleTimeString("en-US", { hour12: false }) : '';
  const RenderableEvent = React.memo(({ event }: { event: ProcessedEvent }) => { const isExpanded = expandedEvents.has(event.key); const renderToolIcon = (toolName: string) => { if (toolName.includes('commit')) return <GitCommitHorizontal size={16} />; if (toolName.includes('observe') || toolName.includes('write')) return <Terminal size={16} />; return <Cog size={16} />; }; switch (event.displayType) { case 'LLM_THOUGHT': return (<div className="event thought-event"><div className="event-header"><span className='mr-2'><BrainCircuit size={16} /></span><span>Agent thought:</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div><div className='event-content'><p>{event.text}</p></div></div>); case 'TOOL_CALL': const StatusIcon = { running: <Loader className="animate-spin text-info" size={16} />, completed: <CheckCircle className="text-success" size={16} />, error: <XCircle className="text-error" size={16} />, }[event.status]; return (<div className={`event tool-call-event status-${event.status}`}><div className="event-header clickable" onClick={() => toggleEventExpansion(event.key)}><ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} /><span className="tool-status-icon">{StatusIcon}</span><span className="tool-icon">{renderToolIcon(event.toolName)}</span><span className="event-tool">{event.toolName}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div>{isExpanded && (<div className="tool-details"><h4 className="tool-section-header">Parameters</h4><pre className="tool-section-content">{formatJson(event.params)}</pre>{event.output && (<><h4 className="tool-section-header">Output Preview</h4><pre className="tool-section-content">{event.output}</pre></>)}{event.error && (<><h4 className="tool-section-header text-error">Error</h4><pre className="tool-section-content">{formatJson(event.error)}</pre></>)}</div>)}</div>); case 'ERROR': return (<div className="event simple-event event-error"><div className="event-header clickable" onClick={() => toggleEventExpansion(event.key)}><ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} /><span className='mr-2'><TriangleAlert size={16} /></span><span>{event.message}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div>{isExpanded && <pre className="event-data">{formatJson(event.content)}</pre>}</div>); case 'TASK_LIFECYCLE': return (<div className="event simple-event"><div className="event-header"><span className='mr-2'>{event.icon}</span><span>{event.message}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div></div>); default: return null; } });
  RenderableEvent.displayName = 'RenderableEvent';


  const renderRepoStatusBar = () => repoInfo && (
    <div className="repo-status-bar">
      <div className="repo-info">
        {!hasStartedFirstTask ? (
          <>
            <CheckCircle size={14} className="text-success" />
            <span>
              Repository <strong>{repoInfo.owner}/{repoInfo.name}</strong> {repoInfo.isFork ? 'forked and' : ''} clonned into the sandbox
            </span>
          </>
        ) : (
          <span>Working on <strong>{repoInfo.owner}/{repoInfo.name}</strong></span>
        )}
      </div>
      {hasStartedFirstTask && repoInfo.isFork && (
        <div className="fork-badge">
          <GitCommitHorizontal size={14} />
          <span>Fork</span>
        </div>
      )}
    </div>
  );

  const renderInputArea = () => (
    <div className="input-section">
      <div className="input-container">
        <div className="model-selector" ref={modelSelectorRef}>
          <button className="model-selector-trigger" onClick={() => setIsModelSelectorOpen(!isModelSelectorOpen)} disabled={isTaskRunning}>
            <span>{selectedModelName}</span>
            <ChevronUp size={16} className={`model-selector-chevron ${isModelSelectorOpen ? 'open' : ''}`} />
          </button>
          {isModelSelectorOpen && (
            <div className="model-selector-panel">
              {MODEL_GROUPS.map(group => (
                <div key={group.provider} className="model-group">
                  <div className="model-group-label">{group.provider}</div>
                  {group.models.map(model => (
                    <div key={model.id} className={`model-option ${selectedModel === model.id ? 'selected' : ''}`} onClick={() => { setSelectedModel(model.id); setIsModelSelectorOpen(false); }}>
                      {model.name}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>
        <textarea ref={queryRef} placeholder="Describe the task for the AI agent..." disabled={isTaskRunning} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startTask(); }}} />
        <button onClick={startTask} disabled={isTaskRunning} className={`submit-button ${isTaskRunning ? 'loading' : ''}`} title="Start Task (Enter)">{'>'}</button>
      </div>
    </div>
  );

  const renderTerminal = () => (
    <div className="terminal-container">
      <div className="terminal-header">
        <div className='header-left'>
            <Cloud size={16} /> 
            <span>Agent Stream</span>
            {lastUsedModelName && (<span className="model-display-name">- {lastUsedModelName}</span>)}
        </div>
        {isTaskRunning && (
            <div className="header-right">
                <div className="loading-indicator">
                    <span /><span /><span />
                </div>
                {}
                <div 
                  className={`stop-control ${isStopping ? 'disabled' : ''}`}
                  onClick={stopTask} 
                  title="Stop the current task"
                >
                  <Square size={12} />
                  <span>Stop</span>
                </div>
            </div>
        )}
      </div>
      <div className="terminal" ref={terminalRef}>
        {processedEvents.map(event => <RenderableEvent key={event.key} event={event} />)}
      </div>
    </div>
  );

  // --- Main Render Logic ---
  if (sessionState !== 'SESSION_ACTIVE') {
    return (
      <div className="setup-container">
        <div className="setup-box">
          <div className="input-container">
            <input type="text" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/owner/repository-name" className="repo-input" disabled={sessionState === 'CREATING_SESSION'} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); createSession(); }}} />
            <button onClick={createSession} disabled={sessionState === 'CREATING_SESSION'} className={`submit-button ${sessionState === 'CREATING_SESSION' ? 'loading' : ''}`} title="Start Session (Enter)">
              {sessionState === 'CREATING_SESSION' ? <Loader className="animate-spin" size={20} /> : '>'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`agent-terminal-wrapper ${!hasStartedFirstTask ? 'pre-task-mode' : 'task-mode'}`}>
      {!hasStartedFirstTask ? (
        <div className="pre-task-container">
          {renderRepoStatusBar()}
          {renderInputArea()}
        </div>
      ) : (
        <div className="main-view-container">
          {renderRepoStatusBar()}
          {renderTerminal()}
          {renderInputArea()}
        </div>
      )}
      {status && (<div className={`status-toast ${status.type} ${isExiting ? 'exiting' : ''}`}><div className="status-indicator" /><span>{status.message}</span></div>)}
    </div>
  );
}
