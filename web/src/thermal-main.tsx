import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './fonts.css'
import TicketExample from './thermal/TicketExample.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <TicketExample />
  </StrictMode>,
)
