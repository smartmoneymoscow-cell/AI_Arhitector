/**
 * aedifex-bridge.ts — thin client for the aedifex-bridge REST API.
 *
 * aedifex-bridge exposes auxiliary operations the editor itself can't do
 * (IFC export, DXF import, Blender render) by delegating to the AI_Arhitector
 * microservices (ifc-service / cad-service / blender-service). This module
 * is the missing piece that actually calls it — previously
 * NEXT_PUBLIC_API_URL was wired through docker-compose but nothing in the
 * editor ever read it.
 *
 * NEXT_PUBLIC_API_URL should be a same-origin path (e.g. "/aedifex/api",
 * proxied by Nginx — see nginx.conf) rather than a Docker-internal
 * hostname, since this code runs in the user's browser, not in a
 * container.
 */

export class AedifexBridgeError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message)
    this.name = 'AedifexBridgeError'
  }
}

function getBridgeBaseUrl(): string | null {
  const url = process.env.NEXT_PUBLIC_API_URL
  return url && url.length > 0 ? url.replace(/\/$/, '') : null
}

/** Whether the bridge is configured for this deployment. Use to conditionally show export/import UI. */
export function isBridgeConfigured(): boolean {
  return getBridgeBaseUrl() !== null
}

export interface AedifexSceneExport {
  nodes: Record<string, unknown>
  rootNodeIds: string[]
}

/**
 * Export the current scene to an IFC file via aedifex-bridge -> ifc-service.
 *
 * Known limitation (not fixed by this client): aedifex-bridge's current
 * scene -> IFC parameter mapping only extracts flat wall/door/window/slab
 * lists, not the floors[].rooms[] structure ifc-service's generator expects.
 * The exported file will currently be a valid but mostly empty IFC shell
 * (Site + Building only) until that mapping is built out on the bridge
 * side — this call itself will succeed once bridge/ifc-service are up.
 */
export async function exportSceneToIfc(scene: AedifexSceneExport): Promise<Blob> {
  const base = getBridgeBaseUrl()
  if (!base) {
    throw new AedifexBridgeError(
      'IFC export is not configured for this deployment (NEXT_PUBLIC_API_URL is unset).',
    )
  }

  let res: Response
  try {
    res = await fetch(`${base}/v1/export/ifc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene, format: 'ifc' }),
    })
  } catch {
    throw new AedifexBridgeError('Could not reach aedifex-bridge. Is it running?')
  }

  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json())?.detail ?? ''
    } catch {
      // response wasn't JSON — ignore, we'll use the status text below
    }
    throw new AedifexBridgeError(
      detail || `IFC export failed (HTTP ${res.status})`,
      res.status,
    )
  }

  return res.blob()
}
