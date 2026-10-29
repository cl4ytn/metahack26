import { describe, expect, it } from 'vitest'
import { edgePath } from '../components/geometry'
describe('directional graph connections', () => {
 it('attaches rightward edges at facing sides', () => { expect(edgePath({x:0,y:0},{x:400,y:0})).toMatch(/^M220,60 C.* 400,60$/) })
 it('attaches reversed edges at facing sides', () => { expect(edgePath({x:400,y:0},{x:0,y:0})).toMatch(/^M400,60 C.* 220,60$/) })
 it('attaches vertically stacked edges at bottom and top', () => { expect(edgePath({x:0,y:0},{x:0,y:300})).toMatch(/^M110,150 C.* 110,300$/) })
 it('attaches upward edges at top and bottom', () => { expect(edgePath({x:0,y:300},{x:0,y:0})).toMatch(/^M110,300 C.* 110,150$/) })
})
