import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import Control from './pages/Control'
import Dashboard from './pages/Dashboard'
import Phone, { PhonePicker } from './pages/Phone'
import PrintCard from './pages/PrintCard'
import Join from './pages/Join'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/control" element={<Control />} />
        <Route path="/phone" element={<PhonePicker />} />
        <Route path="/phone/:id" element={<Phone />} />
        <Route path="/print/block/:id" element={<PrintCard />} />
        <Route path="/join" element={<Join />} />
      </Routes>
    </BrowserRouter>
  )
}

function Home() {
  const link = (to: string, title: string, text: string) => (
    <Link to={to} className="block rounded-2xl bg-panel p-5 shadow-sm ring-1 ring-line hover:ring-brand">
      <p className="text-lg font-semibold">{title}</p>
      <p className="text-sm text-muted">{text}</p>
    </Link>
  )
  return (
    <div className="mx-auto max-w-xl p-8">
      <h1 className="text-3xl font-bold tracking-tight">Kampung Grid</h1>
      <p className="mb-6 text-muted">No one in the block gets forgotten.</p>
      <div className="flex flex-col gap-3">
        {link('/dashboard', 'Authority dashboard', 'The big screen: block view, live reports')}
        {link('/control', 'Demo control panel', 'Run each beat of the demo')}
        {link('/phone', 'Phone app', 'Residents and helpers')}
      </div>
    </div>
  )
}
