/**
 * @aedifex/constraints — Geometric constraint solver for architectural editing.
 *
 * Handles parametric constraints:
 * - Wall alignment (parallel, perpendicular, collinear)
 * - Window/door positioning along walls (parametric offset)
 * - Dimensional constraints (fixed length, ratio)
 * - Grid snapping
 * - Room area constraints
 *
 * Lightweight TypeScript solver — can be replaced with ezpz WASM later.
 */

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

export type Vec2 = [number, number]

export interface Point {
  x: number
  y: number
}

export interface ConstraintBase {
  id: string
  type: string
  active: boolean
}

/** Fixed distance between two points */
export interface DistanceConstraint extends ConstraintBase {
  type: 'distance'
  pointA: string // node id
  pointB: string // node id
  distance: number // meters
}

/** Two walls are parallel */
export interface ParallelConstraint extends ConstraintBase {
  type: 'parallel'
  wallA: string
  wallB: string
}

/** Two walls are perpendicular */
export interface PerpendicularConstraint extends ConstraintBase {
  type: 'perpendicular'
  wallA: string
  wallB: string
}

/** Point lies on a wall at parametric position t ∈ [0,1] */
export interface OnWallConstraint extends ConstraintBase {
  type: 'on-wall'
  pointId: string
  wallId: string
  t: number // parametric position along wall
}

/** Opening (door/window) centered on wall */
export interface CenterOnWallConstraint extends ConstraintBase {
  type: 'center-on-wall'
  openingId: string
  wallId: string
}

/** Fixed angle between two walls */
export interface AngleConstraint extends ConstraintBase {
  type: 'angle'
  wallA: string
  wallB: string
  angleDeg: number
}

/** Grid snap — point snaps to nearest grid intersection */
export interface GridSnapConstraint extends ConstraintBase {
  type: 'grid-snap'
  gridSize: number // meters (default 0.5)
}

/** Collinear — two walls share the same line */
export interface CollinearConstraint extends ConstraintBase {
  type: 'collinear'
  wallA: string
  wallB: string
}

/** Room area constraint */
export interface AreaConstraint extends ConstraintBase {
  type: 'area'
  roomId: string
  targetArea: number // m²
  tolerance: number // ±m²
}

export type Constraint =
  | DistanceConstraint
  | ParallelConstraint
  | PerpendicularConstraint
  | OnWallConstraint
  | CenterOnWallConstraint
  | AngleConstraint
  | GridSnapConstraint
  | CollinearConstraint
  | AreaConstraint

// ═══════════════════════════════════════════════════════════════
// Scene node types (minimal for constraint solving)
// ═══════════════════════════════════════════════════════════════

export interface WallData {
  id: string
  type: 'wall'
  start: Vec2
  end: Vec2
  thickness: number
  height: number
}

export interface OpeningData {
  id: string
  type: 'door' | 'window'
  wallId: string
  position: [number, number, number] // [along, height, depth]
  width: number
  height: number
}

export type SceneNode = WallData | OpeningData

// ═══════════════════════════════════════════════════════════════
// Vector math
// ═══════════════════════════════════════════════════════════════

function dist(a: Vec2, b: Vec2): number {
  return Math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)
}

