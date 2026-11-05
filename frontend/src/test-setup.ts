import '@testing-library/jest-dom/vitest'
import { configure } from '@testing-library/react'

// IndexedDB callbacks and jsdom rendering can exceed one second on Windows.
// Keep a bounded wait so missing UI still fails deterministically.
configure({ asyncUtilTimeout: 5000 })
