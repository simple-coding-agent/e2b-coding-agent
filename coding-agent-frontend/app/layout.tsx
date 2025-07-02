// layout.tsx
import './globals.css'

export const metadata = {
  title: 'Coding Agent',
  description: 'AI Coding Agent Interface',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
