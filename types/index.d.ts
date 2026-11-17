// The agenting plugin's hooks-module contract (the fan-out view, hooks/fanouts/): what
// scripts/fanout_scan.py prints (Snapshot) and the session values the view keeps in $.state.

export type AgentState = 'queued' | 'pending' | 'running' | 'done' | 'failed' | 'died' | 'skipped'
export type RunState = 'running' | 'done' | 'failed' | 'stopped' | 'died' | 'unknown'

export type FanoutAgent = {
  id: string
  label: string
  phase: string | null
  state: AgentState
  model: string | null
  effort: string | null
  elapsed_s: number | null
  // output tokens alone, and every token (output plus cache writes and reads), this run's attempts
  out_tokens: number | null
  tokens?: number | null
  cost_usd: number | null
  attempts: number
  error: string | null
  // done without an attempt in this run: its output came from an earlier run
  resumed?: boolean
}

export type FanoutCounts = {
  total: number
  done: number
  running: number
  queued: number
  failed: number
  skipped: number
}

export type Fanout = {
  id: string
  kind: 'runtime' | 'cleanrun' | 'unknown'
  name: string
  dir: string
  script?: string | null
  pid?: number | null
  alive?: boolean | null
  state: RunState
  started_at?: number | null
  ended_at?: number | null
  elapsed_s?: number | null
  jobs?: number | null
  phases?: string[]
  agents: FanoutAgent[]
  counts?: FanoutCounts
  cost_usd?: number | null
  tokens?: number | null
  last_log?: string | null
  warnings?: string[]
  problems: string[]
}

export type Snapshot = {
  v: 1
  now: number
  platform: string
  // the claude process whose runs this lists (the chat); null when every run on the machine is listed
  owner?: number | null
  // the process table could not be read: the snapshot says nothing about what runs
  degraded?: boolean
  fanouts: Fanout[]
  cwds: Record<string, string>
  problems: string[]
}

// A run folder the mod has seen, passed back to the scanner (--dir) so a finished run stays
// on screen after its process is gone. endedAt (epoch seconds) is when the mod first saw it
// ended, or the run's own end when it was already over; null while it runs.
export type Known = { dir: string; endedAt: number | null }

// What the pane shows, as /workflows does: one fan-out (by folder), one of its phases, the agent
// row holding the focus ring (an index into the phase's agents, or null) and the first agent row
// of the page on screen. pinned is the folder a band row opened while it had ended (kept in the
// pane until the person picks another tab, or a scan shows that folder running again or gone), else null.
export type Selection = { dir: string | null; phase: string | null; agent: number | null; top: number; pinned: string | null }

// One run folder of this chat's clean fan-outs: what earlier runs there cost (settled), what the
// run in it now costs (current), and whether it was running at the last scan.
export type SpendRun = { dir: string; settled: number; current: number; running: boolean }

// This chat's clean fan-out spend, for the status line: every folder seen, and the total last
// written to the spend file (null before the first write).
export type Spend = { runs: SpendRun[]; written: number | null }

declare module 'claude-code' {
  interface PluginState {
    agenting: {
      snapshot: Shaped<Snapshot | null>
      known: Shaped<Known[]>
      selection: Shaped<Selection>
      spend: Shaped<Spend>
      scanError: string | null
    }
  }
}
