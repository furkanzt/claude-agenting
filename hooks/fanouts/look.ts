// The look of a clean fan-out, copied from how Claude Code draws a Workflow.
//
// A mod cannot mount the engine's own Workflow or task-panel rows (no render site takes
// synthetic data), so this file is the one place the mod is tied to them: glyphs, words,
// widths and colour roles, read off a real Claude Code LOOK_FROM screen (the bottom-panel
// row and the /workflows view). Colours are theme keys only, so they follow the person's
// theme. When the engine's look changes, change this file (hooks/fanouts/look.ts); the pane says so when the running
// version differs.

import type { AgentState, RunState } from '../../types'

export const LOOK_FROM = '2.1.317'

export const WORDS = {
  kind: 'clean fan-out',
  kindPlural: 'clean fan-outs',
  heading: 'Clean fan-outs',
  phases: 'Phases',
  defaultGroup: 'Agents',
  agent: 'agent',
  done: 'done',
  notStarted: 'Not started yet',
  none: 'No clean fan-outs yet. One shows here while cleanrun.py runs (or an external clean_runtime.mjs).',
  hint: '↑↓ select · esc close',
  tokens: 'tokens',
  tok: 'tok',
  more: (n: number) => `+${n} more`,
}

export const GLYPHS = {
  runningMac: '⏺',
  runningOther: '●',
  tick: '✔',
  cross: '✘',
  warning: '⚠',
  queued: '◌',
  idle: '◯',
  pointer: '❯',
  // the Workflow row's "pill" bar; Ghostty draws ▰▱ badly, so there the engine uses █░
  pill: { full: '▰', empty: '▱' },
  pillGhostty: { full: '█', empty: '░' },
  frame: { tl: '╭', tr: '╮', bl: '╰', br: '╯', h: '─', v: '│', down: '┬', up: '┴' },
}

// The bottom-panel row's bar, and the /workflows phase column (its inner width, padding included).
export const BAR_CELLS = 20

// The engine's own rule (hasGeometricShapesInkBleedBug: TERM xterm-ghostty or TERM_PROGRAM
// ghostty), kept exact so the band's bar is always the one Claude Code draws beside it.
export function isGhostty(env: { term?: string | null; termProgram?: string | null }): boolean {
  return env.term === 'xterm-ghostty' || env.termProgram === 'ghostty'
}

export function barGlyphs(ghostty: boolean): { full: string; empty: string } {
  return ghostty ? GLYPHS.pillGhostty : GLYPHS.pill
}
export const PHASE_COL = 16

export type Tone = { icon: string; color?: string; dim?: boolean }

function runningGlyph(platform: string): string {
  return platform === 'darwin' ? GLYPHS.runningMac : GLYPHS.runningOther
}

// An agent's icon in /workflows: running ⏺ subtle, done ✔ success, failed ✘ error, stopped ⚠,
// skipped ✘ subtle, waiting ◌ subtle.
export function agentTone(state: AgentState, platform: string): Tone {
  switch (state) {
    case 'running':
      return { icon: runningGlyph(platform), color: 'subtle' }
    case 'done':
      return { icon: GLYPHS.tick, color: 'success' }
    case 'failed':
      return { icon: GLYPHS.cross, color: 'error' }
    case 'died':
      return { icon: GLYPHS.warning, color: 'warning' }
    case 'skipped':
      return { icon: GLYPHS.cross, color: 'subtle' }
    case 'queued':
    case 'pending':
      return { icon: GLYPHS.queued, color: 'subtle' }
  }
}

// A run's icon on the bottom-panel row: ◯ dim while it runs, ◯ success when done.
export function runTone(state: RunState): Tone {
  switch (state) {
    case 'running':
      return { icon: GLYPHS.idle, dim: true }
    case 'done':
      return { icon: GLYPHS.idle, color: 'success' }
    case 'failed':
      return { icon: GLYPHS.cross, color: 'error' }
    default:
      return { icon: GLYPHS.warning, color: 'warning' }
  }
}

export function plural(n: number, one: string, many = one + 's'): string {
  return `${n} ${n === 1 ? one : many}`
}

// Elapsed time as the engine writes it on the Workflow row: 35s, 28m45s, 1h02m, 2d03h.
export function duration(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return null
  const s = Math.floor(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m${String(s % 60).padStart(2, '0')}s`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h${String(m % 60).padStart(2, '0')}m`
  return `${Math.floor(h / 24)}d${String(h % 24).padStart(2, '0')}h`
}

// A token count as the engine writes it: compact, lower case, one decimal from 1,000 up
// (812, 1.0k, 113.3k, 2.5m), the same Intl format it uses.
export function count(n: number | null | undefined): string | null {
  if (n === null || n === undefined || !Number.isFinite(n)) return null
  const big = n >= 1000
  try {
    return new Intl.NumberFormat('en-US', {
      notation: 'compact',
      maximumFractionDigits: 1,
      minimumFractionDigits: big ? 1 : 0,
    }).format(n).toLowerCase()
  } catch {
    const units: Array<[number, string]> = [[1e12, 't'], [1e9, 'b'], [1e6, 'm'], [1e3, 'k']]
    for (const [size, unit] of units) {
      if (n >= size * 0.99995) return `${(n / size).toFixed(1)}${unit}`
    }
    return String(Math.round(n * 10) / 10)
  }
}

export function dollars(usd: number | null | undefined): string | null {
  if (usd === null || usd === undefined || !Number.isFinite(usd)) return null
  return `$${usd.toFixed(2)}`
}

// claude-opus-5-5 -> Opus 5.5, as the /workflows rows name a model.
export function modelName(id: string | null | undefined): string | null {
  if (!id) return null
  const m = /^claude-([a-z]+)-(\d+)-(\d+)/.exec(id)
  if (!m) return id
  const [, family = '', major = '', minor = ''] = m
  return `${family.charAt(0).toUpperCase()}${family.slice(1)} ${major}.${minor}`
}

export const SEP = ' · '
