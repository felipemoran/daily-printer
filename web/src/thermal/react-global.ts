import * as React from 'react'

// bundle.js is a classic script from Claude Design: it reads window.React when it runs.
declare global {
  interface Window { React: typeof React }
}

window.React = React
