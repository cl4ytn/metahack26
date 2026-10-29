interface Point { x: number; y: number }
const WIDTH = 220
const HEIGHT = 150
/** Attach horizontal neighbours at facing sides and stacked nodes at top/bottom. */
export function edgePath(source: Point, target: Point): string {
  if (source.x + WIDTH + 20 <= target.x) {
    const sx = source.x + WIDTH, tx = target.x
    const offset = Math.max(40, (tx - sx) / 2)
    return `M${sx},${source.y + 60} C${sx + offset},${source.y + 60} ${tx - offset},${target.y + 60} ${tx},${target.y + 60}`
  }
  if (target.x + WIDTH + 20 <= source.x) {
    const sx = source.x, tx = target.x + WIDTH
    const offset = Math.max(40, (sx - tx) / 2)
    return `M${sx},${source.y + 60} C${sx - offset},${source.y + 60} ${tx + offset},${target.y + 60} ${tx},${target.y + 60}`
  }
  const down = target.y >= source.y
  const sx = source.x + WIDTH / 2, tx = target.x + WIDTH / 2
  const sy = source.y + (down ? HEIGHT : 0), ty = target.y + (down ? 0 : HEIGHT)
  const offset = Math.max(40, Math.abs(ty - sy) / 2) * (down ? 1 : -1)
  return `M${sx},${sy} C${sx},${sy + offset} ${tx},${ty - offset} ${tx},${ty}`
}
