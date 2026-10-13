import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MantineProvider } from '@mantine/core'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './apis/AuthContext.jsx'
import '@mantine/core/styles.css'
import './index.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MantineProvider
      defaultColorScheme="light"
      theme={{
        primaryColor: 'blue',
        colors: {
          blue: ['#e8f2ff', '#cfe3ff', '#a6ccff', '#77b2ff', '#4d98f5', '#287de0', '#1768c4', '#10549f', '#0d427d', '#0a315e'],
          dark: ['#dce8f8', '#b8cae0', '#8da7c8', '#6481a5', '#405f86', '#27466c', '#102945', '#050d1a', '#030916', '#01040b'],
        },
      }}
    >
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </MantineProvider>
  </StrictMode>,
)