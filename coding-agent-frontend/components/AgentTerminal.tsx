'use client'

import { useState, useRef, useEffect } from 'react'

interface Event {
  type: string
  timestamp?: string
  tool?: string
  data: any
}

export default function AgentTerminal() {
  const [events, setEvents] = useState<Event[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [query, setQuery] = useState('Create a simple README.md file with project information')
  const [status, setStatus] = useState('')
  const terminalRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight
    }
  }, [events])

  const startTask = async () => {
    if (!query.trim()) {
      alert('Please enter a query')
      return
    }

    setEvents([])
    setIsRunning(true)
    setStatus('Creating task...')

    try {
      // Create task
      const response = await fetch('http://127.0.0.1:8000/tasks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: query.trim(),
          max_iterations: 15,
          model: 'openai/gpt-4.1'
        })
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      const taskId = data.task_id

      setStatus(`Task created: ${taskId}`)

      // Start listening to events
      const eventSource = new EventSource(`http://127.0.0.1:8000/tasks/${taskId}/events`)

      eventSource.onmessage = (e) => {
        try {
          const event = JSON.parse(e.data)
          
          // Skip keepalive events
          if (event.type === 'keepalive') return

          setEvents(prev => [...prev, event])

          if (event.type === 'task_complete' || event.type === 'final_response') {
            setStatus('Task completed!')
            eventSource.close()
            setIsRunning(false)
          }
        } catch (error) {
          console.error('Error parsing event:', error)
        }
      }

      eventSource.onerror = (e) => {
        console.error('EventSource error:', e)
        setStatus('Connection error occurred')
        eventSource.close()
        setIsRunning(false)
      }

      setStatus('Connected - waiting for events...')

    } catch (error) {
      setStatus(`Error: ${error}`)
      setIsRunning(false)
    }
  }

  const formatEventData = (data: any): string => {
    if (typeof data === 'string') return data
    return JSON.stringify(data, null, 2)
  }

  const formatTimestamp = (timestamp?: string): string => {
    if (!timestamp) return ''
    return new Date(timestamp).toLocaleTimeString()
  }

  const clearTerminal = () => {
    setEvents([])
    setStatus('')
  }

  return (
    <div>
      <div className="input-section">
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter your task for the AI agent..."
          disabled={isRunning}
        />
        <div>
          <button onClick={startTask} disabled={isRunning}>
            {isRunning ? 'Running...' : 'Start Task'}
          </button>
          <button onClick={clearTerminal} disabled={isRunning} style={{ marginLeft: '10px' }}>
            Clear
          </button>
        </div>
      </div>

      {status && <div className="status">{status}</div>}

      <div className="terminal" ref={terminalRef}>
        {events.length === 0 ? (
          <div style={{ color: '#666', textAlign: 'center', marginTop: '50px' }}>
            Enter a task above and click "Start Task" to begin
          </div>
        ) : (
          events.map((event, idx) => {
            // Show iteration headers
            if (event.type === 'iteration_start') {
              return (
                <div key={idx} className="iteration-header">
                  🔄 Iteration {event.data.iteration} / {event.data.max_iterations}
                </div>
              )
            }

            return (
              <div key={idx} className={`event ${event.type}`}>
                <div className="event-header">
                  <span className="event-type">[{event.type.toUpperCase()}]</span>
                  {event.tool && (
                    <span className="event-tool">🔧 {event.tool}</span>
                  )}
                  <span className="event-timestamp">
                    {formatTimestamp(event.timestamp)}
                  </span>
                </div>
                <div className="event-data">
                  {formatEventData(event.data)}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
