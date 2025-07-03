'use client'

import React, { useState, useRef, useEffect, useMemo, useLayoutEffect } from 'react'
import {
  CheckCircle, Loader, TriangleAlert, XCircle, ChevronRight, ChevronUp,
  BotMessageSquare, Terminal, Cog, GitCommitHorizontal, Cloud, BrainCircuit, Github, Server, Link
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
  {
    provider: 'OpenAI',
    models: [
      { id: 'openai/gpt-4o', name: 'ChatGPT 4o' },
      { id: 'openai/gpt-4.1', name: 'GPT-4.1' },
    ]
  },
  {
    provider: 'Anthropic',
    models: [
      { id: 'anthropic/claude-sonnet-4', name: 'Claude Sonnet 4' },
      { id: 'anthropic/claude-opus-4', name: 'Claude Opus 4' },
    ]
  },
  {
    provider: 'Google',
    models: [
      { id: 'google/gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
      { id: 'google/gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
    ]
  },
  {
    provider: 'Mistral AI',
    models: [
      { id: 'mistralai/mistral-medium-3', name: 'Mistral Medium 3' },
    ]
  },
  {
    provider: 'DeepSeek',
    models: [
      { id: 'deepseek/deepseek-r1-0528', name: 'DeepSeek R1' },
    ]
  },
  {
    provider: 'xAI',
    models: [
      { id: 'x-ai/grok-3-mini', name: 'Grok 3 Mini' },
    ]
  }
];
const API_BASE_URL = 'http://127.0.0.1:8000/api';
const ALL_MODELS = MODEL_GROUPS.flatMap(g => g.models);


// --- Custom Hook for Status Toast (Unchanged) ---
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
  const [repoUrl, setRepoUrl] = useState<string>('https://github.com/simple-coding-agent/playground_repo');
  const [selectedModel, setSelectedModel] = useState('openai/gpt-4o');
  const [lastUsedModelId, setLastUsedModelId] = useState<string | null>(null);
  const [isModelSelectorOpen, setIsModelSelectorOpen] = useState(false);

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
  
  // Auto-scroll logic (Unchanged)
  useLayoutEffect(() => {
    const terminalEl = terminalRef.current;
    if (terminalEl) {
      const isScrolledToBottom = terminalEl.scrollHeight - terminalEl.scrollTop <= terminalEl.clientHeight + 50;
      if (isScrolledToBottom) {
        terminalEl.scrollTop = terminalEl.scrollHeight;
      }
    }
  }, [rawEvents]);

  // Event processing logic (Unchanged)
  const processedEvents = useMemo(() => {
    const filteredRawEvents = rawEvents.filter(event => 
        !event.type.startsWith('repo.') && 
        !event.type.startsWith('setup.')
    );

    filteredRawEvents.forEach((event, index) => {
      let key = `event-${index}-${event.timestamp}`;
      if (eventCache.has(key)) return;

      let processed: ProcessedEvent | null = null;
      let shouldCache = true;

      switch (event.type) { 
        case 'task.start': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <span className='text-success'>▶</span>, message: `Task started: "${event.data.query}"`, raw: event, timestamp: event.timestamp }; break; 
        case 'task.finish': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <CheckCircle className="text-success" />, message: `Task completed successfully (${event.data.total_iterations} iterations)`, raw: event, timestamp: event.timestamp }; break; 
        case 'task.error': processed = { key, displayType: 'ERROR', message: event.data.error, content: event.data, raw: event, timestamp: event.timestamp }; break; 
        case 'agent.loop.start': processed = { key, displayType: 'TASK_LIFECYCLE', icon: <BotMessageSquare className="text-info" size={16} />, message: "Agent started working on the task", raw: event, timestamp: event.timestamp }; break; 
        case 'llm.thought': processed = { key, displayType: 'LLM_THOUGHT', text: event.data.text, raw: event, timestamp: event.timestamp }; break; 
        case 'llm.tool_call.start': key = `tool-${event.data.tool_name}-${event.timestamp}`; processed = { key, displayType: 'TOOL_CALL', status: 'running', toolName: event.data.tool_name, params: event.data.arguments, raw: event, timestamp: event.timestamp }; runningTools.set(event.data.tool_name, key); break; 
        case 'llm.tool_call.end': const runningToolKey = runningTools.get(event.data.tool_name); if (runningToolKey && eventCache.has(runningToolKey)) { const toolToUpdate = eventCache.get(runningToolKey) as ToolCallEvent; toolToUpdate.status = event.data.was_successful ? 'completed' : 'error'; if (event.data.was_successful) toolToUpdate.output = event.data.response_preview; else toolToUpdate.error = event.data.error; runningTools.delete(event.data.tool_name); } shouldCache = false; break; 
      }
      if (processed && shouldCache) { eventCache.set(processed.key, processed); }
    });
    return Array.from(eventCache.values());
  }, [rawEvents, eventCache, runningTools]);

  const handleTaskEnd = (isError = false) => {
    setIsTaskRunning(false);
    if (!isError) showStatus('Task finished. Ready for next command.', 'success');
  }

  // Session Creation Logic (Unchanged)
  const createSession = async () => {
    if (!repoUrl.trim() || !repoUrl.includes('github.com')) {
      showStatus('Please enter a valid GitHub repository URL', 'error');
      return;
    }
    setSessionState('CREATING_SESSION');
    showStatus('Setting up repository environment...', 'info');
    eventCache.clear();
    runningTools.clear();
    setRawEvents([]);
    setExpandedEvents(new Set());
    setLastUsedModelId(null);

    try {
      const response = await fetch(`${API_BASE_URL}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_url: repoUrl }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }

      const data: { session_id: string; repo_owner: string; repo_name: string; is_fork: boolean } = await response.json();
      setSessionId(data.session_id);
      setRepoInfo({ owner: data.repo_owner, name: data.repo_name, isFork: data.is_fork });
      setSessionState('SESSION_ACTIVE');
      showStatus(data.is_fork ? 'Repository forked and ready.' : 'Repository connected and ready.', 'success');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      showStatus(`Session setup failed: ${errorMessage}`, 'error');
      setSessionState('NO_SESSION');
    }
  };

  // Task Starting Logic (Unchanged)
  const startTask = async () => {
    const query = queryRef.current?.value.trim();
    if (!query || !sessionId) return;
    setLastUsedModelId(selectedModel);
    
    eventCache.clear();
    runningTools.clear();
    setRawEvents([]);
    setExpandedEvents(new Set());
    setIsTaskRunning(true);
    showStatus('Agent starting...', 'info');

    try {
      const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, model: selectedModel }),
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const data = await response.json();
      if (queryRef.current) queryRef.current.value = '';

      const eventSource = new EventSource(`${API_BASE_URL}/tasks/${data.task_id}/events`);
      eventSource.onmessage = (e) => {
        const event: RawEvent = JSON.parse(e.data);
        if (event.type === 'stream.keepalive') return;
        setRawEvents(prev => [...prev, event]);
        switch (event.type) { 
          case 'llm.thought': showStatus('Agent is thinking...', 'info'); break; 
          case 'llm.tool_call.start': showStatus(`Executing: ${event.data.tool_name}`, 'info'); break; 
          case 'task.end': eventSource.close(); handleTaskEnd(); break; 
          case 'task.error': showStatus(event.data.error || 'An unknown error occurred', 'error'); eventSource.close(); handleTaskEnd(true); break; 
        }
      };
      eventSource.onerror = () => { showStatus('Stream connection lost.', 'error'); eventSource.close(); handleTaskEnd(true); };
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      showStatus(`Failed to start task: ${errorMessage}`, 'error');
      handleTaskEnd(true);
    }
  };

  // --- UI Components ---
  const toggleEventExpansion = (key: string) => { setExpandedEvents(prev => { const newSet = new Set(prev); if (newSet.has(key)) newSet.delete(key); else newSet.add(key); return newSet; }); };
  const formatJson = (data: any) => JSON.stringify(data, null, 2);
  const formatTimestamp = (timestamp?: string) => timestamp ? new Date(timestamp).toLocaleTimeString("en-US", { hour12: false }) : '';
  const RenderableEvent = React.memo(({ event }: { event: ProcessedEvent }) => { const isExpanded = expandedEvents.has(event.key); const renderToolIcon = (toolName: string) => { if (toolName.includes('commit')) return <GitCommitHorizontal size={16} />; if (toolName.includes('observe') || toolName.includes('write')) return <Terminal size={16} />; return <Cog size={16} />; }; switch (event.displayType) { case 'LLM_THOUGHT': return (<div className="event thought-event"><div className="event-header"><span className='mr-2'><BrainCircuit size={16} /></span><span>Agent thought:</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div><div className='event-content'><p>{event.text}</p></div></div>); case 'TOOL_CALL': const StatusIcon = { running: <Loader className="animate-spin text-info" size={16} />, completed: <CheckCircle className="text-success" size={16} />, error: <XCircle className="text-error" size={16} />, }[event.status]; return (<div className={`event tool-call-event status-${event.status}`}><div className="event-header clickable" onClick={() => toggleEventExpansion(event.key)}><ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} /><span className="tool-status-icon">{StatusIcon}</span><span className="tool-icon">{renderToolIcon(event.toolName)}</span><span className="event-tool">{event.toolName}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div>{isExpanded && (<div className="tool-details"><h4 className="tool-section-header">Parameters</h4><pre className="tool-section-content">{formatJson(event.params)}</pre>{event.output && (<><h4 className="tool-section-header">Output Preview</h4><pre className="tool-section-content">{event.output}</pre></>)}{event.error && (<><h4 className="tool-section-header text-error">Error</h4><pre className="tool-section-content">{formatJson(event.error)}</pre></>)}</div>)}</div>); case 'ERROR': return (<div className="event simple-event event-error"><div className="event-header clickable" onClick={() => toggleEventExpansion(event.key)}><ChevronRight className={`expand-icon ${isExpanded ? 'expanded' : ''}`} size={16} /><span className='mr-2'><TriangleAlert size={16} /></span><span>{event.message}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div>{isExpanded && <pre className="event-data">{formatJson(event.content)}</pre>}</div>); case 'TASK_LIFECYCLE': return (<div className="event simple-event"><div className="event-header"><span className='mr-2'>{event.icon}</span><span>{event.message}</span><span className="event-timestamp">{formatTimestamp(event.timestamp)}</span></div></div>); default: return null; } });
  RenderableEvent.displayName = 'RenderableEvent';


  if (sessionState !== 'SESSION_ACTIVE') {
    return (
      <div className="setup-container">
        <div className="setup-box">
          <Github size={48} className="mb-4 text-gray-400" />
          <h2 className="text-2xl font-semibold mb-2">Connect a Repository</h2>
          <p className="text-gray-400 mb-6 text-center">Provide a GitHub URL to begin. The agent will fork the repository to your account if needed to enable commits.</p>
          <div className="w-full flex items-center gap-2">
            <Link size={20} className="text-gray-500 flex-shrink-0" />
            <input type="text" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} placeholder="https://github.com/user/repo-name" className="setup-input" disabled={sessionState === 'CREATING_SESSION'}/>
          </div>
          <button onClick={createSession} disabled={sessionState === 'CREATING_SESSION'} className="setup-button">
            {sessionState === 'CREATING_SESSION' ? <Loader className="animate-spin" /> : 'Start Session'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`agent-terminal-wrapper`}>
      {repoInfo && (
        <div className="repo-status-bar">
          <div className="repo-info">
            <Github size={16} />
            <span>Working on: <strong>{repoInfo.owner}/{repoInfo.name}</strong></span>
          </div>
          {repoInfo.isFork && (
            <div className="fork-badge">
              <GitCommitHorizontal size={14} />
              <span>Fork</span>
            </div>
          )}
        </div>
      )}

      <div className="terminal-container">
        <div className="terminal-header">
          <Cloud size={16} /> 
          <span>Agent Stream</span>
          {lastUsedModelName && (
            <span className="model-display-name">- {lastUsedModelName}</span>
          )}
        </div>
        <div className="terminal" ref={terminalRef}>
          {processedEvents.map(event => <RenderableEvent key={event.key} event={event} />)}
        </div>
      </div>

      {!isTaskRunning && (
        <div className="input-section">
          <div className="input-container">
            <div className="model-selector" ref={modelSelectorRef}>
              {/* --- REVISED: Simplified Button --- */}
              <button
                className="model-selector-trigger"
                onClick={() => setIsModelSelectorOpen(!isModelSelectorOpen)}
                disabled={isTaskRunning}
              >
                {/* Icon removed for a simpler look */}
                <span>{selectedModelName}</span>
                <ChevronUp size={16} className={`model-selector-chevron ${isModelSelectorOpen ? 'open' : ''}`} />
              </button>
              {isModelSelectorOpen && (
                <div className="model-selector-panel">
                  {MODEL_GROUPS.map(group => (
                    <div key={group.provider} className="model-group">
                      <div className="model-group-label">{group.provider}</div>
                      {group.models.map(model => (
                        <div
                          key={model.id}
                          className={`model-option ${selectedModel === model.id ? 'selected' : ''}`}
                          onClick={() => {
                            setSelectedModel(model.id);
                            setIsModelSelectorOpen(false);
                          }}
                        >
                          {model.name}
                          {selectedModel === model.id && <CheckCircle size={14} />}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            <textarea
              ref={queryRef}
              placeholder="Describe the task for the AI agent..."
              disabled={isTaskRunning}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); startTask(); }}}
            />

            <button
              onClick={startTask} disabled={isTaskRunning}
              className={`submit-button ${isTaskRunning ? 'loading' : ''}`}
              title="Start Task (Enter)">{'>'}
            </button>
          </div>
        </div>
      )}

      {status && (<div className={`status-toast ${status.type} ${isExiting ? 'exiting' : ''}`}><div className="status-indicator" /><span>{status.message}</span></div>)}
    </div>
  );
}
