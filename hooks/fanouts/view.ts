// What the band and the pane show, worked out from a scanner snapshot. No I/O, no drawing.

import type { Fanout, FanoutAgent, Known, Selection, Snapshot } from '../../types'
import { BAR_CELLS, GLYPHS, PHASE_COL, SEP, WORDS, count, dollars, duration, modelName, plural } from './look'

// A finished fan-out stays in the band this long after the mod saw it end, then only in the pane.
export const BAND_KEEP_S = 300
// A finished fan-out's folder is passed back to the scanner this long.
export const KNOWN_KEEP_S = 2 * 3600
export const KNOWN_MAX = 20
export const BAND_MAX = 3
// Agent rows on one page of the agent column, as /workflows shows them ("1-10 of 14 ↓").
export const PAGE = 10

export function parseSnapshot(text: string): Snapshot {
  const value = JSON.parse(text) as Snapshot
  if (!value || value.v !== 1 || !Array.isArray(value.fanouts)) {
    throw new Error('the scanner printed something that is not a v1 snapshot')
  }
  return value
}

export function isLive(f: Fanout): boolean {
  return f.state === 'running'
}

function endedAt(f: Fanout, known: Known[]): number | null {
  const k = known.find(x => x.dir === f.dir)
  return k ? k.endedAt : (f.ended_at ?? null)
}

// The band: every running fan-out, and one that ended in the last BAND_KEEP_S seconds.
export function bandFanouts(snap: Snapshot | null, known: Known[] = []): Fanout[] {
  if (!snap) return []
  return snap.fanouts.filter(f => {
    if (isLive(f)) return true
    if (f.state === 'unknown') return false
    const end = endedAt(f, known)
    return typeof end === 'number' && snap.now - end < BAND_KEEP_S
  })
}

export function counts(f: Fanout) {
  if (f.counts) return f.counts
  const c = { total: f.agents.length, done: 0, running: 0, queued: 0, failed: 0, skipped: 0 }
  for (const a of f.agents) {
    if (a.state === 'done') c.done++
    else if (a.state === 'running') c.running++
    else if (a.state === 'queued' || a.state === 'pending') c.queued++
    else if (a.state === 'failed' || a.state === 'died') c.failed++
    else if (a.state === 'skipped') c.skipped++
  }
  return c
}

export function totalTokens(f: Fanout): number | null {
  if (typeof f.tokens === 'number') return f.tokens
  const known = f.agents.map(a => a.tokens).filter((t): t is number => typeof t === 'number')
  return known.length ? known.reduce((x, y) => x + y, 0) : null
}

// The bottom-panel row's bar: floor(done × BAR_CELLS / total) filled cells, as the engine counts them.
export function barCells(f: Fanout): { full: number; empty: number } {
  const c = counts(f)
  const full = c.total > 0 ? Math.min(BAR_CELLS, Math.floor((c.done * BAR_CELLS) / c.total)) : 0
  return { full, empty: BAR_CELLS - full }
}

// The bottom-panel row's stats: "2/5 · 23s · ↓ 132.2k tokens", then the fan-out's own words.
export function bandStats(f: Fanout): string {
  const c = counts(f)
  const parts = [`${c.done}/${c.total}`]
  const time = duration(f.elapsed_s)
  if (time) parts.push(time)
  const tok = count(totalTokens(f))
  if (tok) parts.push(`↓ ${tok} ${WORDS.tokens}`)
  if (c.failed) parts.push(`${c.failed} failed`)
  parts.push(WORDS.kind)
  return parts.join(SEP)
}

// The /workflows header's right side: "3/3 agents · 6s · done", the run's cost before the end word.
export function headerStats(f: Fanout): string {
  const c = counts(f)
  const parts = [`${c.done}/${plural(c.total, WORDS.agent)}`]
  const time = duration(f.elapsed_s)
  if (time) parts.push(time)
  const cost = dollars(f.cost_usd)
  if (cost) parts.push(cost)
  if (!isLive(f)) parts.push(f.state === 'done' ? WORDS.done : f.state === 'died' ? 'stopped' : f.state)
  return parts.join(SEP)
}

