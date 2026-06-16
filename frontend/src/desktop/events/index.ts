import mitt from 'mitt'
import type { DesktopEventTypes } from './event-types'

const emitter = mitt<DesktopEventTypes>()

export default emitter
