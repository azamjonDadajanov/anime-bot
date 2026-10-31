import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import OrientationWrapper from './OrientationWrapper'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <OrientationWrapper>
      <App />
    </OrientationWrapper>
  </StrictMode>,
)