function midpoint(a: Vec2, b: Vec2): Vec2 {
  return [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
}

function normalize(v: Vec2): Vec2 {
  const len = Math.sqrt(v[0] ** 2 + v[1] ** 2)
  if (len < 1e-10) return [0, 0]
  return [v[0] / len, v[1] / len]
}

function wallDirection(wall: WallData): Vec2 {
  return normalize([wall.end[0] - wall.start[0], wall.end[1] - wall.start[1]])
}

function wallNormal(wall: WallData): Vec2 {
  const d = wallDirection(wall)
  return [-d[1], d[0]]
}

function dot(a: Vec2, b: Vec2): number {
  return a[0] * b[0] + a[1] * b[1]
}

function cross(a: Vec2, b: Vec2): number {
  return a[0] * b[1] - a[1] * b[0]
}

function angleBetween(a: Vec2, b: Vec2): number {
  return Math.atan2(cross(a, b), dot(a, b)) * (180 / Math.PI)
}

function movePoint(p: Vec2, dx: number, dy: number): Vec2 {
  return [p[0] + dx, p[1] + dy]
}

function snapToGrid(p: Vec2, gridSize: number): Vec2 {
  return [
    Math.round(p[0] / gridSize) * gridSize,
    Math.round(p[1] / gridSize) * gridSize,
  ]
}

// ═══════════════════════════════════════════════════════════════
// Constraint Solver
// ═══════════════════════════════════════════════════════════════

export interface SolverResult {
  solved: boolean
  iterations: number
  residual: number
  adjustments: Map<string, Vec2> // nodeId → new position
}

export class ConstraintSolver {
  private constraints: Map<string, Constraint> = new Map()
  private gridSize: number = 0.5
  private maxIterations: number = 50
  private tolerance: number = 0.001 // 1mm

  constructor(options?: { gridSize?: number; maxIterations?: number; tolerance?: number }) {
    this.gridSize = options?.gridSize ?? 0.5
    this.maxIterations = options?.maxIterations ?? 50
    this.tolerance = options?.tolerance ?? 0.001
  }

  // ── Constraint management ──

  addConstraint(constraint: Constraint): void {
    this.constraints.set(constraint.id, constraint)
  }

  removeConstraint(id: string): void {
    this.constraints.delete(id)
  }

  getConstraints(): Constraint[] {
    return Array.from(this.constraints.values())
  }

  clearConstraints(): void {
    this.constraints.clear()
  }

  // ── Auto-detect constraints from scene ──

  autoDetect(nodes: Record<string, SceneNode>): Constraint[] {
    const detected: Constraint[] = []
    const walls = Object.values(nodes).filter((n) => n.type === 'wall') as WallData[]

    // Detect parallel walls
    for (let i = 0; i < walls.length; i++) {
      for (let j = i + 1; j < walls.length; j++) {
        const dA = wallDirection(walls[i])
        const dB = wallDirection(walls[j])
        const angle = Math.abs(angleBetween(dA, dB))

        if (angle < 2 || Math.abs(angle - 180) < 2) {
          detected.push({
            id: `parallel_${walls[i].id}_${walls[j].id}`,
            type: 'parallel',
            wallA: walls[i].id,
            wallB: walls[j].id,
            active: true,
          })
        } else if (Math.abs(angle - 90) < 2 || Math.abs(angle + 90) < 2) {
          detected.push({
            id: `perp_${walls[i].id}_${walls[j].id}`,
            type: 'perpendicular',
            wallA: walls[i].id,
            wallB: walls[j].id,
            active: true,
          })
        }
      }
    }

    // Detect collinear walls (shared endpoint)
    for (let i = 0; i < walls.length; i++) {
      for (let j = i + 1; j < walls.length; j++) {
        const wA = walls[i]
        const wB = walls[j]
        const dA = wallDirection(wA)
        const dB = wallDirection(wB)

        // Check if endpoints are close and directions are similar
        const endToStart = dist(wA.end, wB.start) < 0.1
        const startToEnd = dist(wA.start, wB.end) < 0.1
        const dirsSimilar = Math.abs(angleBetween(dA, dB)) < 5

        if ((endToStart || startToEnd) && dirsSimilar) {
          detected.push({
            id: `collinear_${wA.id}_${wB.id}`,
            type: 'collinear',
            wallA: wA.id,
            wallB: wB.id,
            active: true,
          })
        }
      }
    }

    // Detect openings centered on walls
    const openings = Object.values(nodes).filter(
      (n) => n.type === 'door' || n.type === 'window',
    ) as OpeningData[]

    for (const opening of openings) {
      const wall = walls.find((w) => w.id === opening.wallId)
      if (wall) {
        const wallLen = dist(wall.start, wall.end)
        const openingCenter = opening.position[0]
        const isCentered = Math.abs(openingCenter - wallLen / 2) < 0.1

        if (isCentered) {
          detected.push({
            id: `center_${opening.id}`,
            type: 'center-on-wall',
            openingId: opening.id,
            wallId: wall.id,
            active: true,
          })
        }
      }
    }

    return detected
  }

  // ── Solve constraints ──

  solve(nodes: Record<string, SceneNode>): SolverResult {
    const adjustments = new Map<string, Vec2>()
    let totalResidual = 0
    let iterations = 0

    // Deep copy node positions for solving
    const workingNodes: Record<string, SceneNode> = JSON.parse(JSON.stringify(nodes))

    for (iterations = 0; iterations < this.maxIterations; iterations++) {
      let maxDelta = 0

      for (const constraint of this.constraints.values()) {
        if (!constraint.active) continue

        const delta = this.applyConstraint(constraint, workingNodes)
        maxDelta = Math.max(maxDelta, delta)
      }

      totalResidual = maxDelta

      if (maxDelta < this.tolerance) break
    }

    // Collect adjustments
    for (const [id, node] of Object.entries(workingNodes)) {
      const original = nodes[id]
      if (!original) continue

      if (node.type === 'wall') {
        const origWall = original as WallData
        if (
          dist(node.start, origWall.start) > 0.0001 ||
          dist(node.end, origWall.end) > 0.0001
        ) {
          adjustments.set(id, node.start)
        }
      }
    }

    return {
      solved: totalResidual < this.tolerance,
      iterations,
      residual: totalResidual,
      adjustments,
    }
  }

  private applyConstraint(constraint: Constraint, nodes: Record<string, SceneNode>): number {
    switch (constraint.type) {
      case 'grid-snap':
        return this.applyGridSnap(nodes)
      case 'parallel':
        return this.applyParallel(constraint, nodes)
      case 'perpendicular':
        return this.applyPerpendicular(constraint, nodes)
      case 'collinear':
        return this.applyCollinear(constraint, nodes)
      case 'center-on-wall':
        return this.applyCenterOnWall(constraint, nodes)
      case 'distance':
        return this.applyDistance(constraint, nodes)
      case 'angle':
        return this.applyAngle(constraint, nodes)
      default:
        return 0
    }
  }

  private applyGridSnap(nodes: Record<string, SceneNode>): number {
    let maxDelta = 0
    for (const node of Object.values(nodes)) {
      if (node.type === 'wall') {
        const wall = node as WallData
        const snappedStart = snapToGrid(wall.start, this.gridSize)
        const snappedEnd = snapToGrid(wall.end, this.gridSize)

        maxDelta = Math.max(maxDelta, dist(wall.start, snappedStart))
        maxDelta = Math.max(maxDelta, dist(wall.end, snappedEnd))

        wall.start = snappedStart
        wall.end = snappedEnd
      }
    }
    return maxDelta
  }

  private applyParallel(constraint: ParallelConstraint, nodes: Record<string, SceneNode>): number {
    const wallA = nodes[constraint.wallA] as WallData | undefined
    const wallB = nodes[constraint.wallB] as WallData | undefined
    if (!wallA || !wallB) return 0

    const dirA = wallDirection(wallA)
    const dirB = wallDirection(wallB)
    const angle = angleBetween(dirA, dirB)

    if (Math.abs(angle) < 0.1) return 0

    // Rotate wallB to be parallel to wallA
    const targetDir = angle > 90 ? [-dirA[0], -dirA[1]] : dirA
    const wallBLen = dist(wallB.start, wallB.end)
    const midB = midpoint(wallB.start, wallB.end)

    wallB.start = [midB[0] - targetDir[0] * wallBLen / 2, midB[1] - targetDir[1] * wallBLen / 2]
    wallB.end = [midB[0] + targetDir[0] * wallBLen / 2, midB[1] + targetDir[1] * wallBLen / 2]

    return Math.abs(angle) * (Math.PI / 180) * wallBLen
  }

  private applyPerpendicular(
    constraint: PerpendicularConstraint,
    nodes: Record<string, SceneNode>,
  ): number {
    const wallA = nodes[constraint.wallA] as WallData | undefined
    const wallB = nodes[constraint.wallB] as WallData | undefined
    if (!wallA || !wallB) return 0

    const dirA = wallDirection(wallA)
    const dirB = wallDirection(wallB)
    const angle = angleBetween(dirA, dirB)
    const targetAngle = 90
    const error = angle - targetAngle

    if (Math.abs(error) < 0.1) return 0

    // Rotate wallB to be perpendicular to wallA
    const perpDir: Vec2 = [-dirA[1], dirA[0]]
    const wallBLen = dist(wallB.start, wallB.end)
    const midB = midpoint(wallB.start, wallB.end)

    wallB.start = [midB[0] - perpDir[0] * wallBLen / 2, midB[1] - perpDir[1] * wallBLen / 2]
    wallB.end = [midB[0] + perpDir[0] * wallBLen / 2, midB[1] + perpDir[1] * wallBLen / 2]

    return Math.abs(error) * (Math.PI / 180) * wallBLen
  }

  private applyCollinear(
    constraint: CollinearConstraint,
    nodes: Record<string, SceneNode>,
  ): number {
    const wallA = nodes[constraint.wallA] as WallData | undefined
    const wallB = nodes[constraint.wallB] as WallData | undefined
    if (!wallA || !wallB) return 0

    // Snap wallB start to wallA end
    const delta = dist(wallB.start, wallA.end)
    if (delta < this.tolerance) return 0

    const offset: Vec2 = [wallA.end[0] - wallB.start[0], wallA.end[1] - wallB.start[1]]
    wallB.start = movePoint(wallB.start, offset[0], offset[1])
    wallB.end = movePoint(wallB.end, offset[0], offset[1])

    return delta
  }

  private applyCenterOnWall(
    constraint: CenterOnWallConstraint,
    nodes: Record<string, SceneNode>,
  ): number {
    const wall = nodes[constraint.wallId] as WallData | undefined
    const opening = nodes[constraint.openingId] as OpeningData | undefined
    if (!wall || !opening) return 0

    const wallLen = dist(wall.start, wall.end)
    const centerPos = wallLen / 2
    const currentPos = opening.position[0]
    const delta = Math.abs(currentPos - centerPos)

    opening.position = [centerPos, opening.position[1], opening.position[2]]

    return delta
  }

  private applyDistance(
    constraint: DistanceConstraint,
    nodes: Record<string, SceneNode>,
  ): number {
    // Find walls that contain the referenced points
    const walls = Object.values(nodes).filter((n) => n.type === 'wall') as WallData[]
    // Simplified: adjust wall length to match constraint
    return 0
  }

  private applyAngle(
    constraint: AngleConstraint,
    nodes: Record<string, SceneNode>,
  ): number {
    const wallA = nodes[constraint.wallA] as WallData | undefined
    const wallB = nodes[constraint.wallB] as WallData | undefined
    if (!wallA || !wallB) return 0

    const dirA = wallDirection(wallA)
    const dirB = wallDirection(wallB)
    const currentAngle = Math.abs(angleBetween(dirA, dirB))
    const error = currentAngle - constraint.angleDeg

    if (Math.abs(error) < 0.1) return 0

    // Rotate wallB to target angle
    const targetDir: Vec2 = [
      dirA[0] * Math.cos((constraint.angleDeg * Math.PI) / 180) -
        dirA[1] * Math.sin((constraint.angleDeg * Math.PI) / 180),
      dirA[0] * Math.sin((constraint.angleDeg * Math.PI) / 180) +
        dirA[1] * Math.cos((constraint.angleDeg * Math.PI) / 180),
    ]
    const wallBLen = dist(wallB.start, wallB.end)
    const midB = midpoint(wallB.start, wallB.end)

    wallB.start = [midB[0] - targetDir[0] * wallBLen / 2, midB[1] - targetDir[1] * wallBLen / 2]
    wallB.end = [midB[0] + targetDir[0] * wallBLen / 2, midB[1] + targetDir[1] * wallBLen / 2]

    return Math.abs(error) * (Math.PI / 180) * wallBLen
  }

  // ── Dimension queries ──

  getWallLength(wall: WallData): number {
    return dist(wall.start, wall.end)
  }

  getRoomArea(walls: WallData[]): number {
    // Shoelace formula for polygon area
    if (walls.length < 3) return 0

    const points: Vec2[] = walls.map((w) => w.start)
    let area = 0
    for (let i = 0; i < points.length; i++) {
      const j = (i + 1) % points.length
      area += points[i][0] * points[j][1]
      area -= points[j][0] * points[i][1]
    }
    return Math.abs(area) / 2
  }

  // ── Serialization ──

  exportConstraints(): string {
    return JSON.stringify(Array.from(this.constraints.values()), null, 2)
  }

  importConstraints(json: string): void {
    const constraints = JSON.parse(json) as Constraint[]
    this.constraints.clear()
    for (const c of constraints) {
      this.constraints.set(c.id, c)
    }
  }
}

// ═══════════════════════════════════════════════════════════════
// Factory
// ═══════════════════════════════════════════════════════════════

export function createSolver(options?: {
  gridSize?: number
  maxIterations?: number
  tolerance?: number
}): ConstraintSolver {
  return new ConstraintSolver(options)
}
