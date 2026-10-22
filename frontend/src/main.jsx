import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import { MantineProvider } from '@mantine/core'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './apis/AuthContext.jsx'
import { isAdminHost } from './admin/adminBase'
import '@mantine/core/styles.css'
import './index.css'
import App from './App.jsx'

// The SPA owns its scroll position; the browser must not restore an old one.
if ('scrollRestoration' in history) history.scrollRestoration = 'manual'

const AdminApp = lazy(() => import('./admin/AdminApp'))

const theme = {
  primaryColor: 'brand',
  primaryShade: { light: 6, dark: 4 },
  defaultRadius: 'md',
  fontFamily: "'Inter Tight', system-ui, -apple-system, sans-serif",
  fontFamilyMonospace: "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
  headings: {
    fontFamily: "'Bricolage Grotesque', 'Inter Tight', system-ui, sans-serif",
    fontWeight: '600',
  },
  colors: {
    // Electric cobalt — the platform's primary signal colour.
    brand: ['#edf0ff', '#dbe0ff', '#b6c1ff', '#8da0ff', '#6b83ff', '#526cff', '#3046e8', '#2233b8', '#18268f', '#101b66'],
    // Ultraviolet — secondary highlights and chrome gradients.
    violet: ['#f3edff', '#e5d9ff', '#c9b2ff', '#ab8aff', '#956cff', '#8657ff', '#7042f0', '#5a2ed0', '#4622a6', '#351880'],
    // Acid lime — live markers, ratings, success details.
    acid: ['#f7ffe0', '#ecffb3', '#e0ff85', '#d3fb58', '#c9f23a', '#b9de22', '#9dbf16', '#7f9c0d', '#637a08', '#4a5c04'],
  },
  defaultColorScheme: 'dark',
  respectReducedMotion: true,
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <MantineProvider defaultColorScheme="dark" theme={theme}>
      <BrowserRouter>
        {isAdminHost() ? (
          <Suspense fallback={<div className="loading-state">Yuklanmoqda…</div>}>
            <AdminApp />
          </Suspense>
        ) : (
          <AuthProvider>
            <App />
          </AuthProvider>
        )}
      </BrowserRouter>
    </MantineProvider>
  </StrictMode>,
)