// The /workflows header's left side, where a Workflow has its description: what this is.
export function description(f: Fanout): string {
  return [WORDS.kind, f.script ?? (f.kind === 'cleanrun' ? 'cleanrun.py' : null)].filter(Boolean).join(SEP)
}

export type Phase = {
  title: string
  index: number
  agents: FanoutAgent[]
  done: number
  failed: number
  open: boolean
}

// Phases in the order the script reached them; agents with no phase go under "Agents".
export function phases(f: Fanout): Phase[] {
  const order = [...(f.phases ?? [])]
  const by = new Map<string, FanoutAgent[]>()
  for (const a of f.agents) {
    const title = a.phase ?? WORDS.defaultGroup
    if (!order.includes(title)) order.push(title)
    const list = by.get(title) ?? []
    list.push(a)
    by.set(title, list)
  }
  const list = order.filter(t => by.has(t) || (f.phases ?? []).includes(t))
  return list.map((title, i) => {
    const agents = by.get(title) ?? []
    return {
      title,
      index: i + 1,
      agents,
      done: agents.filter(a => a.state === 'done').length,
      failed: agents.filter(a => a.state === 'failed' || a.state === 'died').length,
      open: agents.some(a => a.state === 'running' || a.state === 'queued' || a.state === 'pending'),
    }
  })
}

// The phase /workflows opens on: the first with work still open, else the last.
export function defaultPhase(list: Phase[]): Phase | null {
  return list.find(p => p.open) ?? list[list.length - 1] ?? null
}

// The fan-out and phase on screen: the person's pick while it still exists, else the defaults.
export function pick(list: Fanout[], sel: Selection): { fanout: Fanout | null; phase: Phase | null; phases: Phase[] } {
  const fanout = list.find(f => f.dir === sel.dir) ?? list[0] ?? null
  if (!fanout) return { fanout: null, phase: null, phases: [] }
  const ps = phases(fanout)
  const phase = (sel.dir === fanout.dir ? ps.find(p => p.title === sel.phase) : undefined) ?? defaultPhase(ps)
  return { fanout, phase, phases: ps }
}

// Cut or pad text to exactly `width` cells (a cut ends in '…').
export function fit(text: string, width: number): string {
  if (width <= 0) return ''
  const chars = [...text]
  if (chars.length > width) return chars.slice(0, Math.max(0, width - 1)).join('') + '…'
  return text + ' '.repeat(width - chars.length)
}

// The phase column's width, padding included: the Workflow view's 16 cells, wider (up to 28) when
// a phase title would not fit, so "Denetle" is not cut to "Denet…".
export function phaseCol(list: Phase[]): number {
  const need = Math.max(0, ...list.map(p => 4 + [...p.title].length + (p.agents.length ? 2 + `${p.done}/${p.agents.length}`.length : 0)))
  return Math.min(28, Math.max(PHASE_COL, need + 2))
}

// The phase column's text: "❯ 1 One    1/2", the icon a number until the phase is done.
export function phaseCell(p: Phase, selected: boolean, col = PHASE_COL): { pointer: string; icon: string; title: string; counts: string } {
  const inner = col - 2
  const icon = p.agents.length > 0 && p.done === p.agents.length ? GLYPHS.tick : p.failed > 0 && !p.open ? GLYPHS.cross : String(p.index)
  const counts = p.agents.length > 0 ? `${p.done}/${p.agents.length}` : ''
  const head = `${selected ? GLYPHS.pointer : ' '} ${icon} `
  const room = inner - [...head].length - counts.length - (counts ? 1 : 0)
  // padded so the counts end at the column's edge; with no counts, nothing trails the title
  const title = counts ? fit(p.title, Math.max(1, room)) : fit(p.title, Math.max(1, room)).trimEnd()
  return { pointer: selected ? GLYPHS.pointer : ' ', icon, title, counts }
}

