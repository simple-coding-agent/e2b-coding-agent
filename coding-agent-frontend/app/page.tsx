// page.tsx
import AgentTerminal from '../components/AgentTerminal'
import './globals.css'

export default function Home() {
  return (
    <div className="app-container">
      <header className="header">
        <h1>Coding Agent</h1>
        <p>Powered by E2B</p>
      </header>
      
      <main className="main-content">
        <AgentTerminal />
      </main>
    </div>
  )
}
