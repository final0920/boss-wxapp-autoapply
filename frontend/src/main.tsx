import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { routeTree } from './routeTree.gen'
import { SessionProvider } from './lib/device-context'
import { I18nProvider } from './lib/i18n'
import '@fontsource/inter/400.css'
import '@fontsource/inter/500.css'
import '@fontsource/inter/600.css'
import '@fontsource/inter/700.css'
import '@fontsource/newsreader/400.css'
import '@fontsource/newsreader/500.css'
import '@fontsource/newsreader/600.css'
import './styles/globals.css'

const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

const rootEl = document.getElementById('root')!
createRoot(rootEl).render(
  <StrictMode>
    <I18nProvider>
      <SessionProvider>
        <RouterProvider router={router} />
      </SessionProvider>
    </I18nProvider>
  </StrictMode>,
)
