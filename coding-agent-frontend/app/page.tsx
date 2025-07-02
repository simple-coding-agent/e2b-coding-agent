import AgentTerminal from '../components/AgentTerminal'
import './globals.css'

export default function Home() {
  return (
    <div className="container">
      <h1 style={{ marginBottom: '20px', textAlign: 'center' }}>
        AI Coding Agent
      </h1>
      <AgentTerminal />
    </div>
  )
}
