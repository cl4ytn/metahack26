import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { INITIAL_GRAPH, fetchArchitecture, updateArchitecture, approveArchitecture, decomposeRequirement, validateGraph, fetchRevisionImpact, fetchTaskSchedule, verifyTask, resetTask } from '../services/api'
import { serializeGraph } from '../services/export'
afterEach(()=>vi.unstubAllGlobals())
describe('API boundaries',()=>{
 const calls = [()=>fetchArchitecture(),()=>updateArchitecture(INITIAL_GRAPH),()=>approveArchitecture(2),()=>decomposeRequirement('requirement'),()=>validateGraph(),()=>fetchRevisionImpact('node','a'),()=>fetchTaskSchedule(),()=>verifyTask('a',{command:['pytest']}),()=>resetTask('a')]
 it.each([400,403,404,409,500])('rejects every failed API operation (%i)',async status=>{vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>new Response('Rejected',{status})));for(const call of calls)await expect(call()).rejects.toThrow(String(status))})
 it('does not simulate any success when disconnected',async()=>{vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('offline')));for(const call of calls)await expect(call()).rejects.toThrow('offline')})
 it('uses real command argv and escaped task ids',async()=>{const fetch=vi.fn().mockResolvedValue(new Response('{}',{status:200}));vi.stubGlobal('fetch',fetch);await verifyTask('task/a',{command:['python','-m','pytest']});expect(fetch).toHaveBeenCalledWith('/api/tasks/task%2Fa/verify',expect.objectContaining({method:'POST',body:JSON.stringify({command:['python','-m','pytest']})}))})
 it('sends approval revision precondition',async()=>{const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify(INITIAL_GRAPH)));vi.stubGlobal('fetch',fetch);await approveArchitecture(9);expect(fetch).toHaveBeenCalledWith('/api/architecture/approve',expect.objectContaining({body:'{"revision":9}'}))})
 it('preserves authoritative server states and supplies only layout',async()=>{const graph={...INITIAL_GRAPH,nodes:[{...INITIAL_GRAPH.nodes[0],x:undefined,y:undefined}],tasks:[{...INITIAL_GRAPH.tasks[0],status:'blocked'}]};vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify(graph))));const loaded=await fetchArchitecture();expect(loaded.tasks[0].status).toBe('blocked');expect(loaded.nodes[0].metrics).toBeUndefined();expect(loaded.nodes[0].x).toBeTypeOf('number')})
})
describe('exports and presentation',()=>{
 it('round trips the complete graph with quotes, newlines and evidence',()=>{const graph={...INITIAL_GRAPH,requirement:'quote " and\nnew line: \\ path',verifications:[{id:'v',stdout:'line\n"output"'}]};expect(JSON.parse(serializeGraph(graph as typeof INITIAL_GRAPH))).toEqual(graph)})
 it('sample has no fabricated verification, progress or telemetry',()=>{expect(INITIAL_GRAPH.executions).toEqual([]);expect(INITIAL_GRAPH.verifications).toEqual([]);expect(INITIAL_GRAPH.tasks.every(t=>t.status==='pending')).toBe(true);expect(INITIAL_GRAPH.nodes.every(n=>!n.metrics)).toBe(true)})
 it('loads the real stylesheet with responsive layouts and visible keyboard focus',()=>{const main=readFileSync(new URL('../main.tsx',import.meta.url),'utf8'); const css=readFileSync(new URL('../index.css',import.meta.url),'utf8');expect(main).toContain("import './index.css'");expect(css).toContain('@media(max-width:760px)');expect(css).toContain(':focus-visible');expect(css).toContain('.graph-node');expect(css).not.toContain('@import "tailwindcss"')})
})
