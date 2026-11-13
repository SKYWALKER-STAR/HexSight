import React from 'react'
import ReactDOM from 'react-dom/client'
import { Dashboard } from './pages/Dashboard'
import './styles.css'
import { Schedule } from './pages/Schedule'
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{window.location.pathname === '/schedule' ? <Schedule/> : <Dashboard/>}</React.StrictMode>)
