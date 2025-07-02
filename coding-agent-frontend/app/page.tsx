// page.tsx
import AgentTerminal from '../components/AgentTerminal'
import './globals.css'

export default function Home() {
  return (
    <div className="app-container">
      <header className="header">
        <h1>AI Coding Agent</h1>
        <p>Intelligent Task Automation</p>
      </header>
      
      <main className="main-content">
        <AgentTerminal />
      </main>
    </div>
  )
}