export function phaseState(p: Phase): 'done' | 'failed' | 'open' | 'idle' {
  if (p.agents.length > 0 && p.done === p.agents.length) return 'done'
  if (p.failed > 0 && !p.open) return 'failed'
  return p.agents.length > 0 ? 'open' : 'idle'
}

// An agent row's stats, as /workflows writes them: "Opus 5.5 · xhigh · 31.6k tok", then a state word.
export function agentStats(a: FanoutAgent, withEffort = true): string {
  const parts = [modelName(a.model), withEffort ? a.effort : null]
  const tok = count(a.tokens ?? null)
  if (tok) parts.push(`${tok} ${WORDS.tok}`)
  if (a.state === 'done' && a.resumed) parts.push('resumed')
  if (a.state === 'queued' || a.state === 'pending') parts.push('queued')
  if (a.state === 'skipped') parts.push('skipped')
  if (a.state === 'died') parts.push('stopped')
  if (a.state === 'failed') parts.push('failed')
  if (a.attempts > 1) parts.push(plural(a.attempts, 'attempt'))
  return parts.filter(Boolean).join(SEP)
}

// The effort every agent of a phase shares, else null. When there is one, the agent column's title
// carries it once and the rows read as the Workflow view's do ("Opus 5.5 · 31.6k tok"). A call still
// queued has no effort known yet, so it does not count against the others.
export function sharedEffort(list: FanoutAgent[]): string | null {
  const efforts = new Set(list.map(a => a.effort).filter((e): e is string => Boolean(e)))
  const [only] = [...efforts]
  return efforts.size === 1 && only ? only : null
}

export function agentTime(a: FanoutAgent): string {
  return duration(a.elapsed_s) ?? ''
}

// The label column: as wide as the phase's longest label (12 to 28 cells) and two spaces.
export function labelWidth(agents: FanoutAgent[]): number {
  return Math.min(28, Math.max(12, ...agents.map(a => [...a.label].length))) + 1
}

// The frame lines around the two columns: "╭ Phases ────┬ One · 2 agents ───╮" and "╰────┴───╯".
export function frameTop(right: number, title: string, col = PHASE_COL): string {
  const f = GLYPHS.frame
  const left = ` ${WORDS.phases} `
  const t = ` ${title} `
  return f.tl + left + f.h.repeat(Math.max(0, col - left.length)) + f.down
    + fit(t, Math.min([...t].length, right)) + f.h.repeat(Math.max(0, right - [...t].length)) + f.tr
}

// The bottom line; with more agents than a page, the pager sits in it: "──── 1-10 of 14 ↓ ╯".
export function frameBottom(right: number, col = PHASE_COL, pagerText: string | null = null): string {
  const f = GLYPHS.frame
  const tail = pagerText ? ` ${pagerText} ` : ''
  return f.bl + f.h.repeat(col) + f.up + f.h.repeat(Math.max(0, right - [...tail].length)) + tail + f.br
}

// "1-10 of 14 ↓", "3-12 of 14 ↑↓", "5-14 of 14 ↑"; null when one page holds them all.
export function pager(top: number, total: number): string | null {
  if (total <= PAGE) return null
  const end = Math.min(total, top + PAGE)
  const arrows = (top > 0 ? '↑' : '') + (end < total ? '↓' : '')
  return `${top + 1}-${end} of ${total}${arrows ? ' ' + arrows : ''}`
}

// The page's first row once the agent at `index` holds the ring: it moves only to keep a row
// beyond the focused one on screen, so ↑↓ always has a row to move to.
export function pageTop(index: number, top: number, total: number): number {
  if (total <= PAGE) return 0
  let t = top
  if (index >= t + PAGE - 1) t = index - PAGE + 2
  if (index <= t) t = index - 1
  return Math.max(0, Math.min(total - PAGE, t))
}

