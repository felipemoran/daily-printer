// The Thermal design system, mirrored from Claude Design: docs/feature-design-system.md.
import './react-global'
import '../../../design-system/components/bundle.js'
import './generated/tokens.css'
import './generated/bundle.css'
import type * as Components from './generated/thermal'

declare global {
  interface Window { Thermal: typeof Components }
}

const Thermal = window.Thermal
export default Thermal
export type * from './generated/thermal'
