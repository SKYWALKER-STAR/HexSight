import React from 'react'
import ReactDOM from 'react-dom/client'
import { Dashboard } from './pages/Dashboard'
import './styles.css'
import { Schedule } from './pages/Schedule'
import { Winrate } from './pages/Winrate'
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{window.location.pathname === '/winrate' ? <Winrate/> : window.location.pathname === '/schedule' ? <Schedule/> : <Dashboard/>}</React.StrictMode>)