// An agent row cut to `width` cells: "❯✔ label        Opus 5.5 · 31.6k tok          12s".
export function agentLine(a: FanoutAgent, lw: number, width: number, selected: boolean, withEffort = true) {
  const label = fit(a.label, lw)
  const time = agentTime(a)
  const rest = Math.max(0, width - 3 - lw)
  const statsRoom = Math.max(0, rest - time.length - (time ? 1 : 0))
  const stats = fit(agentStats(a, withEffort), statsRoom).trimEnd()
  // a failed agent's reason follows its stats, inside the same width so the frame stays straight
  const left = statsRoom - [...stats].length
  const error = a.error && left > 3 ? fit(` — ${a.error}`, left).trimEnd() : ''
  const pad = ' '.repeat(Math.max(0, rest - [...stats].length - [...error].length - time.length))
  return { pointer: selected ? GLYPHS.pointer : ' ', label, stats, error, pad, time }
}

// Every fan-out folder in the snapshot, newest first. endedAt is when the mod first saw a run end
// (so a run whose files stopped changing long ago still gets its five minutes in the band), or the
// run's own end when it was over before the mod saw it. Kept KNOWN_KEEP_S, at most KNOWN_MAX.
export function mergeKnown(known: Known[], snap: Snapshot): Known[] {
  const by = new Map<string, Known>(known.map(k => [k.dir, k]))
  for (const f of snap.fanouts) {
    if (f.state === 'unknown') continue
    const before = by.get(f.dir)
    if (isLive(f)) by.set(f.dir, { dir: f.dir, endedAt: null })
    else if (!before) by.set(f.dir, { dir: f.dir, endedAt: f.ended_at ?? snap.now })
    else if (before.endedAt === null) by.set(f.dir, { dir: f.dir, endedAt: snap.now })
  }
  return [...by.values()]
    .filter(k => k.endedAt === null || snap.now - k.endedAt < KNOWN_KEEP_S)
    .sort((a, b) => (b.endedAt ?? Infinity) - (a.endedAt ?? Infinity))
    .slice(0, KNOWN_MAX)
}

// A fan-out the scanner could not read this time ('unknown': its process's folder could not be
// resolved) keeps the entry of the last good scan, marked, so its band row and its end toast stay.
export const UNREAD = 'could not be read in the last scan; showing the one before'
export function carryUnknown(prev: Snapshot | null, next: Snapshot): Snapshot {
  return {
    ...next,
    fanouts: next.fanouts.map(f => {
      if (f.state !== 'unknown') return f
      const before = prev?.fanouts.find(p => p.dir === f.dir && p.state !== 'unknown')
      return before ? { ...before, problems: [...before.problems.filter(p => p !== UNREAD), UNREAD] } : f
    }),
  }
}

// Fan-outs that were running in the last snapshot and have ended now: the ones to announce.
export function finished(prev: Snapshot | null, next: Snapshot): Fanout[] {
  if (!prev) return []
  const wasLive = new Set(prev.fanouts.filter(isLive).map(f => f.id))
  return next.fanouts.filter(f => wasLive.has(f.id) && !isLive(f) && f.state !== 'unknown')
}

export function announce(f: Fanout): string {
  const c = counts(f)
  const verb = f.state === 'done' ? 'finished' : f.state === 'died' ? 'stopped' : f.state
  const parts = [`${c.done}/${plural(c.total, WORDS.agent)}`]
  if (c.failed) parts.push(`${c.failed} failed`)
  const time = duration(f.elapsed_s)
  if (time) parts.push(time)
  const cost = dollars(f.cost_usd)
  if (cost) parts.push(cost)
  return `${WORDS.kind} ${f.name} ${verb}: ${parts.join(SEP)}`
}

